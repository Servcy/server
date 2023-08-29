import json
import logging
import traceback

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def github(request):
    try:
        body = json.loads(request.body)
        logger.info(f"Received github webhook: {body}")
        return HttpResponse(status=200)
    except Exception:
        logger.error(
            f"An error occurred while processing github webhook.\n{traceback.format_exc()}"
        )
        return HttpResponse(status=500)