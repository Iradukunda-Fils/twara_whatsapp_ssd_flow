"""
WhatsApp webhook views for handling incoming messages.
"""
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
import json
import logging

from whatsapp_ussd.services.core.controller import StateFlowController
from whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    """
    Handle WhatsApp webhook requests.
    
    GET: Webhook verification (Meta requires this)
    POST: Incoming messages
    """
    if request.method == "GET":
        # Webhook verification
        verify_token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")
        
        # TODO: Move to settings
        expected_token = "your_webhook_verify_token"
        
        if verify_token == expected_token:
            return HttpResponse(challenge)
        else:
            return HttpResponse("Invalid verify token", status=403)
    
    # POST: Handle incoming messages
    try:
        # Verify webhook signature
        signature = request.headers.get("X-Hub-Signature-256", "")
        payload = request.body.decode("utf-8")
        
        if not WhatsAppClient.validate_webhook_signature(payload, signature):
            logger.warning("Invalid webhook signature")
            return JsonResponse({"error": "Invalid signature"}, status=403)
        
        data = json.loads(payload)
        
        # Handle webhook events
        if "entry" in data:
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    
                    # Handle incoming messages
                    if "messages" in value:
                        for message in value["messages"]:
                            _process_message(message)
                    
                    # Handle status updates (delivery, read receipts)
                    if "statuses" in value:
                        for status in value["statuses"]:
                            _process_status_update(status)
        
        return JsonResponse({"status": "ok"})
    
    except Exception as e:
        logger.exception(f"Error processing webhook: {e}")
        return JsonResponse({"error": "Internal server error"}, status=500)


def _process_message(message_data: dict):
    """Process incoming WhatsApp message."""
    try:
        import asyncio
        
        # Extract message details
        phone_number = message_data.get("from")
        message_type = message_data.get("type")
        
        if message_type == "text":
            message_text = message_data.get("text", {}).get("body", "")
        elif message_type == "interactive":
            # Handle button clicks
            interactive = message_data.get("interactive", {})
            if "button_reply" in interactive:
                message_text = interactive["button_reply"].get("id", "")
            elif "list_reply" in interactive:
                message_text = interactive["list_reply"].get("id", "")
            else:
                message_text = ""
        else:
            # Handle other message types (media, location, etc.)
            logger.info(f"Unsupported message type: {message_type}")
            return
        
        # Process through state controller (async)
        controller = StateFlowController()
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            response = loop.run_until_complete(controller.handle_message(phone_number, message_text))
            if not response or not response.success:
                logger.warning(f"Failed to process message from {phone_number}")
        finally:
            loop.close()
    
    except Exception as e:
        logger.exception(f"Error processing message: {e}")


def _process_status_update(status_data: dict):
    """Process message status updates (delivery, read)."""
    try:
        # Log status updates for analytics
        message_id = status_data.get("id")
        status = status_data.get("status")
        recipient = status_data.get("recipient_id")
        
        logger.info(f"Message {message_id} status: {status} for {recipient}")
        
        # TODO: Update message delivery status in database
        
    except Exception as e:
        logger.exception(f"Error processing status update: {e}")
