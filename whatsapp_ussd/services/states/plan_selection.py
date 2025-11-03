# states/plan_selection.py
from .base import BaseStateHandler, StateTransition
from whatsapp import ListMessage, TextMessage

class PlanSelectionState(BaseStateHandler):
    """
    Display available subscription plans using ListMessage.
    """
    
    state_name = "plan_selection"
    display_name = "Plan Selection"
    requires_auth = True
    
    # Plan definitions
    PLANS = {
        "daily": {"name": "Umunsi", "price": 1000, "days": 1, "description": "1 munsi"},
        "weekly": {"name": "Icyumweru", "price": 2000, "days": 7, "description": "7 iminsi"},
        "monthly": {"name": "Ukwezi", "price": 5000, "days": 30, "description": "30 iminsi - Popular!"},
        "quarterly": {"name": "Amezi 3", "price": 10000, "days": 90, "description": "90 iminsi - Igiciro cyiza"},
        "yearly": {"name": "Umwaka", "price": 30000, "days": 365, "description": "365 iminsi - Best value!"}
    }
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show subscription plans in a list.
        """
        body = (
            "🎯 *TWARA SUBSCRIPTION PLANS*\n\n"
            "Hitamo plan ikubereye:\n"
            "• Ibizamini bitagira ingano\n"
            "• Raporo y'iterambere\n"
            "• Support 24/7"
        )
        
        message = ListMessage(
            to=self.customer.phone_number,
            body=body,
            button_text="Hitamo Plan",
            header="PLANS"
        )
        
        # Popular plans section
        popular_rows = [
            {
                "id": "monthly",
                "title": f"🌟 {self.PLANS['monthly']['name']} - {self.PLANS['monthly']['price']:,}RWF",
                "description": self.PLANS['monthly']['description']
            },
            {
                "id": "quarterly",
                "title": f"💎 {self.PLANS['quarterly']['name']} - {self.PLANS['quarterly']['price']:,}RWF",
                "description": self.PLANS['quarterly']['description']
            }
        ]
        message.add_section("⭐ Popular", popular_rows)
        
        # All plans section
        all_plans_rows = [
            {
                "id": "daily",
                "title": f"{self.PLANS['daily']['name']} - {self.PLANS['daily']['price']:,}RWF",
                "description": self.PLANS['daily']['description']
            },
            {
                "id": "weekly",
                "title": f"{self.PLANS['weekly']['name']} - {self.PLANS['weekly']['price']:,}RWF",
                "description": self.PLANS['weekly']['description']
            },
            {
                "id": "yearly",
                "title": f"🎁 {self.PLANS['yearly']['name']} - {self.PLANS['yearly']['price']:,}RWF",
                "description": self.PLANS['yearly']['description']
            }
        ]
        message.add_section("Izindi Plans", all_plans_rows)
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle plan selection.
        """
        choice = user_message.lower().strip()
        
        # Map user input to plan
        plan_key = None
        if choice in self.PLANS:
            plan_key = choice
        elif "umunsi" in choice or "daily" in choice:
            plan_key = "daily"
        elif "icyumweru" in choice or "weekly" in choice:
            plan_key = "weekly"
        elif "ukwezi" in choice or "monthly" in choice:
            plan_key = "monthly"
        elif "amezi 3" in choice or "quarterly" in choice:
            plan_key = "quarterly"
        elif "umwaka" in choice or "yearly" in choice:
            plan_key = "yearly"
        
        if plan_key:
            selected_plan = self.PLANS[plan_key]
            
            return StateTransition(
                next_state="plan_confirmation",
                context_updates={
                    "selected_plan_key": plan_key,
                    "selected_plan": selected_plan
                }
            )
        
        # Invalid selection
        return StateTransition(
            next_state="plan_selection",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Hitamo plan imwe muri zo hejuru."
            )
        )
    
