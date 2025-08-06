from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

__all__ = ["RoomsConfig"]


class RoomsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rooms"
    verbose_name = _("Комнаты")
