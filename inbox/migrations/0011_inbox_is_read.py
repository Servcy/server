# Generated by Django 4.2.9 on 2024-02-14 02:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inbox", "0010_alter_inbox_uid_alter_inbox_unique_together"),
    ]

    operations = [
        migrations.AddField(
            model_name="inbox",
            name="is_read",
            field=models.BooleanField(default=False),
        ),
    ]
