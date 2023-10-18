# Generated by Django 4.2.4 on 2023-10-16 09:59

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integration", "0001_initial_squashed_0005_userintegration_is_revoked"),
        ("project", "0007_project_user_integration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="user_integration",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="integration.userintegration",
            ),
        ),
    ]