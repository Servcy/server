# Generated by Django 4.2.9 on 2024-03-09 13:07

import common.file_field
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Document",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=100)),
                (
                    "file",
                    models.FileField(
                        default=None,
                        null=True,
                        upload_to=common.file_field.upload_path,
                        validators=[common.file_field.file_size_validator],
                    ),
                ),
                ("link", models.URLField(default=None, null=True)),
                ("meta_data", models.JSONField(default=dict)),
            ],
            options={
                "verbose_name": "Document",
                "verbose_name_plural": "Documents",
                "db_table": "document",
            },
        ),
    ]
