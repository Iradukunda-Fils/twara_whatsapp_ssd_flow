# states/welcome.py
from .base import BaseStateHandler, StateTransition

class WelcomeState(BaseStateHandler):
    """
    Initial state when user first contacts Twara.
    Welcomes user and checks if name is captured.
    """
    
    state_name = "welcome"
    display_name = "Welcome"
    requires_auth = False
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Welcome message with immediate transition check.
        """
        # Check if user has name
        if not self.customer.name:
            # Transition to name capture
            return None  # Will be handled by process_input
        
        # User has name, show main menu
        return None  # Will transition to main_menu
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Process any incoming message and route appropriately.
        """
        # Check if user has name
        if not self.customer.name:
            return StateTransition(
                next_state="name_capture",
                context_updates={"welcomed": True}
            )
        
        # User has name, go to main menu
        return StateTransition(
            next_state="main_menu",
            context_updates={"welcomed": True}
        )
    
