from django.urls import path
from django.views.generic import TemplateView

from users import views

app_name = "users"

urlpatterns = [
    # Authentication
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.CustomLogoutView.as_view(), name="logout"),
    # Registration
    path("signup/", views.SignupView.as_view(), name="signup"),
    path(
        "signup/complete/",
        views.SignupCompleteView.as_view(),
        name="signup-complete",
    ),
    path(
        "activate/<uidb64>/<token>/",
        views.ActivateUserView.as_view(),
        name="activate",
    ),
    path(
        "resend-activation/",
        views.ResendActivationView.as_view(),
        name="resend-activation",
    ),
    # Profile
    path("profile/", views.ProfileView.as_view(), name="profile"),
    # Password Change
    path(
        "password-change/",
        views.CustomPasswordChangeView.as_view(),
        name="password-change",
    ),
    path(
        "password-change/done/",
        views.CustomPasswordChangeDoneView.as_view(),
        name="password-change-done",
    ),
    # Password Reset
    path(
        "password-reset/",
        views.CustomPasswordResetView.as_view(),
        name="password-reset",
    ),
    path(
        "password-reset/done/",
        views.CustomPasswordResetDoneView.as_view(),
        name="password-reset-done",
    ),
    path(
        "password-reset/<uidb64>/<token>/",
        views.CustomPasswordResetConfirmView.as_view(),
        name="password-reset-confirm",
    ),
    path(
        "password-reset/complete/",
        views.CustomPasswordResetCompleteView.as_view(),
        name="password-reset-complete",
    ),
    # Terms and Conditions
    path(
        "terms/",
        TemplateView.as_view(
            template_name="users/terms.html",
            extra_context={"current_date": "2026-01-04"},
        ),
        name="terms",
    ),
]
