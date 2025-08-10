from datetime import timedelta
import logging
from pathlib import Path
import subprocess

from celery import shared_task
from django.conf import settings
import ffmpeg

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


@shared_task
def generate_hls(video_id):
    try:
        from upload.models import Video

        video = Video.objects.get(pk=video_id)
        raw_path = Path(video.file.path)

        out_dir = Path(settings.MEDIA_ROOT) / "streams" / str(video.pk)
        out_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = out_dir / "master.m3u8"
        segment_pattern = out_dir / "seg%d.ts"

        cmd = [
            "ffmpeg",
            "-i",
            raw_path,
            "-vf",
            "scale=w=1920:h=1080:force_original_aspect_ratio=decrease,fps=60",
            "-c:v",
            "libx264",
            "-preset",
            "slow",  # Лучше качество (медленнее кодирование)
            "-crf",
            "18",  # Лучше визуальное качество (меньше — выше качество)
            "-maxrate",
            "12M",  # Выше пик битрейта
            "-bufsize",
            "20M",  # Соответствует maxrate
            "-c:a",
            "aac",
            "-b:a",
            "192k",  # Лучше звук
            "-ar",
            "48000",  # Частота дискретизации
            "-ac",
            "2",  # Стерео
            "-flags",
            "+global_header",
            "-hls_time",
            "6",  # Частые сегменты для плавности (меньше задержка)
            "-hls_list_size",
            "0",
            "-hls_segment_filename",
            segment_pattern,
            str(manifest_path),
        ]

        subprocess.run(cmd, check=True)

        relative_manifest = manifest_path.relative_to(settings.MEDIA_ROOT)
        video.hls_manifest.name = str(relative_manifest).replace("\\", "/")
        video.save(update_fields=["hls_manifest"])

    except Exception as e:
        logger.error(
            "[HLS Task] Ошибка",
            e,
            exc_info=True,
        )
