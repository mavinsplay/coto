from django.forms.widgets import ClearableFileInput
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe


__all__ = ["ChunkedAdminFileWidget"]


class ChunkedAdminFileWidget(ClearableFileInput):
    template_name = "admin/upload/chunked_file_widget.html"

    class Media:
        js = ("upload/js/chunked_admin.js",)
        css = {
            "all": ("upload/css/chunked_admin.css",),
        }

    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        ctx["widget"]["chunk_start_url"] = "/chunked-upload/start/"
        ctx["widget"]["chunk_complete_url"] = "/chunked-upload/complete/"
        ctx["widget"]["name"] = name
        return ctx

    def render(self, name, value, attrs=None, renderer=None):
        ctx = self.get_context(name, value, attrs)
        return mark_safe(render_to_string(self.template_name, ctx))

    def value_from_datadict(self, data, files, name):
        upload_id_key = f"{name}_upload_id"
        upload_id = data.get(upload_id_key)

        if upload_id:
            return None

        return super().value_from_datadict(data, files, name)
