# Generated by Django 4.2.10 on 2024-04-17 08:55

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0003_subscriptionwebhookevent"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionwebhookevent",
            name="event_body",
            field=models.JSONField(default=dict),
        ),
    ]
