import re

from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserChangeForm,
    UserCreationForm,
)
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from users.models import Profile

__all__ = ()


class BootstrapFormMixin:
    """Mixin to apply Bootstrap 5 styling to form fields"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            # Add Bootstrap classes
            existing_classes = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = (
                f"{existing_classes} form-control".strip()
            )

            # Add placeholder if label exists
            if field.label:
                field.widget.attrs["placeholder"] = field.label

            # Add aria-label for accessibility
            field.widget.attrs["aria-label"] = field.label or field_name


class TurnstileField(forms.CharField):
    """Cloudflare Turnstile CAPTCHA field"""

    def __init__(self, *args, **kwargs):
        kwargs["required"] = True
        kwargs["widget"] = forms.HiddenInput(
            attrs={
                "class": "cf-turnstile",
                "data-sitekey": "{{ TURNSTILE_SITE_KEY }}",
            },
        )
        super().__init__(*args, **kwargs)


class CustomAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    """Enhanced login form with better validation"""

    username = forms.CharField(
        label=_("Username or Email"),
        max_length=254,
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
            },
        ),
    )

    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
            },
        ),
    )

    remember_me = forms.BooleanField(
        label=_("Remember me"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class SignUpForm(BootstrapFormMixin, UserCreationForm):
    """Enhanced registration form with email verification and captcha"""

    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        required=True,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
            },
        ),
        help_text=_("Required. Enter a valid email address."),
    )

    username = forms.CharField(
        label=_("Username"),
        max_length=150,
        required=True,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
            },
        ),
        help_text=_(
            "Required. 150 characters or fewer. Lett\
                ers, digits and @/./+/-/_ only.",
        ),
    )

    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            },
        ),
        help_text=_(
            "Your password must contain at least 8\
                characters and cannot be entirely numeric.",
        ),
    )

    password2 = forms.CharField(
        label=_("Password confirmation"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            },
        ),
        strip=False,
        help_text=_("Enter the same password as before, for verification."),
    )

    terms_accepted = forms.BooleanField(
        label=_("I accept the terms and conditions"),
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        error_messages={
            "required": _(
                "You must accept the terms and conditions to register.",
            ),
        },
    )

    # Turnstile captcha field (optional, enabled via settings)
    turnstile_token = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def clean_email(self):
        """Validate email uniqueness and format"""
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower().strip()
            if User.objects.filter(email=email).exists():
                raise ValidationError(
                    _("A user with this email already exists."),
                    code="email_exists",
                )

        return email

    def clean_username(self):
        """Validate username format and uniqueness"""
        username = self.cleaned_data.get("username")
        if username:
            # Check for valid characters
            if not re.match(r"^[\w.@+-]+$", username):
                raise ValidationError(
                    _(
                        "Username can only contain letters, n\
                            umbers, and @/./+/-/_ characters.",
                    ),
                    code="invalid_username",
                )
            # Check uniqueness (case-insensitive)
            if User.objects.filter(username__iexact=username).exists():
                raise ValidationError(
                    _("A user with this username already exists."),
                    code="username_exists",
                )

        return username

    def clean_password2(self):
        """Validate password confirmation"""
        password1 = self.cleaned_data.get("password1")
        password2 = self.cleaned_data.get("password2")

        if password1 and password2:
            if password1 != password2:
                raise ValidationError(
                    _("The two password fields didn't match."),
                    code="password_mismatch",
                )

        return password2


class CustomUserChangeForm(BootstrapFormMixin, UserChangeForm):
    """Enhanced user profile edit form"""

    password = None  # Remove password field from edit form

    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        required=False,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
            },
        ),
    )

    first_name = forms.CharField(
        label=_("First name"),
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "given-name",
            },
        ),
    )

    last_name = forms.CharField(
        label=_("Last name"),
        max_length=150,
        required=False,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "family-name",
            },
        ),
    )

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name")

    def clean_email(self):
        """Validate email uniqueness (exclude current user)"""
        email = self.cleaned_data.get("email")
        if email:
            email = email.lower().strip()
            users_with_email = User.objects.filter(email=email).exclude(
                pk=self.instance.pk,
            )
            if users_with_email.exists():
                raise ValidationError(
                    _("A user with this email already exists."),
                    code="email_exists",
                )

        return email


class UserProfileForm(BootstrapFormMixin, forms.ModelForm):
    """User profile image upload form"""

    image = forms.ImageField(
        label=_("Profile Picture"),
        required=False,
        widget=forms.FileInput(
            attrs={
                "accept": "image/png,image/jpeg,image/jpg",
                "class": "form-control",
            },
        ),
        help_text=_(
            "Upload a profile picture. Allowed formats: PNG, J\
                PEG, JPG. Max size: 50MB.",
        ),
    )

    class Meta:
        model = Profile
        fields = ("image",)

    def clean_image(self):
        """Validate image file"""
        image = self.cleaned_data.get("image")
        if image:
            # Validate file size (50MB)
            if image.size > 50 * 1024 * 1024:
                raise ValidationError(
                    _("Image file too large. Maximum size is 50MB."),
                    code="file_too_large",
                )
            # Validate file extension
            valid_extensions = ["png", "jpg", "jpeg"]
            ext = image.name.split(".")[-1].lower()
            if ext not in valid_extensions:
                raise ValidationError(
                    _("Invalid file extension. Allowed: PNG, JPEG, JPG."),
                    code="invalid_extension",
                )

        return image


class CustomPasswordResetForm(BootstrapFormMixin, PasswordResetForm):
    """Enhanced password reset form"""

    email = forms.EmailField(
        label=_("Email"),
        max_length=254,
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
            },
        ),
    )


class CustomPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    """Enhanced password change form"""

    old_password = forms.CharField(
        label=_("Current password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "autofocus": True,
            },
        ),
    )

    new_password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            },
        ),
        help_text=_(
            "Your password must contain at least 8 characters and canno\
                t be entirely numeric.",
        ),
    )

    new_password2 = forms.CharField(
        label=_("Confirm new password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            },
        ),
    )


class CustomSetPasswordForm(BootstrapFormMixin, SetPasswordForm):
    """Enhanced set password form for password reset confirmation"""

    new_password1 = forms.CharField(
        label=_("New password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "autofocus": True,
            },
        ),
        help_text=_(
            "Your password must contain at least 8 characters and\
                cannot be entirely numeric.",
        ),
    )

    new_password2 = forms.CharField(
        label=_("Confirm new password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
            },
        ),
    )
