# Generated by Django 4.2 on 2023-08-23 06:31

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("integration", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutlookMail",
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
                (
                    "message_id",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                ("categories", models.JSONField()),
                ("payload", models.JSONField()),
                (
                    "user_integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outlook_mails",
                        to="integration.userintegration",
                    ),
                ),
            ],
            options={
                "verbose_name": "Outlook Mail",
                "verbose_name_plural": "Outlook Mails",
                "db_table": "outlook_mail",
            },
        ),
        migrations.CreateModel(
            name="InboxItem",
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
                ("uid", models.CharField(db_index=True, max_length=255, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField(default=None, null=True)),
                ("is_archived", models.BooleanField(default=False)),
                ("is_deleted", models.BooleanField(default=False)),
                ("cause", models.CharField(default=None, max_length=255, null=True)),
                ("is_body_html", models.BooleanField(default=False)),
                (
                    "user_integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inbox_items",
                        to="integration.userintegration",
                    ),
                ),
            ],
            options={
                "verbose_name": "Inbox Item",
                "verbose_name_plural": "Inbox Items",
                "db_table": "inbox_item",
            },
        ),
        migrations.CreateModel(
            name="GoogleMail",
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
                (
                    "message_id",
                    models.CharField(db_index=True, max_length=255, unique=True),
                ),
                ("thread_id", models.CharField(max_length=255)),
                ("history_id", models.CharField(max_length=255)),
                ("snippet", models.TextField()),
                ("size_estimate", models.IntegerField()),
                ("payload", models.JSONField()),
                ("label_ids", models.JSONField()),
                ("internal_date", models.DateTimeField()),
                (
                    "user_integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="google_mails",
                        to="integration.userintegration",
                    ),
                ),
            ],
            options={
                "verbose_name": "Google Mail",
                "verbose_name_plural": "Google Mails",
                "db_table": "google_mail",
            },
        ),
    ]
