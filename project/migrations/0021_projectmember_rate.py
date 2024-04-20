# Generated by Django 4.2.10 on 2024-04-20 03:28

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("project", "0020_project_budget"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectmember",
            name="rate",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="project_members",
                to="project.projectmemberrate",
            ),
        ),
    ]
