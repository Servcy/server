import json

import requests
from django.conf import settings

from common.exceptions import ServcyOauthCodeException
from integration.models import UserIntegration
from integration.repository import IntegrationRepository
from project.repository import ProjectRepository

from .base import BaseService


class AtlassianService(BaseService):
    _atlassian_redirect_uri = settings.ATLASSIAN_APP_REDIRECT_URI
    _atlassian_client_id = settings.ATLASSIAN_APP_CLIENT_ID
    _atlassian_app_id = settings.ATLASSIAN_APP_ID
    _atlassian_app_secret = settings.ATLASSIAN_APP_CLIENT_SECRET
    _atlassian_api_url = "https://api.atlassian.com"
    _atlassian_auth_url = "https://auth.atlassian.com"

    def __init__(self, **kwargs) -> None:
        self._token = (
            self._fetch_token(kwargs.get("code"))
            if kwargs.get("code")
            else kwargs.get("token")
        )
        self._user_info = self._fetch_user_info()
        self.user_integration = None

    def _fetch_token(self, code: str):
        """
        Fetches token from Atlassian.
        """
        data = {
            "grant_type": "authorization_code",
            "client_id": self._atlassian_client_id,
            "client_secret": self._atlassian_app_secret,
            "code": code,
            "redirect_uri": self._atlassian_redirect_uri,
        }
        token_info = requests.post(f"{self._atlassian_auth_url}/oauth/token", data=data)
        if token_info.status_code != 200:
            raise ServcyOauthCodeException(
                f"An error occurred while obtaining token from Atlassian.\n{str(token_info.json())}"
            )
        return token_info.json()

    def _fetch_user_info(self) -> dict:
        """
        Fetches user info from Atlassian.
        """
        user_info = requests.get(
            f"{self._atlassian_api_url}/me",
            headers={"Authorization": f"Bearer {self._token['access_token']}"},
        )
        if user_info.status_code != 200:
            raise ServcyOauthCodeException(
                f"An error occurred while obtaining user info from Atlassian.\n{str(user_info.json())}"
            )
        return user_info.json()

    def is_active(self, meta_data: dict, **kwargs) -> bool:
        """
        Checks if integration is active.
        """
        self._token = meta_data["token"]
        self._fetch_user_info()
        return True

    def send_reply(
        meta_data: dict,
        user_integration: UserIntegration,
        body: str,
        reply: str,
        is_body_html: bool,
        **kwargs,
    ):
        """
        Send reply to user.
        """
        pass

    def create_integration(self, user_id: int) -> UserIntegration:
        """
        Create integration for user.
        """
        self.user_integration = IntegrationRepository.create_user_integration(
            integration_id=IntegrationRepository.get_integration(
                filters={"name": "Atlassian"}
            ).id,
            user_id=user_id,
            meta_data={"token": self._token, "user_info": self._user_info},
            account_id=self._user_info["account_id"],
            account_display_name=self._user_info["email"],
        )
        self._create_webhook(self._user_info["id"])
        return self.user_integration
