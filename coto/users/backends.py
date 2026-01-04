"""
Custom authentication backends for enhanced security and flexibility
"""

import logging

from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.html import strip_tags
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _

import users.models

__all__ = ()
logger = logging.getLogger(__name__)


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Enhanced authentication backend that allows users to log in with either
    username or email address, with improved security and error handling.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        """
        Authenticate user by username or email with security features

        Args:
            request: HTTP request object
            username: Username or email address
            password: User password
            **kwargs: Additional keyword arguments

        Returns:
            User object if authentication successful, None otherwise
        """
        if username is None or password is None:
            return None

        try:
            # Try to find user by username or email (case-insensitive)
            if "@" in username:
                user = users.models.User.objects.by_mail(username)
            else:
                user = users.models.User.objects.get(username=username)

        except User.DoesNotExist:
            logger.warning(
                f"Failed login attempt for non-existent user: {username}",
            )
            # Run default password hasher to prevent timing attacks
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            logger.error(f"Multiple users found for identifier: {username}")
            return None

        # Ensure user has a profile
        try:
            user.profile
        except Exception:
            users.models.Profile.objects.create(user=user)

        # Check password
        if user.check_password(password):
            # Check if user is active
            if not user.is_active:
                logger.warning(f"Inactive user login attempt: {username}")
                return None

            # Reset failed attempts counter
            user.profile.attempts_count = 0
            user.profile.date_last_active = timezone.now()
            user.profile.save(
                update_fields=["attempts_count", "date_last_active"],
            )

            logger.info(f"Successful login: {user.username}")
            return user

        # Handle failed password attempt
        max_attempts = getattr(settings, "MAX_AUTH_ATTEMPTS", 10)
        user.profile.attempts_count += 1

        if user.profile.attempts_count >= max_attempts:
            # Lock account after too many failed attempts
            user.is_active = False
            user.profile.date_last_active = timezone.now()
            user.save()
            user.profile.save()

            logger.warning(
                f"Account locked due to failed attempts: {username}",
            )

            # Send account reactivation email
            self._send_reactivation_email(request, user)
        else:
            user.profile.save(update_fields=["attempts_count"])
            logger.warning(
                f"Failed login attempt for {username} "
                f"({user.profile.attempts_count}/{max_attempts})",
            )

        return None

    def _send_reactivation_email(self, request, user):
        """Send account reactivation email after account lock"""
        try:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            if request:
                activation_link = request.build_absolute_uri(
                    reverse(
                        "users:activate",
                        kwargs={"uidb64": uid, "token": token},
                    ),
                )
            else:
                activation_link = (
                    f"{settings.SITE_URL}"
                    f"{reverse('users:activate', kwargs={'uidb64': uid, 'token': token,})}"  # noqa
                )

            context = {
                "user": user,
                "activation_link": activation_link,
                "site_name": getattr(settings, "SITE_NAME", "Coto"),
                "reason": "multiple_failed_attempts",
            }

            html_message = render_to_string(
                "users/emails/activation_email.html",
                context,
            )
            text_message = strip_tags(html_message)

            email = EmailMultiAlternatives(
                subject=_("Account Locked - Reactivation Required"),
                body=text_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            email.attach_alternative(html_message, "text/html")
            email.send(fail_silently=False)

            logger.info(f"Reactivation email sent to {user.email}")
        except Exception as ex:
            logger.error(f"Failed to send reactivation email: {ex}")

    def get_user(self, user_id):
        """
        Get user by ID

        Args:
            user_id: User ID

        Returns:
            User object or None
        """
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
