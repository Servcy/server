# Generated by Django 4.2 on 2023-08-21 05:56

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inbox", "0003_rename_UserInbox_to_InboxItem"),
    ]

    operations = [
        migrations.AddField(
            model_name="inboxitem",
            name="cause",
            field=models.CharField(default=None, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name="inboxitem",
            name="is_body_html",
            field=models.BooleanField(default=False),
        ),
    ]