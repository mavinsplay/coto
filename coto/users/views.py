import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.views import (
    LoginView,
    LogoutView,
    PasswordChangeView,
    PasswordResetCompleteView,
    PasswordResetConfirmView,
    PasswordResetDoneView,
    PasswordResetView,
)
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.generic import FormView, TemplateView

import users.forms
from users.models import Profile, UserManager

__all__ = ()
logger = logging.getLogger(__name__)


class CustomLoginView(LoginView):

    template_name = "users/login.html"
    form_class = users.forms.CustomAuthenticationForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        """Handle successful login with remember me functionality"""
        remember_me = form.cleaned_data.get("remember_me", False)

        if not remember_me:
            # Session expires when browser closes
            self.request.session.set_expiry(0)
            self.request.session.modified = True
        else:
            # Session expires after 2 weeks
            self.request.session.set_expiry(1209600)

        # Update last active date
        user = form.get_user()
        if hasattr(user, "profile"):
            user.profile.date_last_active = timezone.now()
            user.profile.attempts_count = 0  # Reset failed attempts
            user.profile.save(
                update_fields=["date_last_active", "attempts_count"],
            )

        messages.success(
            self.request,
            _("Welcome back, %(username)s!") % {"username": user.username},
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        """Handle failed login attempts"""
        username = form.data.get("username")

        # Track failed login attempts
        if username:
            try:
                user = User.objects.get(username=username)
                if hasattr(user, "profile"):
                    user.profile.attempts_count += 1
                    user.profile.save(update_fields=["attempts_count"])

                    # Warn user about multiple failed attempts
                    if user.profile.attempts_count >= 5:
                        messages.warning(
                            self.request,
                            _(
                                "Multiple failed login attempts detected. Pl\
                                    ease ensure you are using the corr\
                                        ect credentials.",
                            ),
                        )
            except User.DoesNotExist:
                pass

        messages.error(
            self.request,
            _("Invalid username or password. Please try again."),
        )
        return super().form_invalid(form)


class ActivateUserView(View):
    """Handle email activation links"""

    def get(self, request, uidb64, token):
        """Activate user account via email link"""
        try:
            # Decode user ID
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None

        # Verify token and activate user
        if user is not None and default_token_generator.check_token(
            user,
            token,
        ):
            if not user.is_active:  # noqa
                user.is_active = True
                user.save()

                # Update profile
                if hasattr(user, "profile"):
                    user.profile.date_last_active = timezone.now()
                    user.profile.save(update_fields=["date_last_active"])

                messages.success(
                    request,
                    _(
                        "Your account has been successfully a\
                            ctivated! You can no\
                            w log in.",
                    ),
                )
                login(
                    request,
                    user,
                    backend="django.contrib.auth.backends.ModelBackend",
                )
                return redirect(reverse("homepage:homepage"))
            else:
                messages.info(request, _("Your account is already activated."))
                return redirect(reverse("users:login"))
        else:
            messages.error(
                request,
                _(
                    "The activation link is invalid or has expired. Please r\
                        equest a new one.",
                ),
            )
            return redirect(reverse("users:resend-activation"))


class ResendActivationView(FormView):
    """Allow users to resend activation email"""

    template_name = "users/resend_activation.html"
    form_class = users.forms.CustomPasswordResetForm  # Reuse email form
    success_url = reverse_lazy("users:login")

    def form_valid(self, form):
        """Send activation email to user"""
        email = form.cleaned_data["email"]

        try:
            user = User.objects.get(email__iexact=email, is_active=False)
            self.send_activation_email(user)
            messages.success(
                self.request,
                _("Activation link has been sent to your email address."),
            )
        except User.DoesNotExist:
            # Don't reveal if user exists or not
            messages.success(
                self.request,
                _(
                    "If an inactive account exists with this email, an act\
                        ivation link has been sent.",
                ),
            )

        return super().form_valid(form)

    def send_activation_email(self, user):
        """Send activation email with token"""
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        activation_link = self.request.build_absolute_uri(
            reverse("users:activate", kwargs={"uidb64": uid, "token": token}),
        )

        context = {
            "user": user,
            "activation_link": activation_link,
            "site_name": getattr(settings, "SITE_NAME", "Coto"),
            "protocol": "https" if self.request.is_secure() else "http",
        }

        # Render email templates
        html_message = render_to_string(
            "users/emails/activation_email.html",
            context,
        )
        text_message = strip_tags(html_message)

        # Send email
        email = EmailMultiAlternatives(
            subject=_("Activate your %(site_name)s account")
            % {"site_name": context["site_name"]},
            body=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_message, "text/html")
        email.send(fail_silently=False)


class SignupView(FormView):
    """Enhanced user registration with email verification"""

    template_name = "users/signup.html"
    form_class = users.forms.SignUpForm
    success_url = reverse_lazy("users:signup-complete")

    def get_context_data(self, **kwargs):
        """Add Turnstile settings to context"""
        context = super().get_context_data(**kwargs)
        context["turnstile_site_key"] = getattr(
            settings,
            "TURNSTILE_SITE_KEY",
            "",
        )
        context["turnstile_enabled"] = getattr(
            settings,
            "TURNSTILE_ENABLED",
            False,
        )
        return context

    def form_valid(self, form):
        """Create user and send activation email"""
        # Validate Turnstile if enabled
        turnstile_enabled = getattr(settings, "TURNSTILE_ENABLED", False)
        logger.info(f"Turnstile enabled: {turnstile_enabled}")

        if turnstile_enabled:
            turnstile_token = form.cleaned_data.get("turnstile_token")
            logger.info(
                f'Turnstile token from form: {turnstile_token[:20] if turnstile_token else "None"}...',  # noqa
            )

            if not self.verify_turnstile(turnstile_token):
                logger.warning(
                    "Registration blocked: Turnstile verification failed",
                )
                messages.error(
                    self.request,
                    _(
                        "Проверка капчи не удалась. Пожалуйста, попробуй\
                            те снова.",
                    ),
                )
                return self.form_invalid(form)

            logger.info(
                "Turnstile verification passed, proceeding with registration",
            )

        # Create user
        user = form.save(commit=False)
        user.email = UserManager().normalize_email(form.cleaned_data["email"])
        user.is_active = getattr(settings, "DEFAULT_USER_IS_ACTIVE", False)
        user.save()

        # Create profile
        Profile.objects.get_or_create(user=user)

        # Send activation email if user is not auto-activated
        if not user.is_active:
            self.send_activation_email(user)
            messages.success(
                self.request,
                _(
                    "Registration successful! Please check your email to a\
                        ctivate your account.",
                ),
            )
        else:
            messages.success(
                self.request,
                _(
                    "Registration successful! Y\
                    ou can now log in.",
                ),
            )
            login(
                self.request,
                user,
                backend="django.contrib.auth.backends.ModelBackend",
            )
            return redirect("homepage:homepage")

        return super().form_valid(form)

    def verify_turnstile(self, token):
        """Verify Cloudflare Turnstile token"""
        import requests

        secret_key = getattr(settings, "TURNSTILE_SECRET_KEY", "")
        site_key = getattr(settings, "TURNSTILE_SITE_KEY", "")

        logger.info("Turnstile verification started")
        logger.info(f"Site Key: {site_key[:10]}... (length: {len(site_key)})")
        logger.info(f"Secret Key exists: {bool(secret_key)}")
        logger.info(f"Token received: {bool(token)}")

        if not secret_key or not token:
            logger.warning(
                "Turnstile verification failed: Missing secret_key or token",
            )
            return False

        client_ip = self.get_client_ip()
        logger.info(f"Client IP: {client_ip}")

        try:
            verify_data = {
                "secret": secret_key,
                "response": token,
                "remoteip": client_ip,
            }

            logger.info("Sending verification request to Cloudflare...")
            response = requests.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data=verify_data,
                timeout=10,
            )

            result = response.json()
            logger.info(f"Turnstile response: {result}")

            if result.get("success"):  # noqa
                logger.info("✓ Turnstile verification successful!")
                return True
            else:
                logger.warning(
                    f'✗ Turnstile verification failed: {result.get("error-codes", [])}',  # noqa
                )
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Turnstile network error: {e}")
            return False
        except Exception as e:
            logger.error(f"Turnstile verification error: {e}")
            return False

    def get_client_ip(self):
        """Get client IP address"""
        x_forwarded_for = self.request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            ip = x_forwarded_for.split(",")[0]
        else:
            ip = self.request.META.get("REMOTE_ADDR")

        return ip  # noqa

    def send_activation_email(self, user):
        """Send activation email with secure token"""
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        activation_link = self.request.build_absolute_uri(
            reverse("users:activate", kwargs={"uidb64": uid, "token": token}),
        )

        context = {
            "user": user,
            "activation_link": activation_link,
            "site_name": getattr(settings, "SITE_NAME", "Coto"),
            "protocol": "https" if self.request.is_secure() else "http",
        }

        # Render email templates
        html_message = render_to_string(
            "users/emails/activation_email.html",
            context,
        )
        text_message = strip_tags(html_message)

        try:
            # Send email
            email = EmailMultiAlternatives(
                subject=_("Activate your %(site_name)s account")
                % {"site_name": context["site_name"]},
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            email.attach_alternative(html_message, "text/html")
            email.send(fail_silently=False)
        except Exception as e:
            logger.error(
                f"Failed to send activation email to {user.email}: {e}",
            )
            messages.warning(
                self.request,
                _(
                    "Registration successful, but we could not send the activa\
                        tion email. Please contact support.",
                ),
            )


class SignupCompleteView(TemplateView):
    """Show signup completion message"""

    template_name = "users/signup_complete.html"


class ProfileView(LoginRequiredMixin, View):
    """User profile view and edit"""

    def get(self, request):
        """Display profile edit form"""
        # Ensure profile exists
        profile, created = Profile.objects.get_or_create(user=request.user)

        form = users.forms.CustomUserChangeForm(instance=request.user)
        profile_form = users.forms.UserProfileForm(instance=profile)

        return render(
            request,
            "users/profile.html",
            {
                "form": form,
                "profile_form": profile_form,
                "user": request.user,
            },
        )

    def post(self, request):
        """Handle profile update"""
        # Ensure profile exists
        profile, created = Profile.objects.get_or_create(user=request.user)

        form = users.forms.CustomUserChangeForm(
            request.POST,
            instance=request.user,
        )
        profile_form = users.forms.UserProfileForm(
            request.POST,
            request.FILES,
            instance=profile,
        )

        if form.is_valid() and profile_form.is_valid():  # noqa
            # Save user data
            user = form.save(commit=False)
            if form.cleaned_data.get("email"):
                user.email = UserManager().normalize_email(
                    form.cleaned_data["email"],
                )

            user.save()

            # Save profile data
            profile_form.save()

            messages.success(
                request,
                _("Your profile has been updated successfully!"),
            )
            return redirect("users:profile")
        else:
            # Show errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

            for field, errors in profile_form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")

        return render(
            request,
            "users/profile.html",
            {
                "form": form,
                "profile_form": profile_form,
                "user": request.user,
            },
        )


# Custom password reset views with better templates and error handling
class CustomPasswordResetView(PasswordResetView):
    """Enhanced password reset view"""

    template_name = "users/password_reset.html"
    email_template_name = "users/emails/password_reset_email.html"
    html_email_template_name = "users/emails/password_reset_email.html"
    subject_template_name = "users/emails/password_reset_subject.txt"
    form_class = users.forms.CustomPasswordResetForm
    success_url = reverse_lazy("users:password-reset-done")

    def form_valid(self, form):
        """Send password reset email"""
        messages.success(
            self.request,
            _(
                "Password reset instructions have been sent to \
                    your email address.",
            ),
        )
        return super().form_valid(form)


class CustomPasswordResetDoneView(PasswordResetDoneView):
    """Password reset email sent confirmation"""

    template_name = "users/password_reset_done.html"


class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    """Confirm password reset with token"""

    template_name = "users/password_reset_confirm.html"
    form_class = users.forms.CustomSetPasswordForm
    success_url = reverse_lazy("users:password-reset-complete")

    def form_valid(self, form):
        """Handle successful password reset"""
        messages.success(
            self.request,
            _(
                "Your password has been reset suc\
                    cessfully! You can now log in wit\
                    h your new password.",
            ),
        )
        return super().form_valid(form)


class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    """Password reset complete confirmation"""

    template_name = "users/password_reset_complete.html"


class CustomPasswordChangeView(PasswordChangeView):
    """Enhanced password change view"""

    template_name = "users/password_change.html"
    form_class = users.forms.CustomPasswordChangeForm
    success_url = reverse_lazy("users:password-change-done")

    def form_valid(self, form):
        """Handle successful password change"""
        messages.success(
            self.request,
            _("Your password has been changed successfully!"),
        )
        return super().form_valid(form)


class CustomPasswordChangeDoneView(TemplateView):
    """Password change complete confirmation"""

    template_name = "users/password_change_done.html"


class CustomLogoutView(LogoutView):
    """Enhanced logout view"""

    template_name = "users/logout.html"

    def dispatch(self, request, *args, **kwargs):
        """Show goodbye message"""
        if request.user.is_authenticated:
            messages.info(request, _("You have been successfully logged out."))

        return super().dispatch(request, *args, **kwargs)
