# Generated by Django 4.2 on 2023-08-21 04:51

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("integration", "0001_initial"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="integration",
            name="tag",
        ),
    ]
