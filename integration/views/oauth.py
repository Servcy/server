import logging
import urllib.parse

from rest_framework import status, viewsets
from rest_framework.decorators import action

from common.exceptions import ServcyOauthCodeException
from common.responses import error_response, success_response
from integration.services.figma import FigmaService
from integration.services.github import GithubService
from integration.services.google import GOOGLE_SCOPES, GoogleService
from integration.services.microsoft import MicrosoftService
from integration.services.notion import NotionService
from integration.services.slack import SlackService

logger = logging.getLogger(__name__)


class OauthViewset(viewsets.ViewSet):
    def _handle_oauth_code(self, request, service_class, service_name: str):
        """Generalized method to handle OAuth2 authorization flow for a given service.

        :param request: The HTTP request object.
        :param service_class: The service class responsible for the OAuth2 flow.
        :param service_name: The name of the service for logging and error messages.
        :return: HTTP response.
        """
        try:
            code = urllib.parse.unquote(request.data["code"])
            service = service_class(code=code)
            user_integration = service.create_integration(user_id=request.user.id)
            return success_response(
                results={
                    "redirect": f"{user_integration.integration.configure_at}?user_integration_id={user_integration.id}"
                }
                if user_integration.integration.configure_at is not None
                else None,
                success_message=f"Successfully integrated with {service_name}!",
                status=status.HTTP_200_OK,
            )
        except ServcyOauthCodeException as error:
            return error_response(
                logger=logger,
                logger_message=error.message,
                error_message=f"An error occurred while integrating with {service_name}. Please try again later.",
            )
        except KeyError:
            return error_response(
                logger=logger,
                logger_message="KeyError occurred processing oauth request.",
                error_message="code is required!",
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as ex:
            logger.error(
                f"An unexpected error occurred processing oauth request for {service_name}: {str(ex)}"
            )
            return error_response(
                logger=logger,
                logger_message="An unexpected error occurred processing oauth request.",
            )

    @action(detail=False, methods=["put"], url_path="google")
    def google(self, request):
        """Handle OAuth2 authorization flow for Google."""
        scopes = urllib.parse.unquote(request.data.get("scope", "")).split(" ")
        if not set(scopes).issubset(set(GOOGLE_SCOPES)):
            return error_response(
                logger=logger,
                logger_message="An error occurred processing oauth request.",
                status=status.HTTP_406_NOT_ACCEPTABLE,
                error_message="Please grant all permissions, and try again!",
            )
        return self._handle_oauth_code(request, GoogleService, "Google")

    @action(detail=False, methods=["put"], url_path="microsoft")
    def microsoft(self, request):
        """Handle OAuth2 authorization flow for Microsoft."""
        return self._handle_oauth_code(request, MicrosoftService, "Microsoft")

    @action(detail=False, methods=["put"], url_path="notion")
    def notion(self, request):
        return self._handle_oauth_code(request, NotionService, "Notion")

    @action(detail=False, methods=["put"], url_path="slack")
    def slack(self, request):
        return self._handle_oauth_code(request, SlackService, "Slack")

    @action(detail=False, methods=["put"], url_path="figma")
    def figma(self, request):
        return self._handle_oauth_code(request, FigmaService, "Figma")

    @action(detail=False, methods=["put"], url_path="github")
    def github(self, request):
        return self._handle_oauth_code(request, GithubService, "Github")
