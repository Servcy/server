# Generated by Django 4.2.9 on 2024-02-14 09:41

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("inbox", "0012_blockedemail"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="blockedemail",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="blockedemail",
            name="user",
            field=models.ForeignKey(
                default=0,
                on_delete=django.db.models.deletion.CASCADE,
                to=settings.AUTH_USER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.AlterUniqueTogether(
            name="blockedemail",
            unique_together={("email", "user")},
        ),
        migrations.RemoveField(
            model_name="blockedemail",
            name="user_integration",
        ),
    ]
