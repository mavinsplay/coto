# Generated migration for access_code field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        (
            "rooms",
            "0006_watchparty_playlist_alter_watchparty_is_private_and_more",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="watchparty",
            name="access_code",
            field=models.CharField(
                blank=True,
                help_text="Код для доступа к приватной комнате",
                max_length=20,
                null=True,
                verbose_name="Код доступа",
            ),
        ),
    ]
