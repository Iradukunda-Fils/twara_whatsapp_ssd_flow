# api/views/webhook.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.http import HttpRequest, HttpResponse
from django.conf import settings
from typing import Dict, Any
import json
import logging

from whatsapp import WhatsAppClient, WHATSAPP_CLIENT
from whatsapp_ussd.services.core import StateFlowController, WhatsAppWebhookHandler


logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name="dispatch")
class WhatsAppWebhookView(APIView):
    """
    Webhook view that delegates processing to WhatsAppWebhookHandler which
    integrates with the StateFlowController.
    """

    authentication_classes = []
    permission_classes = []

    whatsapp_client: WhatsAppClient = WHATSAPP_CLIENT

    # -------------------------------------------
    # GET — Webhook Verification
    # -------------------------------------------
    def get(self, request: HttpRequest):
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        verify_token = getattr(settings, "WHATSAPP_APP_SECRET", "your_verify_token")

        if mode == "subscribe" and token == verify_token:
            logger.info("Webhook verified successfully")
            return HttpResponse(challenge or "", content_type="text/plain")

        logger.warning("Webhook verification failed: mode=%s token=%s", mode, token)
        return HttpResponse("Forbidden", status=403)

    # -------------------------------------------
    # POST — Incoming webhook
    # -------------------------------------------
    def post(self, request: HttpRequest):
        try:
            # Read raw body once and use it for signature validation and parsing
            raw_body_bytes = request.body or b""
            try:
                raw_body = raw_body_bytes.decode("utf-8")
            except Exception:
                # fallback to str(raw_bytes) if decoding fails (should be rare)
                raw_body = raw_body_bytes.decode("utf-8", errors="ignore")

            # Validate signature header
            signature = request.headers.get("X-Hub-Signature-256", "")
            if not self.whatsapp_client.validate_webhook_signature(raw_body, signature):
                logger.warning("Invalid webhook signature")
                return Response({"error": "Invalid signature"}, status=status.HTTP_401_UNAUTHORIZED)

            # Parse JSON payload
            try:
                data = json.loads(raw_body) if raw_body else {}
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in webhook: %s", e)
                return Response({"error": "Invalid JSON"}, status=status.HTTP_400_BAD_REQUEST)

            # Build handler (and controller)
            controller = StateFlowController()
            handler = WhatsAppWebhookHandler(controller)


            # Delegate processing to the handler
            result: Dict[str, Any] = handler.handle_webhook(data)

            # Map handler result to HTTP response
            status_str = result.get("status", "").lower()
            if status_str == "success":
                return Response(result, status=status.HTTP_200_OK)
            if status_str == "ignored":
                # status update or similar - not an error
                return Response(result, status=status.HTTP_200_OK)
            # any other value is treated as a client error (bad payload / parse)
            return Response(result, status=status.HTTP_400_BAD_REQUEST)

        except Exception as exc:
            logger.exception("Unhandled exception processing webhook: %s", exc)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# URL Configuration (add to urls.py)
"""
from django.urls import path
from whatsapp_webhook.handler import whatsapp_webhook_view

urlpatterns = [
    path('webhook/whatsapp/', whatsapp_webhook_view, name='whatsapp_webhook'),
]
"""


# Settings Configuration (add to settings.py)
"""
# WhatsApp Configuration
WHATSAPP_VERIFY_TOKEN = "your_secure_verify_token_here"
WHATSAPP_ACCESS_TOKEN = "your_whatsapp_access_token_here"
WHATSAPP_PHONE_NUMBER_ID = "your_phone_number_id"

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'whatsapp_webhook.log',
        },
    },
    'loggers': {
        'whatsapp_webhook': {
            'handlers': ['file'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}
"""