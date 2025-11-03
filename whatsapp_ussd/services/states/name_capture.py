# states/name_capture.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage

class NameCaptureState(BaseStateHandler):
    """
    Captures user's name before allowing exam access.
    """
    
    state_name = "name_capture"
    display_name = "Name Capture"
    requires_auth = False
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Ask user to provide their name.
        """
        return TextMessage(
            to=self.customer.phone_number,
            body="Andika izina ryawe."
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Validate and save user's name.
        """
        # Clean input
        name = user_message.strip()
        
        # Validate name (at least 2 characters, letters only)
        if len(name) < 2:
            return StateTransition(
                next_state="name_capture",  # Stay in same state
                context_updates={},
                validation_errors=["Izina rigomba kuba rifite ibyanditswe byibura 2"],
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Izina rigomba kuba rifite ibyanditswe byibura 2. Ongera ugerageze."
                )
            )
        
        # Check if name contains only letters and spaces
        if not all(c.isalpha() or c.isspace() for c in name):
            return StateTransition(
                next_state="name_capture",
                context_updates={},
                validation_errors=["Name must contain only letters"],
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Izina rigomba kuba rifite inyuguti gusa. Ongera ugerageze."
                )
            )
        
        # Save name to database
        self.customer.name = name
        self.customer.save(update_fields=['name'])
        
        # Transition to main menu with success message
        return StateTransition(
            next_state="main_menu",
            context_updates={"name_captured": True}
        )
    
