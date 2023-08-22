# Generated by Django 4.2 on 2023-08-21 03:54

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("integration", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserInbox",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("title", models.CharField(max_length=255)),
                ("body", models.TextField(default=None, null=True)),
                ("is_archived", models.BooleanField(default=False)),
                ("is_deleted", models.BooleanField(default=False)),
                (
                    "user_integration",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="user_inboxes",
                        to="integration.userintegration",
                    ),
                ),
            ],
            options={
                "verbose_name": "User Inbox",
                "db_table": "user_inbox",
            },
        ),
        migrations.CreateModel(
            name="GoogleMail",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("message_id", models.CharField(max_length=255, unique=True)),
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