# Generated by Django 4.2.11 on 2024-05-22 14:44

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0012_user_utm_campaign_user_utm_medium_user_utm_source"),
        ("billing", "0006_remove_subscriptionwebhookevent_event_body"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="customer_details",
            field=models.JSONField(default=dict),
        ),
        migrations.AlterField(
            model_name="subscription",
            name="workspace",
            field=models.ForeignKey(
                default=None,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscriptions",
                to="iam.workspace",
            ),
        ),
    ]
