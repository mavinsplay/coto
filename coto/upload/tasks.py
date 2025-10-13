from datetime import timedelta
import logging
import os
from pathlib import Path
import subprocess
import time

from celery import shared_task
from django.conf import settings
import ffmpeg
import psutil

__all__ = ("extract_video_metadata", "generate_hls")

logger = logging.getLogger(__name__)


@shared_task
def delete_video_file_delayed(video_id, delay=5):
    """Удаляет исходный видеофайл с повторными попытками"""
    from upload.models import Video
    from django.core.files.storage import default_storage

    max_attempts = 10

    for attempt in range(1, max_attempts + 1):
        try:
            video = Video.objects.get(pk=video_id)
            if video.file and default_storage.exists(video.file.name):
                default_storage.delete(video.file.name)
                logger.info(
                    f"[Delete Task] Файл удален: {video.file.name}",
                )
                return
        except Video.DoesNotExist:
            logger.warning(
                f"[Delete Task] Видео {video_id} не найдено",
            )
            return

        except Exception as e:
            logger.warning(
                f"[Delete Task] Попытка {attempt}/{max_attempts}: " f"{e}",
            )
            if attempt < max_attempts:
                time.sleep(delay)

            continue

    logger.error(
        f"[Delete Task] Не удалось удалить файл видео "
        f"{video_id} после {max_attempts} попыток",
    )


@shared_task
def extract_video_metadata(video_id):
    logger.info(f"[Metadata Task] Начало обработки видео {video_id}")
    try:
        from upload.models import Video

        video = Video.objects.get(pk=video_id)
        file_path = Path(video.file.path)
        logger.info(f"[Metadata Task] Путь файла: {file_path}")
        logger.info(f"[Metadata Task] Файл существует: {file_path.exists()}")

        # Определение длительности
        if not video.duration:
            logger.info("[Metadata Task] Получение длительности...")
            probe = ffmpeg.probe(str(file_path))
            duration_seconds = float(probe["format"]["duration"])
            video.duration = timedelta(seconds=duration_seconds)
            logger.info(f"[Metadata Task] Длительность: {video.duration}")

        # Определение размера
        if not video.file_size:
            logger.info("[Metadata Task] Получение размера...")
            video.file_size = file_path.stat().st_size
            logger.info("[Metadata Task] Размер: {video.file_size} байт")

        video.save(update_fields=["duration", "file_size"])
        logger.info("[Metadata Task] Сохранено успешно")
    except Video.DoesNotExist:
        logger.error(f"[Metadata Task] Видео {video_id} не найдено")
    except Exception as e:
        logger.error(
            f"[Metadata Task] Ошибка при обработке видео {video_id}: {e}",
            exc_info=True,
        )


def try_update_video_progress(
    video,
    progress=None,
    status=None,
    log_line=None,
    force=False,
    delta_percent=1,
    min_interval_sec=2,
):
    """
    Обновление прогресса в модели Video с rate-limit'ом.
    """
    if not hasattr(video, "_last_progress_update"):
        video._last_progress_update = {
            "time": 0,
            "progress": video.hls_progress,
        }

    last = video._last_progress_update

    should = False
    if force:
        should = True
    else:
        if (
            progress is not None
            and abs((progress or 0) - (last["progress"] or 0)) >= delta_percent
        ):
            should = True
        elif (time.time() - last["time"]) >= min_interval_sec:
            should = True

    if not should:
        if log_line:
            video.hls_log = (video.hls_log + "\n" + log_line)[-8000:]

        return

    if progress is not None:
        video.hls_progress = max(0, min(100, int(progress)))
        last["progress"] = video.hls_progress

    if status is not None:
        video.hls_status = status

    if log_line:
        video.hls_log = (video.hls_log + "\n" + log_line)[-8000:]

    try:
        video.save(update_fields=["hls_progress", "hls_status", "hls_log"])
        video._last_progress_update["time"] = time.time()
    except Exception:
        logger.exception("Could not save video progress")


def _ffprobe_duration(path):
    try:
        res = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        out = (res.stdout or "").strip()
        if out:
            return float(out)
    except Exception:
        logger.exception("ffprobe fallback failed for %s", path)

    return 0.0


@shared_task(bind=True)
def generate_hls(self, video_id):
    """
    Генерация HLS с автоподбором параметров и обновлением прогресса.
    """
    logger.info(f"[HLS Task] Начало обработки видео {video_id}")

    try:
        from upload.models import Video

        try:
            video = Video.objects.get(pk=video_id)
        except Video.DoesNotExist:
            logger.error(f"[HLS Task] Видео {video_id} не найдено")
            return

        raw_path = Path(video.file.path)
        logger.info(f"[HLS Task] Путь файла: {raw_path}")
        logger.info(f"[HLS Task] Файл существует: {raw_path.exists()}")

        # Инициализация состояния
        video.hls_progress = 0
        video.hls_status = "pending"
        video.hls_log = ""
        video.save(update_fields=["hls_progress", "hls_status", "hls_log"])
        logger.info("[HLS Task] Состояние инициализировано")

        out_dir = Path(settings.MEDIA_ROOT) / "streams" / str(video.pk)
        out_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[HLS Task] Выходная директория: {out_dir}")

        manifest_path = out_dir / "master.m3u8"
        segment_pattern = out_dir / "seg%d.ts"

        # Попытка получить метаданные через ffmpeg.probe
        logger.info("[HLS Task] Получение метаданных видео...")
        try:
            probe = ffmpeg.probe(str(raw_path))
        except Exception as e:
            logger.warning(f"[HLS Task] ffmpeg.probe ошибка: {e}")
            probe = {}

        try:
            duration = float(probe.get("format", {}).get("duration") or 0.0)
        except Exception:
            duration = 0.0

        # fallback через ffprobe binary если duration == 0
        if not duration:
            duration = _ffprobe_duration(raw_path)
            logger.debug("[HLS Task] ffprobe fallback duration=%s", duration)

        logger.info(f"[HLS Task] Длительность видео: {duration} сек")

        # Найти потоки
        v_stream = None
        a_stream = None
        for s in probe.get("streams", []):
            if s.get("codec_type") == "video" and v_stream is None:
                v_stream = s

            if s.get("codec_type") == "audio" and a_stream is None:
                a_stream = s

        video_codec = v_stream.get("codec_name") if v_stream else None
        audio_codec = a_stream.get("codec_name") if a_stream else None
        logger.info(
            f"[HLS Task] Видео кодек:\
                {video_codec}, Аудио кодек: {audio_codec}",
        )

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
        logger.info(f"[HLS Task] FPS видео: {input_fps}")

        def run_ffmpeg_with_progress(cmd, phase_label, duration_seconds):
            """
            Запускает ffmpeg с -progress pipe:1 и парсит ключи вида key=value.
            duration_seconds может быть 0.0 (неизвестно).
            """
            logger.info(
                "[HLS Task] Phase %s start; duration=%s",
                phase_label,
                duration_seconds,
            )
            video.hls_status = phase_label
            try_update_video_progress(
                video,
                status=video.hls_status,
                force=True,
            )

            logger.info(f"[HLS Task] Команда ffmpeg: {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                universal_newlines=False,
            )

            current_out_time = None
            try:
                while True:
                    chunk = proc.stdout.readline()
                    if not chunk:
                        break

                    # безопасное декодирование
                    try:
                        decoded = chunk.decode("utf-8", errors="replace")
                    except Exception:
                        decoded = chunk.decode("latin1", errors="replace")

                    # один chunk может содержать много строк; разобьём
                    for raw_line in decoded.replace("\r", "\n").splitlines():
                        line = raw_line.strip()
                        if not line:
                            continue

                        # сохраняем хвост лога (rate-limited внутри функции)
                        try_update_video_progress(video, log_line=line)

                        # разбор key=value
                        if "=" in line:
                            key, value = line.split("=", 1)
                            key = key.strip()
                            value = value.strip()
                        else:
                            key = line
                            value = ""

                        if key == "out_time_ms":
                            try:
                                out_ms = int(value)
                                current_out_time = out_ms / 1000.0
                            except Exception:
                                pass
                        elif key == "out_time":
                            try:
                                parts = value.split(":")
                                secs = float(parts[-1])
                                mins = int(parts[-2]) if len(parts) >= 2 else 0
                                hrs = int(parts[-3]) if len(parts) >= 3 else 0
                                current_out_time = (
                                    hrs * 3600 + mins * 60 + secs
                                )
                            except Exception:
                                pass
                        elif key == "time":
                            try:
                                parts = value.split(":")
                                secs = float(parts[-1])
                                mins = int(parts[-2]) if len(parts) >= 2 else 0
                                hrs = int(parts[-3]) if len(parts) >= 3 else 0
                                current_out_time = (
                                    hrs * 3600 + mins * 60 + secs
                                )
                            except Exception:
                                pass
                        elif key == "progress":
                            if value == "end":
                                try_update_video_progress(
                                    video,
                                    progress=100,
                                    status=video.hls_status,
                                    log_line=line,
                                    force=True,
                                )

                        # вычисляем процент при известной длительности
                        if duration_seconds and (current_out_time is not None):
                            try:
                                percent = int(
                                    min(
                                        100.0,
                                        (current_out_time / duration_seconds)
                                        * 100.0,
                                    ),
                                )
                            except Exception:
                                percent = None

                            if percent is not None:
                                # если первая ненулевая запись — форсим её
                                force_write = (
                                    video.hls_progress == 0 and percent > 0
                                )
                                try_update_video_progress(
                                    video,
                                    progress=percent,
                                    status=video.hls_status,
                                    force=force_write,
                                )

                proc.wait()
                logger.info(
                    f"[HLS Task] Phase {phase_label} \
                        завершена, код: {proc.returncode}",
                )
                if proc.returncode != 0:
                    raise subprocess.CalledProcessError(proc.returncode, cmd)
            finally:
                try:
                    if proc.stdout:
                        proc.stdout.close()
                except Exception:
                    pass

        # --- copy path (если возможно) ---
        if (
            video_codec == "h264"
            and audio_codec in ("aac", "mp4a")
            and input_fps >= 59.5
        ):
            logger.info(
                "[HLS Task] Используется копирование без перекводирования",
            )
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
                "-progress",
                "pipe:1",
                "-nostats",
            ]
            run_ffmpeg_with_progress(cmd, "copy", duration)

            rel = manifest_path.relative_to(settings.MEDIA_ROOT)
            video.hls_manifest.name = str(rel).replace("\\", "/")
            video.hls_status = "done"
            try_update_video_progress(
                video,
                progress=100,
                status="done",
                force=True,
            )
            video.save(
                update_fields=[
                    "hls_manifest",
                    "hls_progress",
                    "hls_status",
                    "hls_log",
                ],
            )
            delete_video_file_delayed.delay(video.pk, delay=5)
            logger.info("[HLS Task] Запланировано удаление исходного файла")
            logger.info("[HLS Task] Обработка завершена (copy mode)")
            return

        # --- autotune ---
        logger.info("[HLS Task] Используется перекводирование")
        mem_mb = int(psutil.virtual_memory().available / (1024 * 1024))
        cpu_count = os.cpu_count() or 1
        logger.info(
            f"[HLS Task] Доступная память: {mem_mb}MB, ЦПУ: {cpu_count}",
        )

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
            f"[HLS Task] Параметры кодирования:\
                preset={preset}, threads={threads}, crf={crf}",
        )

        vf_filter = (
            "scale='if(gt(a,1920/1080),1920,trunc(iw/2)*2)':"
            "'if(gt(a,1920/1080),trunc(1080/2)*2,trunc(ih/2)*2)',"
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
            "-progress",
            "pipe:1",
            "-nostats",
        ]

        run_ffmpeg_with_progress(transcode_cmd, "transcode", duration)

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
            "-progress",
            "pipe:1",
            "-nostats",
        ]
        run_ffmpeg_with_progress(seg_cmd, "segment", duration)
        delete_video_file_delayed.delay(video.pk, delay=5)
        logger.info("[HLS Task] Запланировано удаление исходного файла")
        try:
            if tmp_mp4.exists():
                tmp_mp4.unlink()
        except Exception:
            logger.exception("Не удалось удалить временный файл %s", tmp_mp4)

        rel = manifest_path.relative_to(settings.MEDIA_ROOT)
        video.hls_manifest.name = str(rel).replace("\\", "/")
        video.hls_status = "done"
        try_update_video_progress(
            video,
            progress=100,
            status="done",
            force=True,
        )
        video.save(
            update_fields=[
                "hls_manifest",
                "hls_progress",
                "hls_status",
                "hls_log",
            ],
        )
        logger.info("[HLS Task] Обработка завершена успешно")

    except subprocess.CalledProcessError as cpe:
        logger.error(
            "[HLS Task] ffmpeg exited with error: %s",
            cpe,
            exc_info=True,
        )
        try:
            video.hls_status = "error"
            try_update_video_progress(
                video,
                status="error",
                log_line=str(cpe),
                force=True,
            )
        except Exception:
            pass

        raise
    except Exception as e:
        logger.exception("[HLS Task] Ошибка: %s", e)
        try:
            video.hls_status = "error"
            try_update_video_progress(
                video,
                status="error",
                log_line=str(e),
                force=True,
            )
        except Exception:
            pass

        raise
