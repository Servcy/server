# Generated by Django 4.2.10 on 2024-04-24 17:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0001_initial_squashed_0010_remove_loginotp_is_verified"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspacemember",
            name="auto_approve_tracked_time",
            field=models.BooleanField(default=True),
        ),
    ]
