from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import DeleteView, DetailView, ListView, UpdateView

from upload.models import Video


__all__ = []


class MyVideosListView(LoginRequiredMixin, ListView):
    """Список видео текущего пользователя с поиском и фильтрацией."""

    model = Video
    template_name = "videos/video_list.html"
    context_object_name = "videos"
    paginate_by = 12

    def get_queryset(self):
        queryset = Video.objects.filter(
            uploaded_by=self.request.user,
        ).select_related("uploaded_by")

        # Поиск по названию и описанию
        search_query = self.request.GET.get("q", "").strip()
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query)
                | Q(description__icontains=search_query),
            )

        # Фильтрация по статусу HLS
        status_filter = self.request.GET.get("status", "").strip()
        if status_filter:
            queryset = queryset.filter(hls_status=status_filter)

        # Сортировка
        sort_by = self.request.GET.get("sort", "-created_at")
        allowed_sorts = [
            "created_at",
            "-created_at",
            "title",
            "-title",
            "hls_progress",
            "-hls_progress",
        ]
        if sort_by in allowed_sorts:
            queryset = queryset.order_by(sort_by)

        return queryset  # noqa

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["search_query"] = self.request.GET.get("q", "")
        context["status_filter"] = self.request.GET.get("status", "")
        context["sort_by"] = self.request.GET.get("sort", "-created_at")

        # Статистика
        total_videos = Video.objects.filter(
            uploaded_by=self.request.user,
        ).count()
        context["total_videos"] = total_videos

        # Статусы для фильтра
        context["available_statuses"] = [
            ("awaiting processing", "Ожидает обработки"),
            ("pending", "В очереди"),
            ("transcode", "Обрабатывается"),
            ("done", "Завершено"),
            ("error", "Ошибка"),
        ]

        return context


class VideoDetailView(LoginRequiredMixin, UserPassesTestMixin, DetailView):
    """Детальная информация о видео."""

    model = Video
    template_name = "videos/video_detail.html"
    context_object_name = "video"

    def test_func(self):
        video = self.get_object()
        return video.uploaded_by == self.request.user

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        video = self.get_object()

        # Форматирование размера файла
        if video.file_size:
            size_mb = video.file_size / (1024 * 1024)
            if size_mb >= 1024:
                context["file_size_display"] = f"{size_mb / 1024:.2f} GB"
            else:
                context["file_size_display"] = f"{size_mb:.2f} MB"
        else:
            context["file_size_display"] = "Неизвестно"

        return context


class VideoUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    """Редактирование информации о видео."""

    model = Video
    template_name = "videos/video_edit.html"
    fields = ["title", "description", "thumbnail"]

    def test_func(self):
        video = self.get_object()
        return video.uploaded_by == self.request.user

    def get_success_url(self):
        return reverse_lazy("videos:detail", kwargs={"pk": self.object.pk})


class VideoDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    """Удаление видео."""

    model = Video
    template_name = "videos/video_confirm_delete.html"
    success_url = reverse_lazy("videos:list")

    def test_func(self):
        video = self.get_object()
        return video.uploaded_by == self.request.user
