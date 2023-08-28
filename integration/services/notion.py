import requests
from django.conf import settings

from common.exceptions import ServcyOauthCodeException
from integration.repository import IntegrationRepository


class NotionService:
    def __init__(self, code: str = None) -> None:
        """Initializes NotionService."""
        self._token = None
        if code:
            self._fetch_token(code)

    def _fetch_token(self, code: str) -> dict:
        """Fetches access token from Notion."""
        self._token = requests.post(
            url="https://api.notion.com/v1/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.NOTION_APP_REDIRECT_URI,
            },
            auth={
                "client_id": settings.NOTION_APP_CLIENT_ID,
                "client_secret": settings.NOTION_APP_CLIENT_SECRET,
            },
            headers={"Accept": "application/json"},
        ).json()
        if "error" == self._token["object"] or "error" in self._token:
            raise ServcyOauthCodeException(
                f"An error occurred while obtaining access token from Notion.\n{str(self._token)}"
            )

    def create_integration(self, user_id: int) -> None:
        """Creates integration for user."""
        IntegrationRepository.create_user_integration(
            integration_id=IntegrationRepository.get_integration(
                filters={"name": "Notion"}
            ).id,
            user_id=user_id,
            account_id=self._token["workspace_id"],
            meta_data={"token": self._token},
        )
