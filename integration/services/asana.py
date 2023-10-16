import asana
import requests
from django.conf import settings

from common.exceptions import ServcyOauthCodeException
from integration.models import UserIntegration
from integration.repository import IntegrationRepository
from project.repository import ProjectRepository

from .base import BaseService


class AsanaService(BaseService):
    _token_uri = "https://app.asana.com/-/oauth_token"
    _api_uri = "https://app.asana.com/api/1.0"

    """Service class for Asana integration."""

    def __init__(self, user_id: int, **kwargs) -> None:
        """Initializes AsanaService."""
        self._token = None
        self.user_id = user_id
        self._user_info = None
        if kwargs.get("code"):
            self.authenticate(kwargs.get("code"))
            self._establish_webhooks()
        elif kwargs.get("refresh_token"):
            self._token = AsanaService._refresh_tokens(kwargs.get("refresh_token"))
            self._user_info = self._fetch_user_info()

    def authenticate(self, code: str) -> "AsanaService":
        """Authenticate using code."""
        self._fetch_token(code)
        self._user_info = self._fetch_user_info()
        return self

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Helper function to make requests to Asana API."""
        url = (
            f"{AsanaService._api_uri}/{endpoint}"
            if "asana.com" not in endpoint
            else endpoint
        )
        response = requests.request(method, url, **kwargs)
        json_response = response.json()
        if "error" in json_response:
            error_msg = f"An error occurred while communicating with Asana API.\n{str(json_response)}"
            raise ServcyOauthCodeException(error_msg)
        return json_response

    def _fetch_token(self, code: str) -> None:
        """Fetches access token from Asana."""
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.ASANA_APP_CLIENT_ID,
            "client_secret": settings.ASANA_APP_CLIENT_SECRET,
            "redirect_uri": settings.ASANA_APP_REDIRECT_URI,
            "code": code,
        }
        response = requests.post(AsanaService._token_uri, data=data)
        token_data = response.json()
        if "error" in token_data:
            raise ServcyOauthCodeException(
                f"An error occurred while obtaining access token from Asana.\n{str(token_data)}"
            )
        self._token = token_data

    def _fetch_user_info(self) -> dict:
        """Fetches user info from Asana."""
        return self._make_request(
            "GET",
            "users/me",
            headers={
                "Authorization": f"Bearer {self._token['access_token']}",
                "Accept": "application/json",
            },
        )

    @staticmethod
    def _refresh_tokens(refresh_token) -> None:
        """Refreshes tokens."""
        response = requests.post(
            AsanaService._token_uri,
            data={
                "grant_type": "refresh_token",
                "client_id": settings.ASANA_APP_CLIENT_ID,
                "client_secret": settings.ASANA_APP_CLIENT_SECRET,
                "refresh_token": refresh_token,
            },
        )
        token_data = response.json()
        if "error" in token_data:
            raise ServcyOauthCodeException(
                f"An error occurred while refreshing access token from Asana.\n{str(token_data)}"
            )
        return token_data

    def _establish_webhooks(self) -> None:
        """Establishes webhook for Asana."""
        client = asana.Client.access_token(self._token["access_token"])
        for workspace in self._user_info["data"]["workspaces"]:
            self.create_project_monitoring_webhook(workspace["gid"])
            projects = client.projects.get_projects_for_workspace(
                workspace["gid"], opt_pretty=True
            )
            self.create_projects(projects)
            for project in projects:
                self.create_task_monitoring_webhook(project["gid"])

    def create_integration(self, user_id: int) -> UserIntegration:
        """Creates integration for user."""
        self.user_integration = IntegrationRepository.create_user_integration(
            integration_id=IntegrationRepository.get_integration(
                filters={"name": "Asana"}
            ).id,
            user_id=user_id,
            account_id=self._user_info["data"]["gid"],
            meta_data={"token": self._token, "user_info": self._user_info},
            account_display_name=self._user_info["data"]["name"],
        )
        return self.user_integration

    def create_task_monitoring_webhook(self, project_id):
        client = asana.Client.access_token(self._token["access_token"])
        hook = client.webhooks.create_webhook(
            resource=project_id,
            target="https://server.servcy.com/webhook/asana",
            opt_pretty=True,
            filters=[
                {
                    "resource_type": "task",
                    "fields": [],
                },
                {
                    "resource_type": "attachment",
                    "action": "added",
                    "fields": [],
                },
                {
                    "resource_type": "story",
                    "fields": [],
                    "resource_subtype": "comment_added",
                },
                {
                    "resource_type": "story",
                    "fields": [],
                    "resource_subtype": "comment_changed",
                },
            ],
        )
        if "errors" in hook:
            raise ServcyOauthCodeException(
                f"An error occurred while creating task monitoring webhook for Asana.\n{str(hook)}"
            )

    def create_project_monitoring_webhook(self, workspace_id):
        client = asana.Client.access_token(self._token["access_token"])
        hook = client.webhooks.create_webhook(
            resource=workspace_id,
            target="https://server.servcy.com/webhook/asana",
            opt_pretty=True,
            filters=[
                {
                    "resource_type": "project",
                    "action": "added",
                },
            ],
        )
        if "errors" in hook:
            raise ServcyOauthCodeException(
                f"An error occurred while creating project monitoring webhook for Asana.\n{str(hook)}"
            )

    def create_projects(self, projects: list):
        ProjectRepository.create_bulk(
            [
                {
                    "name": project["name"],
                    "description": project["notes"],
                    "user": self.user_id,
                    "user_integration_id": self.user_integration.id,
                }
                for project in projects
            ]
        )

    def is_active(self, meta_data: dict, **kwargs) -> bool:
        """
        Check if the user's integration is active.

        Args:
        - meta_data: The user integration meta data.

        Returns:
        - bool: True if integration is active, False otherwise.
        """
        self._token = meta_data["token"]
        self._fetch_user_info()
        return True
