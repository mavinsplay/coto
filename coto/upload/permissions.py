from django.core.exceptions import PermissionDenied


__all__ = [
    "check_user_can_upload",
    "check_user_owns_playlist",
    "validate_file_size",
    "validate_video_extension",
]


def check_user_can_upload(user):
    """
    Проверяет, может ли пользователь загружать видео.
    """
    if not user.is_authenticated:
        raise PermissionDenied("Необходима авторизация для загрузки видео")

    if not user.is_active:
        raise PermissionDenied("Аккаунт деактивирован")

    return True


def check_user_owns_playlist(user, playlist):
    """
    Проверяет, является ли пользователь владельцем плейлиста.
    """
    if not user.is_authenticated:
        raise PermissionDenied("Необходима авторизация")

    if playlist.created_by != user:
        raise PermissionDenied("Вы не являетесь владельцем этого плейлиста")

    return True


def validate_file_size(file_size, max_size_mb=5000):
    """
    Валидация размера файла (по умолчанию максимум 5GB).
    """
    max_size_bytes = max_size_mb * 1024 * 1024

    if file_size > max_size_bytes:
        raise ValueError(
            f"Размер файла превышает максимально допустимый ({max_size_mb}MB)",
        )

    return True


def validate_video_extension(filename):
    """
    Проверка допустимых расширений видеофайлов.
    """
    allowed_extensions = [
        ".mp4",
        ".mkv",
        ".avi",
        ".mov",
        ".wmv",
        ".flv",
        ".webm",
        ".m4v",
        ".mpg",
        ".mpeg",
        ".3gp",
        ".ogv",
    ]
    # Получаем расширение из имени файла
    if "." not in filename:
        raise ValueError(
            f"Недопустимый формат файла. "
            f"Разрешены: {', '.join(allowed_extensions)}",
        )

    extension = "." + filename.lower().split(".")[-1]

    if extension not in allowed_extensions:
        raise ValueError(
            f"Недопустимый формат файла '{extension}'. "
            f"Разрешены: {', '.join(allowed_extensions)}",
        )

    return True
