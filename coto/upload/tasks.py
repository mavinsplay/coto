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

        vf_filter = (
            "scale='if(gt(a,1920/1080),1920,trunc(iw/2)*2)':'if(gt(a,1920/1080)\
                ,trunc(1080/2)*2,trunc(ih/2)*2)',"
            "pad=ceil(iw/2)*2:ceil(ih/2)*2:(ow-iw)/2:(oh-ih)/2,fps=60"
        )

        cmd = [
            "ffmpeg",
            "-i",
            str(raw_path),
            "-vf",
            vf_filter,
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
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
            "-flags",
            "+global_header",
            "-hls_time",
            "6",
            "-hls_list_size",
            "0",
            "-hls_segment_filename",
            str(segment_pattern),
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
