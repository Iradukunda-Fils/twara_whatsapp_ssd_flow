# api/views/webhook.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings
import json
import logging
import hmac
import hashlib

from whatsapp_ussd.services.core.controller import StateFlowController
from ..integrations.whatsapp_webhook import WhatsAppWebhookParser
from ..middleware import RateLimitMiddleware

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookView(APIView):
    """
    WhatsApp Cloud API Webhook Handler (Production)
    
    Receives incoming messages and routes to state machine.
    """
    
    authentication_classes = []  # No auth for webhooks
    permission_classes = []
    
    def post(self, request):
        """
        Handle incoming WhatsApp messages.
        
        Request body format:
        {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {...},
                        "contacts": [...],
                        "messages": [{
                            "from": "250788123456",
                            "id": "wamid.xxx",
                            "timestamp": "1234567890",
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        """
        try:
            # Validate signature
            signature = request.headers.get('X-Hub-Signature-256', '')
            if not self._verify_signature(request.body, signature):
                logger.warning("Invalid webhook signature")
                return Response(
                    {"error": "Invalid signature"},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            
            # Parse webhook data
            data = json.loads(request.body.decode('utf-8'))
            
            # Validate webhook format
            if data.get('object') != 'whatsapp_business_account':
                return Response(
                    {"error": "Invalid webhook object"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Extract message details
            parser = WhatsAppWebhookParser(data)
            messages = parser.extract_messages()
            
            if not messages:
                # No messages to process (could be status update)
                return Response({"status": "ok"}, status=status.HTTP_200_OK)
            
            # Process each message
            for message_data in messages:
                phone_number = message_data['from']
                message_text = message_data['text']
                message_id = message_data['message_id']
                message_type = message_data['type']
                
                # Rate limiting check
                if not RateLimitMiddleware.check_rate_limit(phone_number):
                    logger.warning(f"Rate limit exceeded for {phone_number}")
                    continue
                
                # Log incoming message
                logger.info(
                    f"Incoming message from {phone_number}: "
                    f"{message_text[:50]}... (type: {message_type})"
                )
                
                # Process message asynchronously
                from whatsapp_ussd.tasks import process_whatsapp_message
                process_whatsapp_message.delay(
                    phone_number=phone_number,
                    message_text=message_text,
                    message_id=message_id,
                    message_type=message_type
                )
            
            # Acknowledge receipt
            return Response({"status": "queued"}, status=status.HTTP_200_OK)
        
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in webhook: {e}")
            return Response(
                {"error": "Invalid JSON"},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        except Exception as e:
            logger.exception(f"Webhook processing error: {e}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _verify_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify webhook signature using app secret.
        
        WhatsApp signs webhooks with HMAC-SHA256.
        """
        if not settings.WHATSAPP_APP_SECRET:
            logger.warning("WHATSAPP_APP_SECRET not configured")
            return True  # Skip verification in development
        
        expected_signature = hmac.new(
            settings.WHATSAPP_APP_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        expected_sig_with_prefix = f"sha256={expected_signature}"
        
        return hmac.compare_digest(expected_sig_with_prefix, signature)


@method_decorator(csrf_exempt, name='dispatch')
class WhatsAppWebhookVerifyView(APIView):
    """
    WhatsApp Webhook Verification (Required by Meta)
    
    Meta will send a GET request to verify the webhook URL.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        """
        Verify webhook with Meta.
        
        Query params:
        - hub.mode: "subscribe"
        - hub.verify_token: Your verify token
        - hub.challenge: Random string to echo back
        """
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')
        
        verify_token = settings.WHATSAPP_VERIFY_TOKEN
        
        if mode == 'subscribe' and token == verify_token:
            logger.info("Webhook verified successfully")
            return Response(int(challenge), status=status.HTTP_200_OK)
        else:
            logger.warning(f"Webhook verification failed: mode={mode}, token={token}")
            return Response(
                {"error": "Verification failed"},
                status=status.HTTP_403_FORBIDDEN
            )