# integrations/whatsapp_webhook.py
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


class WhatsAppWebhookParser:
    """
    Parse incoming WhatsApp webhook payloads.
    
    Handles various message types: text, interactive, button replies, etc.
    """
    
    def __init__(self, webhook_data: Dict[str, Any]):
        self.data = webhook_data
    
    def extract_messages(self) -> List[Dict[str, Any]]:
        """
        Extract all messages from webhook payload.
        
        Returns:
            List of message dictionaries with standardized format.
        """
        messages = []
        
        try:
            entries = self.data.get('entry', [])
            
            for entry in entries:
                changes = entry.get('changes', [])
                
                for change in changes:
                    value = change.get('value', {})
                    
                    # Skip status updates
                    if 'statuses' in value:
                        continue
                    
                    # Extract messages
                    webhook_messages = value.get('messages', [])
                    
                    for msg in webhook_messages:
                        parsed_message = self._parse_message(msg)
                        if parsed_message:
                            messages.append(parsed_message)
        
        except Exception as e:
            logger.error(f"Error parsing webhook: {e}", exc_info=True)
        
        return messages
    
    def _parse_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse individual message based on type.
        """
        message_type = message.get('type', 'text')
        message_id = message.get('id')
        from_number = message.get('from')
        timestamp = message.get('timestamp')
        
        # Extract text based on message type
        text = self._extract_text(message, message_type)
        
        return {
            'message_id': message_id,
            'from': from_number,
            'timestamp': timestamp,
            'type': message_type,
            'text': text,
            'raw': message
        }
    
    def _extract_text(self, message: Dict[str, Any], message_type: str) -> str:
        """
        Extract text content based on message type.
        """
        if message_type == 'text':
            return message.get('text', {}).get('body', '')
        
        elif message_type == 'interactive':
            # Handle button or list replies
            interactive = message.get('interactive', {})
            
            if interactive.get('type') == 'button_reply':
                return interactive.get('button_reply', {}).get('id', '')
            
            elif interactive.get('type') == 'list_reply':
                return interactive.get('list_reply', {}).get('id', '')
        
        elif message_type == 'button':
            # Quick reply button
            return message.get('button', {}).get('payload', '')
        
        elif message_type == 'image':
            # Image caption
            return message.get('image', {}).get('caption', '[Image]')
        
        elif message_type == 'video':
            return message.get('video', {}).get('caption', '[Video]')
        
        elif message_type == 'document':
            return message.get('document', {}).get('caption', '[Document]')
        
        elif message_type == 'audio':
            return '[Audio]'
        
        elif message_type == 'location':
            location = message.get('location', {})
            return f"Location: {location.get('latitude')}, {location.get('longitude')}"
        
        else:
            logger.warning(f"Unsupported message type: {message_type}")
            return ''