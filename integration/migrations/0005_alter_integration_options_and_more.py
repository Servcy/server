# Generated by Django 4.2 on 2023-08-20 02:27

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("integration", "0004_alter_integrationuser_integration"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="integration",
            options={
                "verbose_name": "Integration",
                "verbose_name_plural": "Integrations",
            },
        ),
        migrations.AlterModelOptions(
            name="integrationuser",
            options={
                "verbose_name": "Integration User",
                "verbose_name_plural": "Integration Users",
            },
        ),
    ]
