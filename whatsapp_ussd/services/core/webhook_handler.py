
"""
WhatsApp Business API Webhook Handler
Processes incoming webhooks and routes to StateFlowController
"""
import logging
from typing import Dict, Any, Optional
from whatsapp import WhatsAppWebhookMessage, WebhookValidator, WebhookMessageParser

logger = logging.getLogger(__name__)


class WhatsAppWebhookHandler:
    """Main webhook handler that integrates with StateFlowController"""
    
    def __init__(self, controller):
        """
        Args:
            controller: Instance of StateFlowController
        """
        self.controller = controller
        self.validator = WebhookValidator()
        self.parser = WebhookMessageParser()
    
    def handle_webhook(self, request_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook and route to controller
        
        Returns:
            Dict with status and any response data
        """
        # Validate webhook structure
        if not self.validator.is_valid_webhook(request_data):
            logger.warning("Invalid webhook structure")
            return {"status": "error", "message": "Invalid webhook structure"}
        
        # Check if it's a status update (ignore these)
        if self.validator.is_status_update(request_data):
            logger.info("Status update received, ignoring")
            return {"status": "ignored", "message": "Status update"}
        
        # Extract messages
        messages = self.validator.extract_messages(request_data)
        
        if not messages:
            logger.warning("No messages found in webhook")
            return {"status": "error", "message": "No messages found"}
        
        # Process each message
        results = []
        for msg_data in messages:
            result = self._process_message(msg_data)
            results.append(result)
        
        return {
            "status": "success",
            "processed": len(results),
            "results": results
        }
    
    def _process_message(self, msg_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a single message through the state controller"""
        # Parse message
        message: Optional[WhatsAppWebhookMessage] = self.parser.parse_message(msg_data)
        
        if not message:
            return {
                "status": "error",
                "message_id": msg_data.get("id"),
                "error": "Failed to parse message"
            }
        
        # Log incoming message
        logger.info(
            f"Processing message from {message.from_number}: "
            f"type={message.message_type}, body='{message.message_body[:50]}...'"
        )
        
        try:
            # Route to state controller
            response = self.controller.handle_message(
                phone_number=message.from_number,
                message=message.message_body
            )
            
            return {
                "status": "success",
                "message_id": message.message_id,
                "from": message.from_number,
                "response_sent": response is not None
            }
        
        except Exception as e:
            logger.error(
                f"Error processing message {message.message_id}: {e}",
                exc_info=True
            )
            return {
                "status": "error",
                "message_id": message.message_id,
                "from": message.from_number,
                "error": str(e)
            }