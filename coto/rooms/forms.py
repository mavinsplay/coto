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
        choices=[("video", _("Одно видео")), ("playlist", _("Плейлист"))],
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
        is_private = cleaned_data.get("is_private")
        access_code = cleaned_data.get("access_code")
        generate_code = cleaned_data.get("generate_code")

        # Проверяем, что выбран контент
        if content_choice == "video" and not video:  # noqa: R506
            raise forms.ValidationError(_("Выберите видео для комнаты"))

        elif content_choice == "playlist" and not playlist:
            raise forms.ValidationError(_("Выберите плейлист для комнаты"))

        # Очищаем неиспользуемое поле
        if content_choice == "video":
            cleaned_data["playlist"] = None
        else:
            cleaned_data["video"] = None

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

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Устанавливаем video или playlist из cleaned_data
        content_choice = self.cleaned_data.get("content_choice")
        if content_choice == "video":
            instance.video = self.cleaned_data.get("video")
            instance.playlist = None
        else:
            instance.playlist = self.cleaned_data.get("playlist")
            instance.video = None

        if commit:
            # Сохраняем без вызова full_clean() чтобы обойти валидацию модели
            instance.save(
                force_insert=False,
                force_update=False,
                using=None,
                update_fields=None,
            )
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
