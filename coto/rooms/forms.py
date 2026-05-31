import secrets
import string

from django import forms
from django.utils.translation import gettext_lazy as _

from rooms.models import WatchParty
from upload.models import Playlist, Video

__all__ = []


class RoomCreateForm(forms.ModelForm):
    """Форма для создания комнаты просмотра"""

    content_choice = forms.ChoiceField(
        label=_("Тип контента"),
        choices=[
            ("video", _("Одно видео")),
            ("playlist", _("Плейлист")),
            ("external", _("Видео по ссылке")),
        ],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        initial="video",
    )

    video = forms.ModelChoiceField(
        queryset=Video.objects.none(),
        label=_("Выберите видео"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    playlist = forms.ModelChoiceField(
        queryset=Playlist.objects.none(),
        label=_("Выберите плейлист"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    external_url = forms.URLField(
        label=_("Ссылка на видео"),
        required=False,
        widget=forms.URLInput(
            attrs={
                "class": "form-control",
                "placeholder": "https://example.com/video.mp4",
            },
        ),
    )

    generate_code = forms.BooleanField(
        label=_("Автоматически сгенерировать код доступа"),
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = WatchParty
        fields = [
            "name",
            "room_image",
            "limit_participants",
            "is_private",
            "access_code",
        ]
        # Исключаем video и playlist из Meta, чтобы избежать валидации модели
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("Введите название комнаты"),
                },
            ),
            "room_image": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                },
            ),
            "limit_participants": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "2",
                    "max": "100",
                },
            ),
            "is_private": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                },
            ),
            "access_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("Оставьте пустым для автогенерации"),
                    "readonly": "readonly",
                },
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        if user:
            # Показываем только видео и плейлисты пользователя
            self.fields["video"].queryset = Video.objects.filter(
                uploaded_by=user,
                hls_status="done",
            ).order_by("-created_at")
            self.fields["playlist"].queryset = Playlist.objects.filter(
                created_by=user,
            ).order_by("-created_at")

    def clean(self):
        cleaned_data = super().clean()
        content_choice = cleaned_data.get("content_choice")
        video = cleaned_data.get("video")
        playlist = cleaned_data.get("playlist")
        external_url = cleaned_data.get("external_url")
        is_private = cleaned_data.get("is_private")
        access_code = cleaned_data.get("access_code")
        generate_code = cleaned_data.get("generate_code")

        # Проверяем, что выбран контент
        if content_choice == "video" and not video:
            raise forms.ValidationError(_("Выберите видео для комнаты"))

        if content_choice == "playlist" and not playlist:
            raise forms.ValidationError(_("Выберите плейлист для комнаты"))

        if content_choice == "external" and not external_url:
            raise forms.ValidationError(_("Укажите ссылку на видео"))

        # Очищаем неиспользуемые поля
        if content_choice == "video":
            cleaned_data["playlist"] = None
            cleaned_data["external_url"] = ""
        elif content_choice == "playlist":
            cleaned_data["video"] = None
            cleaned_data["external_url"] = ""
        elif content_choice == "external":
            cleaned_data["video"] = None
            cleaned_data["playlist"] = None

        # Генерируем или валидируем код доступа для приватных комнат
        if is_private:
            if generate_code or not access_code:
                # Генерируем случайный код
                alphabet = string.ascii_uppercase + string.digits
                cleaned_data["access_code"] = "".join(
                    secrets.choice(alphabet) for _ in range(8)
                )
            elif access_code:
                # Валидируем введенный код
                if len(access_code) < 4:
                    raise forms.ValidationError(
                        _("Код доступа должен содержать минимум 4 символа"),
                    )
        else:
            # Для публичных комнат очищаем код
            cleaned_data["access_code"] = None

        return cleaned_data

    def clean_external_url(self):
        url = self.cleaned_data.get("external_url")
        if not url:
            return url

        # ── Google Drive: bypass yt-dlp validation ───────────────────────────
        if "drive.google.com" in url.lower():
            import re

            file_id_match = re.search(r"[-\w]{25,}", url)
            if not file_id_match:
                raise forms.ValidationError(
                    _(
                        "Не удалось найти идентификатор файла "
                        "в ссылке Google Диска.",
                    ),
                )

            self.external_title = _("Файл из облака")
            return url

        # ── YouTube and others: validate via yt-dlp ──────────────────────────
        try:
            import yt_dlp

            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "nocheckcertificate": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                # Сохраняем название для использования в save()
                self.external_title = info.get("title", "")
        except Exception as e:
            error_msg = str(e)
            if (
                "Failed to resolve" in error_msg
                or "getaddrinfo failed" in error_msg
            ):
                raise forms.ValidationError(
                    _(
                        "Не удалось найти указанный адрес (ошибка DNS). "
                        "Проверьте правильность написания ссылки.",
                    ),
                )

            raise forms.ValidationError(
                _(
                    "Не удалось получить информацию о видео. "
                    "Убедитесь, что ссылка корректна и доступна: %(error)s",
                )
                % {"error": error_msg},
            )

        return url

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Устанавливаем video или playlist из cleaned_data
        content_choice = self.cleaned_data.get("content_choice")
        if content_choice == "video":
            instance.video = self.cleaned_data.get("video")
            instance.playlist = None
            instance.external_url = ""
        elif content_choice == "playlist":
            instance.playlist = self.cleaned_data.get("playlist")
            instance.video = None
            instance.external_url = ""
        elif content_choice == "external":
            instance.external_url = self.cleaned_data.get("external_url")
            instance.video = None
            instance.playlist = None
            # Используем название, полученное во время валидации
            if hasattr(self, "external_title"):
                instance.external_title = self.external_title
            elif instance.external_url and not instance.external_title:
                try:
                    import yt_dlp

                    ydl_opts = {
                        "quiet": True,
                        "skip_download": True,
                        "nocheckcertificate": True,
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(
                            instance.external_url,
                            download=False,
                        )
                        instance.external_title = info.get("title", "")
                except Exception:
                    pass

        if commit:
            instance.save()
            self.save_m2m()

        return instance


class RoomUpdateForm(forms.ModelForm):
    """Форма для редактирования комнаты"""

    generate_code = forms.BooleanField(
        label=_("Сгенерировать новый код доступа"),
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = WatchParty
        fields = [
            "name",
            "room_image",
            "limit_participants",
            "is_private",
            "access_code",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("Введите название комнаты"),
                },
            ),
            "room_image": forms.FileInput(
                attrs={
                    "class": "form-control",
                    "accept": "image/*",
                },
            ),
            "limit_participants": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "min": "2",
                    "max": "100",
                },
            ),
            "is_private": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                },
            ),
            "access_code": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": _("Текущий код доступа"),
                },
            ),
        }

    def clean(self):
        cleaned_data = super().clean()
        is_private = cleaned_data.get("is_private")
        access_code = cleaned_data.get("access_code")
        generate_code = cleaned_data.get("generate_code")

        # Генерируем новый код или валидируем существующий
        if is_private:
            if generate_code:
                # Генерируем новый случайный код
                alphabet = string.ascii_uppercase + string.digits
                cleaned_data["access_code"] = "".join(
                    secrets.choice(alphabet) for _ in range(8)
                )
            elif not access_code:
                # Если код не указан и не запрошена генерация, оставляем старый
                if self.instance and self.instance.access_code:
                    cleaned_data["access_code"] = self.instance.access_code
                else:
                    # Генерируем код автоматически для новых приватных комнат
                    alphabet = string.ascii_uppercase + string.digits
                    cleaned_data["access_code"] = "".join(
                        secrets.choice(alphabet) for _ in range(8)
                    )
        else:
            # Для публичных комнат очищаем код
            cleaned_data["access_code"] = None

        return cleaned_data


class JoinPrivateRoomForm(forms.Form):
    """Форма для присоединения к приватной комнате по коду"""

    access_code = forms.CharField(
        label=_("Код доступа"),
        max_length=20,
        widget=forms.TextInput(
            attrs={
                "class": "form-control form-control-lg t\
                    ext-center text-uppercase",
                "placeholder": _("ВВЕДИТЕ КОД"),
                "style": "letter-spacing: 0.2em;",
            },
        ),
    )

    def clean_access_code(self):
        code = self.cleaned_data.get("access_code", "").strip().upper()
        if not code:
            raise forms.ValidationError(_("Введите код доступа"))

        # Проверяем существование комнаты с таким кодом
        try:
            room = WatchParty.objects.get(access_code=code, is_private=True)
            self.cleaned_data["room"] = room
        except WatchParty.DoesNotExist:
            raise forms.ValidationError(_("Неверный код доступа"))

        return code
