# states/waiting_for_offer.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage

class WaitingForOfferState(BaseStateHandler):
    """
    Intermediate state while waiting for delayed subscription offer.
    User stays here for 15 seconds after failed exam.
    """
    
    state_name = "waiting_for_offer"
    display_name = "Waiting for Offer"
    requires_auth = True
    timeout_seconds = 60  # Timeout after 1 minute if offer not triggered
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        No message sent - user already saw exam results.
        This state is just a placeholder for the delayed transition.
        """
        return None
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle any user input while waiting.
        """
        message_lower = user_message.lower().strip()
        
        if "menu" in message_lower:
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        elif "ikizamini" in message_lower or "exam" in message_lower:
            # User wants to retry exam
            return StateTransition(
                next_state="exam_start",
                context_updates={"retry_from_waiting": True}
            )
        
        # Any other input: remind user to wait
        return StateTransition(
            next_state="waiting_for_offer",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Tegereza gato... Tugiye kugufasha kwitegura neza. ⏳"
            )
        )
    
