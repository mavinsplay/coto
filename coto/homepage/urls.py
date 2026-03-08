from django.urls import path

from homepage.views import HomeView, LoveView

app_name = "homepage"

urlpatterns = [
    path("", HomeView.as_view(), name="homepage"),
    path("love/", LoveView.as_view(), name="homepage"),
]
