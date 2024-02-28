import logging
import traceback

from common.exceptions import IntegrationAccessRevokedException
from integration.repository import IntegrationRepository
from integration.services.google import GoogleService

logger = logging.getLogger(__name__)


def refresh_watchers_and_tokens():
    """
    Refresh watchers for all users in the system.
    """
    try:
        user_integrations = IntegrationRepository.get_user_integrations(
            {
                "integration__name": "Gmail",
            }
        )
        for user_integration in user_integrations:
            try:
                google_service = GoogleService(
                    access_token=user_integration["meta_data"]["token"]["access_token"],
                    refresh_token=user_integration["meta_data"]["token"][
                        "refresh_token"
                    ],
                )
                google_service.add_watcher_to_inbox_pub_sub(
                    google_service._user_info["emailAddress"]
                )
                new_tokens = google_service.refresh_tokens()
                IntegrationRepository.update_integraion(
                    user_integration_id=user_integration["id"],
                    meta_data=IntegrationRepository.encrypt_meta_data(
                        {
                            **user_integration["meta_data"],
                            "token": {
                                **user_integration["meta_data"]["token"],
                                **new_tokens,
                            },
                        }
                    ),
                )
            except IntegrationAccessRevokedException:
                IntegrationRepository.revoke_user_integrations(
                    user_integrations=user_integration["id"]
                )
            except:
                logger.exception(
                    f"Error in refreshing watchers.",
                    extra={
                        "traceback": traceback.format_exc(),
                        "user_integration_id": user_integration["id"],
                        "user_integration_account_id": user_integration["account_id"],
                    },
                )
    except Exception:
        logger.exception(
            f"Error occurred while running cron job.",
            extra={
                "traceback": traceback.format_exc(),
            },
        )
