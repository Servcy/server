import json
import logging

from rest_framework import status
from rest_framework.decorators import action
from rest_framework.viewsets import ViewSet

from common.responses import error_response, success_response
from inbox.services import InboxService

logger = logging.getLogger(__name__)


class InboxViewSet(ViewSet):
    @action(detail=False, methods=["get"], url_path="items")
    def fetch_items(self, request):
        try:
            user_id = request.user.id
            user = request.user
            inbox_service = InboxService(user=user, user_id=user_id)
            table_settings = request.data.get("pagination", {})
            items, details = inbox_service.get_paginated_items(
                filters=request.data.get("filters", {}),
                search=request.data.get("search", {}),
                sort_by=table_settings.get("sort_by", []),
                sort_desc=table_settings.get("sort_desc", []),
                page=table_settings.get("page", 1),
                page_size=table_settings.get("page_size", 10),
            )
            return success_response(
                results={
                    "items": items,
                    "details": details,
                },
                success_message="Inbox fetched successfully",
                status=status.HTTP_200_OK,
            )
        except Exception as err:
            return error_response(
                logger=logger,
                logger_message="Error while fetching inbox",
            )
