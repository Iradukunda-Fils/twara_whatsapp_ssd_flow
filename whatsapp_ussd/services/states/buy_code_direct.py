# states/buy_code_direct.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage

class BuyCodeDirectState(BaseStateHandler):
    """
    Direct purchase flow (Option 2 from main menu).
    Skips subscription offer and goes straight to plans.
    """
    
    state_name = "buy_code_direct"
    display_name = "Buy Code Direct"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Welcome message for direct purchase.
        """
        body = (
            f"🛒 *KUGURA CODE*\n\n"
            f"Murakoze {self.customer.name}!\n\n"
            f"Code yo kwitegura igufasha:\n"
            f"✅ Kora ibizamini byinshi\n"
            f"✅ Reba iterambere ryawe\n"
            f"✅ Witegure neza ikizamini\n\n"
            f"Hitamo plan ikubereye..."
        )
        
        return TextMessage(
            to=self.customer.phone_number,
            body=body
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Immediately transition to plan selection.
        """
        return StateTransition(
            next_state="plan_selection",
            context_updates={"direct_purchase": True}
        )
