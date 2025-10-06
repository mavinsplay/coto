import logging
from pathlib import Path

from django.core.files.base import File
from django.core.files.storage import default_storage
from django.utils import timezone


__all__ = ["attach_chunked_file_to_instance"]


logger = logging.getLogger(__name__)


def attach_chunked_file_to_instance(
    instance,
    chunked_path: str,
    final_filename: str | None = None,
):
    if not chunked_path:
        raise ValueError("chunked_path is required")

    if instance.file and instance.file.name:
        logger.info(
            "Instance %s already has file %s, skipping attach",
            instance, instance.file.name,
        )
        return

    storage = default_storage

    if not storage.exists(chunked_path):
        raise FileNotFoundError(f"Chunked file not found: {chunked_path}")

    if final_filename is None:
        name = Path(chunked_path).name.replace(".part", "")
        final_filename = timezone.now().strftime("videos/%Y/%m/%d/") + name

    # Попытка быстрого перемещения на локальной FS через Path
    try:
        src_path = Path(storage.path(chunked_path))
        dest_path = Path(storage.path(final_filename))
        dest_dir = dest_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)
        # атомарный replace если возможен
        try:
            src_path.replace(dest_path)
        except Exception:
            src_path.rename(dest_path)
        # Прописать относительный путь в instance (как storage ожидает)
        instance.file.name = final_filename
        return
    except NotImplementedError:
        # storage не предоставляет .path() (например S3) — fallback
        logger.debug("Storage has no path(); falling back to streaming copy.")
    except Exception as exc:
        logger.warning(
            "Fast move failed, fallback to streaming. Error: %s",
            exc,
            exc_info=True,
        )

    # Fallback: потоковое копирование (не читаем весь файл в память)
    try:
        # Откроем исход и сохраним целиком в storage (streaming)
        with storage.open(chunked_path, "rb") as src:
            storage.save(final_filename, File(src))
        # Установим имя поля
        instance.file.name = final_filename
        # Удаляем временный файл
        try:
            storage.delete(chunked_path)
        except Exception:
            logger.debug(
                "Could not delete chunked file %s (ignored)",
                chunked_path,
                exc_info=True,
            )
    except Exception as exc:
        logger.exception(
            "Streaming copy failed for %s -> %s: %s",
            chunked_path,
            final_filename,
            exc,
        )
        raise
