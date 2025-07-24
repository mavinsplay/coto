from datetime import timedelta
import logging

from django.db.models.signals import pre_save
from django.dispatch import receiver
import ffmpeg

from upload.models import Video


__all__ = ["set_video_duration"]


logger = logging.getLogger(__name__)


@receiver(pre_save, sender=Video)
def set_video_duration(sender, instance, **kwargs):
    if instance.file and not instance.duration:
        try:
            probe = ffmpeg.probe(instance.file.path)
            duration_seconds = float(probe["format"]["duration"])
            instance.duration = timedelta(seconds=duration_seconds)
        except Exception as e:
            logger.error(
                "Ошибка при получении длительности видео: %s",
                e,
                exc_info=True,
            )
