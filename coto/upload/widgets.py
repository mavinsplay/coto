from django.forms.widgets import ClearableFileInput

__all__ = ["ChunkedAdminFileWidget"]


class ChunkedAdminFileWidget(ClearableFileInput):
    template_name = "admin/upload/chunked_file_widget.html"
    
    def get_context(self, name, value, attrs):
        ctx = super().get_context(name, value, attrs)
        # Добавляем hidden input для chunked_path
        ctx['widget'].update({
            'chunked_input': True,
        })
        return ctx
