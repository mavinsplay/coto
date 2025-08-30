from datetime import timedelta
import logging
import os
from pathlib import Path
import subprocess

from celery import shared_task
from django.conf import settings
import ffmpeg
import psutil

__all__ = ("extract_video_metadata", "generate_hls")

logger = logging.getLogger(__name__)


@shared_task
def extract_video_metadata(video_id):
    try:
        from upload.models import Video

        video = Video.objects.get(pk=video_id)
        file_path = Path(video.file.path)

        # Определение длительности
        if not video.duration:
            probe = ffmpeg.probe(str(file_path))
            duration_seconds = float(probe["format"]["duration"])
            video.duration = timedelta(seconds=duration_seconds)

        # Определение размера
        if not video.file_size:
            video.file_size = file_path.stat().st_size

        video.save(update_fields=["duration", "file_size"])
    except Exception as e:
        logger.error(
            "[Metadata Task] Ошибка",
            e,
            exc_info=True,
        )


@shared_task(bind=True)
def generate_hls(self, video_id):
    """
    Генерация HLS с автоподбором параметров.
    Сохраняет 60 fps; старается минимизировать пиковую память за счет:
      - использования copy-пути если возможно
      - адаптации preset/threads/rc_lookahead по доступной памяти
      - двухшаговой обработки: транскод -> сегментация (копирование)
    """
    try:
        from upload.models import Video

        video = Video.objects.get(pk=video_id)
        raw_path = Path(video.file.path)

        out_dir = Path(settings.MEDIA_ROOT) / "streams" / str(video.pk)
        out_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = out_dir / "master.m3u8"
        segment_pattern = out_dir / "seg%d.ts"
        ffmpeg_log = out_dir / "ffmpeg.log"

        # --- 1) проба метаданных входа ---
        try:
            probe = ffmpeg.probe(str(raw_path))
        except Exception:
            probe = {}

        # Найти видеопоток и аудиопоток
        v_stream = None
        a_stream = None
        for s in probe.get("streams", []):
            if s.get("codec_type") == "video" and v_stream is None:
                v_stream = s

            if s.get("codec_type") == "audio" and a_stream is None:
                a_stream = s

        video_codec = v_stream.get("codec_name") if v_stream else None
        audio_codec = a_stream.get("codec_name") if a_stream else None

        def parse_fps(s):
            if not s:
                return 0.0

            afr = s.get("avg_frame_rate") or s.get("r_frame_rate") or "0/1"
            try:
                if "/" in afr:
                    num, den = afr.split("/")
                    return float(num) / float(den) if float(den) != 0 else 0.0

                return float(afr)
            except Exception:
                return 0.0

        input_fps = parse_fps(v_stream) if v_stream else 0.0

        if (
            video_codec == "h264"
            and audio_codec in ("aac", "mp4a")
            and input_fps >= 59.5
        ):
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(raw_path),
                "-c",
                "copy",
                "-bsf:v",
                "h264_mp4toannexb",
                "-hls_time",
                "6",
                "-hls_list_size",
                "0",
                "-hls_segment_filename",
                str(segment_pattern),
                str(manifest_path),
            ]
            logger.info(
                "[HLS Task] Используем путь \
                copy (вход уже h264/aac 60fps).",
            )

            with ffmpeg_log.open("ab") as logf:
                subprocess.run(cmd, check=True, stdout=logf, stderr=logf)

            relative_manifest = manifest_path.relative_to(settings.MEDIA_ROOT)
            video.hls_manifest.name = str(relative_manifest).replace("\\", "/")
            video.save(update_fields=["hls_manifest"])
            return

        mem_mb = int(psutil.virtual_memory().available / (1024 * 1024))
        cpu_count = os.cpu_count() or 1

        if mem_mb < 1800:
            preset = "fast"
            threads = 1
            rc_lookahead = 6
            crf = 18
        elif mem_mb < 3200:
            preset = "fast"
            threads = max(1, min(cpu_count, 2))
            rc_lookahead = 8
            crf = 18
        elif mem_mb < 6000:
            preset = "slow"
            threads = max(1, min(cpu_count, 2))
            rc_lookahead = 10
            crf = 18
        else:
            preset = "slow"
            threads = max(1, min(cpu_count, 4))
            rc_lookahead = 20
            crf = 18

        logger.info(
            "[HLS Task] Autotune: mem_mb=%d cpu=%d preset=%s threads=%d \
                rc_lookahead=%d crf=%s",
            mem_mb,
            cpu_count,
            preset,
            threads,
            rc_lookahead,
            crf,
        )

        vf_filter = (
            "scale='if(gt(a,1920/1080),1920,trunc(iw/2)*2)':'if(gt(a,1920/1080)\
                ,trunc(1080/2)*2,trunc(ih/2)*2)',"
            "pad=ceil(iw/2)*2:ceil(ih/2)*2:(ow-iw)/2:(oh-ih)/2,fps=60"
        )
        tmp_mp4 = out_dir / "transcoded_temp.mp4"

        transcode_cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_path),
            "-vf",
            vf_filter,
            "-c:v",
            "libx264",
            "-preset",
            preset,
            "-crf",
            str(crf),
            "-x264-params",
            f"rc_lookahead={rc_lookahead}:ref=3",
            "-threads",
            str(threads),
            "-maxrate",
            "12M",
            "-bufsize",
            "20M",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-movflags",
            "+faststart",
            str(tmp_mp4),
        ]

        with ffmpeg_log.open("ab") as logf:
            logger.info("[HLS Task] Запуск транскодинга в %s", str(tmp_mp4))
            subprocess.run(transcode_cmd, check=True, stdout=logf, stderr=logf)

            seg_cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(tmp_mp4),
                "-c",
                "copy",
                "-bsf:v",
                "h264_mp4toannexb",
                "-hls_time",
                "6",
                "-hls_list_size",
                "0",
                "-hls_segment_filename",
                str(segment_pattern),
                str(manifest_path),
            ]
            logger.info(
                "[HLS Task] Запуск сегментации (копирование) в %s",
                str(manifest_path),
            )
            subprocess.run(seg_cmd, check=True, stdout=logf, stderr=logf)

        try:
            if tmp_mp4.exists():
                tmp_mp4.unlink()
        except Exception:
            logger.exception("Не удалось удалить временный файл %s", tmp_mp4)

        relative_manifest = manifest_path.relative_to(settings.MEDIA_ROOT)
        video.hls_manifest.name = str(relative_manifest).replace("\\", "/")
        video.save(update_fields=["hls_manifest"])

    except subprocess.CalledProcessError as cpe:
        logger.error(
            "[HLS Task] ffmpeg завершился с ошибкой: %s",
            cpe,
            exc_info=True,
        )
        raise
    except Exception as e:
        logger.error(
            "[HLS Task] Ошибка",
            e,
            exc_info=True,
        )
        raise
