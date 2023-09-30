from django.db import models

from app.models import TimeStampedModel
from iam.models import User
from integration.models import UserIntegration


class Inbox(TimeStampedModel):
    uid = models.CharField(max_length=255, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    body = models.TextField(null=True, blank=False, default=None)
    is_archived = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    cause = models.CharField(max_length=10000, null=True, blank=False, default=None)
    is_body_html = models.BooleanField(default=False)
    user_integration = models.ForeignKey(
        UserIntegration, on_delete=models.CASCADE, related_name="inbox_items"
    )
    category = models.CharField(max_length=255, null=True, blank=False, default=None)

    class Meta:
        db_table = "inbox"
        verbose_name = "Inbox"
