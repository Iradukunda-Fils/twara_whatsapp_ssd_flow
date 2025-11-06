
"""
WhatsApp Business API Webhook Handler
Processes incoming webhooks and routes to StateFlowController
"""
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WhatsAppWebhookMessage:
    """Parsed WhatsApp message data"""
    from_number: str
    message_id: str
    timestamp: str
    message_type: str
    message_body: str
    contact_name: Optional[str] = None
    interactive_reply: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None


class WebhookValidator:
    """Validates incoming WhatsApp webhook payloads"""
    
    @staticmethod
    def is_valid_webhook(data: Dict[str, Any]) -> bool:
        """Check if payload has required WhatsApp structure"""
        try:
            if data.get("object") != "whatsapp_business_account":
                return False
            
            entry = data.get("entry", [])
            if not entry or not isinstance(entry, list):
                return False
            
            # Check at least one entry has valid structure
            for ent in entry:
                changes = ent.get("changes", [])
                if not changes or not isinstance(changes, list):
                    continue
                
                # At least one change should have WhatsApp messaging
                for change in changes:
                    value = change.get("value", {})
                    if value.get("messaging_product") == "whatsapp":
                        return True
            
            return False
        except (KeyError, IndexError, AttributeError):
            return False
    
    @staticmethod
    def extract_all_messages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract ALL message objects from webhook payload.
        Handles multiple entries and multiple changes per entry.
        """
        all_messages = []
        
        try:
            entries = data.get("entry", [])
            
            for entry in entries:
                changes = entry.get("changes", [])
                
                for change in changes:
                    value = change.get("value", {})
                    
                    # Skip if not WhatsApp or is status update
                    if value.get("messaging_product") != "whatsapp":
                        continue
                    if "statuses" in value:
                        continue
                    
                    messages = value.get("messages", [])
                    contacts = value.get("contacts", [])
                    metadata = value.get("metadata", {})
                    
                    # Build contact map
                    contact_map = {c.get("wa_id"): c for c in contacts}
                    
                    # Attach metadata and contact info to each message
                    for msg in messages:
                        # Add business metadata
                        msg["_metadata"] = {
                            "phone_number_id": metadata.get("phone_number_id"),
                            "display_phone_number": metadata.get("display_phone_number")
                        }
                        
                        # Attach contact info
                        from_number = msg.get("from")
                        if from_number and from_number in contact_map:
                            msg["_contact_info"] = contact_map[from_number]
                        
                        all_messages.append(msg)
            
            return all_messages
            
        except Exception as e:
            logger.error(f"Failed to extract messages: {e}", exc_info=True)
            return []
    
    @staticmethod
    def extract_messages(data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Backward compatibility wrapper.
        Extract messages from first entry/change only.
        """
        try:
            entry = data.get("entry", [])[0]
            changes = entry.get("changes", [])[0]
            value = changes.get("value", {})
            messages = value.get("messages", [])
            contacts = value.get("contacts", [])
            metadata = value.get("metadata", {})
            
            # Attach metadata and contact info to messages
            contact_map = {c.get("wa_id"): c for c in contacts}
            
            for msg in messages:
                msg["_metadata"] = {
                    "phone_number_id": metadata.get("phone_number_id"),
                    "display_phone_number": metadata.get("display_phone_number")
                }
                
                from_number = msg.get("from")
                if from_number and from_number in contact_map:
                    msg["_contact_info"] = contact_map[from_number]
            
            return messages
        except (KeyError, IndexError, AttributeError) as e:
            logger.error(f"Failed to extract messages: {e}")
            return []
    
    @staticmethod
    def has_status_updates(data: Dict[str, Any]) -> bool:
        """Check if webhook contains any status updates"""
        try:
            entries = data.get("entry", [])
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    if "statuses" in value:
                        return True
            return False
        except (KeyError, IndexError, AttributeError):
            return False
    
    @staticmethod
    def is_status_update(data: Dict[str, Any]) -> bool:
        """Check if webhook is ONLY status updates (no messages)"""
        try:
            entries = data.get("entry", [])
            has_status = False
            has_messages = False
            
            for entry in entries:
                changes = entry.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    if "statuses" in value:
                        has_status = True
                    if "messages" in value and value.get("messages"):
                        has_messages = True
            
            return has_status and not has_messages
        except (KeyError, IndexError, AttributeError):
            return False


class WebhookMessageParser:
    """Parses WhatsApp message objects into structured data"""
    
    @staticmethod
    def parse_message(msg_data: Dict[str, Any]) -> Optional[WhatsAppWebhookMessage]:
        """Parse a single message into WhatsAppMessage object"""
        try:
            message_type = msg_data.get("type")
            from_number = msg_data.get("from")
            message_id = msg_data.get("id")
            timestamp = msg_data.get("timestamp")
            
            if not all([message_type, from_number, message_id, timestamp]):
                logger.warning(f"Missing required fields in message: {msg_data}")
                return None
            
            # Extract contact name
            contact_info = msg_data.get("_contact_info", {})
            contact_name = contact_info.get("profile", {}).get("name")
            
            # Extract message body based on type
            message_body = WebhookMessageParser._extract_message_body(msg_data, message_type)
            
            # Extract interactive reply data
            interactive_reply = WebhookMessageParser._extract_interactive_reply(msg_data, message_type)
            
            # Extract context (reply info)
            context = msg_data.get("context")
            
            return WhatsAppWebhookMessage(
                from_number=from_number,
                message_id=message_id,
                timestamp=timestamp,
                message_type=message_type,
                message_body=message_body,
                contact_name=contact_name,
                interactive_reply=interactive_reply,
                context=context
            )
        except Exception as e:
            logger.error(f"Failed to parse message: {e}", exc_info=True)
            return None
    
    @staticmethod
    def _extract_message_body(msg_data: Dict[str, Any], msg_type: str) -> str:
        """Extract message body text based on message type"""
        if msg_type == "text":
            return msg_data.get("text", {}).get("body", "")
        
        elif msg_type == "interactive":
            # Button reply
            button_reply = msg_data.get("interactive", {}).get("button_reply", {})
            if button_reply:
                return button_reply.get("id", "")
            
            # List reply
            list_reply = msg_data.get("interactive", {}).get("list_reply", {})
            if list_reply:
                return list_reply.get("id", "")
        
        elif msg_type == "button":
            return msg_data.get("button", {}).get("payload", "")
        
        elif msg_type == "location":
            location = msg_data.get("location", {})
            return f"Location: {location.get('latitude')}, {location.get('longitude')}"
        
        elif msg_type in ["image", "video", "document", "audio", "sticker"]:
            caption = msg_data.get(msg_type, {}).get("caption", "")
            return caption or f"[{msg_type.upper()}]"
        
        return ""
    
    @staticmethod
    def _extract_interactive_reply(msg_data: Dict[str, Any], msg_type: str) -> Optional[Dict[str, Any]]:
        """Extract interactive reply details for context"""
        if msg_type == "interactive":
            interactive = msg_data.get("interactive", {})
            
            # Button reply
            if "button_reply" in interactive:
                return {
                    "type": "button",
                    "id": interactive["button_reply"].get("id"),
                    "title": interactive["button_reply"].get("title")
                }
            
            # List reply
            if "list_reply" in interactive:
                return {
                    "type": "list",
                    "id": interactive["list_reply"].get("id"),
                    "title": interactive["list_reply"].get("title"),
                    "description": interactive["list_reply"].get("description")
                }
        
        return None