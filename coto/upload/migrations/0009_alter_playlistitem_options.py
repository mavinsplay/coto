# Generated manually

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('upload', '0008_alter_video_hls_status'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='playlistitem',
            options={
                'ordering': ['order', 'season_number', 'episode_number'],
                'verbose_name': 'Эпизод плейлиста',
                'verbose_name_plural': 'Эпизоды плейлиста'
            },
        ),
    ]
