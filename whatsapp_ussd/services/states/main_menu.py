# states/main_menu.py
from .base import BaseStateHandler, StateTransition
from whatsapp import ListMessage, TextMessage

class MainMenuState(BaseStateHandler):
    """
    Main menu with 3 options using ListMessage.
    """
    
    state_name = "main_menu"
    display_name = "Main Menu"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Display main menu with interactive list.
        """
        # Check if user just registered
        if self.get_context("name_captured"):
            greeting = f"Murakoze cyane {self.customer.name}!"
        else:
            greeting = f"Murakaza neza {self.customer.name}!"
        
        # Check subscription status for personalized message
        has_active_sub = self.customer.get_active_transactions().exists()
        
        if has_active_sub:
            body = (
                f"{greeting}\n\n"
                f"Ufite subscription ikora. Hitamo icyo ushaka gukora:"
            )
        else:
            body = (
                f"{greeting}\n\n"
                f"Murakaza neza kuri Twara, Itegure ikizamini cy'amategeko "
                f"y'umuhanda utigoye.\n\n"
                f"Wemerewe gukora ikizamini cyo kugerageza ubumenyi bwawe "
                f"kubuntu inshuro yambere."
            )
        
        # Build menu with ListMessage
        message = ListMessage(
            to=self.customer.phone_number,
            body=body,
            button_text="Hitamo",
            header="MENU"
        )
        
        # Add main menu section
        menu_rows = [
            {
                "id": "take_exam",
                "title": "Gukora ikizamini",
                "description": "Tangira ikizamini cya none"
            },
            {
                "id": "buy_code",
                "title": "Kugura Code",
                "description": "Gura code yo kwitegura"
            },
            {
                "id": "police_info",
                "title": "Kwiyandikisha kuri Police",
                "description": "Menya uko wiyandikisha"
            }
        ]
        
        message.add_section("Hitamo", menu_rows)
        
        # Add additional options if user has subscription
        if has_active_sub:
            extra_rows = [
                {
                    "id": "view_progress",
                    "title": "Reba uko uhagaze",
                    "description": "Amanota n'iterambere"
                },
                {
                    "id": "subscription_status",
                    "title": "Subscription yawe",
                    "description": "Reba igihe gisigaye"
                }
            ]
            message.add_section("Ibindi", extra_rows)
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Route based on user selection.
        """
        choice = user_message.lower().strip()
        
        # Map choices to states
        if choice == "take_exam" or "ikizamini" in choice:
            return StateTransition(
                next_state="exam_start",
                context_updates={"exam_source": "main_menu"}
            )
        
        elif choice == "buy_code" or "code" in choice:
            return StateTransition(
                next_state="buy_code_direct",
                context_updates={"purchase_source": "main_menu"}
            )
        
        elif choice == "police_info" or "police" in choice:
            return StateTransition(
                next_state="police_registration_info",
                context_updates={}
            )
        
        elif choice == "view_progress":
            return StateTransition(
                next_state="view_progress",
                context_updates={}
            )
        
        elif choice == "subscription_status":
            return StateTransition(
                next_state="subscription_status",
                context_updates={}
            )
        
        # Invalid choice
        return StateTransition(
            next_state="main_menu",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Murakoze. Hitamo kimwe muri menu."
            )
        )
    
    def get_allowed_transitions(self) -> list:
        return [
            "exam_start", 
            "buy_code_direct", 
            "police_registration_info",
            "view_progress",
            "subscription_status",
            "main_menu"
        ]