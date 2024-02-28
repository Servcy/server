import json
import logging
import traceback
from base64 import decodebytes

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from common.exceptions import (
    ExternalAPIRateLimitException,
    IntegrationAccessRevokedException,
)
from inbox.repository import InboxRepository
from inbox.repository.google import GoogleMailRepository
from integration.repository import IntegrationRepository
from integration.services.google import GoogleService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def google(request):
    account_id = None
    history_id = None
    try:
        payload = json.loads(request.body.decode("utf-8"))
        encoded_data = payload["message"]["data"]
        decoded_data = json.loads(decodebytes(encoded_data.encode()).decode())
        account_id = decoded_data["emailAddress"]
        history_id = decoded_data["historyId"]
        user_integration = IntegrationRepository.get_user_integrations(
            filters={
                "account_id": account_id,
                "integration__name": "Gmail",
            },
            first=True,
        )
        if user_integration is None:
            return HttpResponse(status=200)
        IntegrationRepository.update_integraion(
            user_integration_id=user_integration["id"],
            meta_data=IntegrationRepository.encrypt_meta_data(
                {
                    **user_integration["meta_data"],
                    "last_history_id": history_id,
                }
            ),
        )
        last_history_id = int(user_integration["meta_data"].get("last_history_id", 0))
        if last_history_id == 0:
            return HttpResponse(status=200)
        service = GoogleService(
            access_token=user_integration["meta_data"]["token"]["access_token"],
            refresh_token=user_integration["meta_data"]["token"]["refresh_token"],
        )
        unread_message_ids = service.get_latest_unread_primary_inbox(last_history_id)
        if not unread_message_ids:
            return HttpResponse(status=200)
        mails = service.get_messages(
            message_ids=unread_message_ids,
        )
        inbox_items, attachments, has_attachments = GoogleMailRepository.create_mails(
            mails=mails,
            user_integration_id=user_integration["id"],
            user_integration_configuration=user_integration["configuration"],
        )
        if has_attachments:
            attachments = service.get_attachments(attachments=attachments)
        for item in inbox_items:
            item["attachments"] = attachments.get(item["uid"], [])
        InboxRepository.add_items(inbox_items)
        return HttpResponse(status=200)
    except IntegrationAccessRevokedException:
        IntegrationRepository.revoke_user_integrations(user_integration.get("id", 0))
        return HttpResponse(status=200)
    except ExternalAPIRateLimitException:
        return HttpResponse(status=200)
    except Exception:
        logger.exception(
            f"An error occurred processing webhook for google request.",
            extra={
                "payload": payload,
                "headers": request.headers,
                "account_id": account_id,
                "history_id": history_id,
                "traceback": traceback.format_exc(),
            },
        )
        return HttpResponse(status=500)
