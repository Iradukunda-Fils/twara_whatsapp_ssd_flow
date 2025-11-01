# states/payment_input.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage
from django.utils import timezone
import re

class PaymentInputState(BaseStateHandler):
    """
    Collect Mobile Money phone number for payment.
    """
    
    state_name = "payment_input"
    display_name = "Payment Input"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Ask for Mobile Money number.
        """
        plan = self.get_context("selected_plan")
        
        if not plan:
            return StateTransition(
                next_state="plan_selection",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Hitamo plan mbere."
                )
            )
        
        body = (
            f"💳 *ISHYURA*\n\n"
            f"Plan: {plan['name']}\n"
            f"Igiciro: *{plan['price']:,} RWF*\n\n"
            f"Shyiramo numero ukoresha kuri:\n"
            f"• MTN Mobile Money\n"
            f"• Airtel Money\n\n"
            f"Numero igomba kuba ifite amafaranga "
            f"{plan['price']:,}RWF.\n\n"
            f"Numara kwemeza, uzabona SMS yo kwishyura."
        )
        
        return TextMessage(
            to=self.customer.phone_number,
            body=body
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Validate and process phone number.
        """
        # Clean phone number
        phone = user_message.strip()
        phone = re.sub(r'[^\d+]', '', phone)  # Remove non-digit characters except +
        
        # Validate phone number format
        is_valid, error_message = self._validate_phone_number(phone)
        
        if not is_valid:
            return StateTransition(
                next_state="payment_input",
                context_updates={},
                validation_errors=[error_message],
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=f"❌ {error_message}\n\nOngera ugerageze."
                )
            )
        
        # Normalize phone number
        if not phone.startswith('+'):
            if phone.startswith('0'):
                phone = '+250' + phone[1:]
            elif phone.startswith('250'):
                phone = '+' + phone
            else:
                phone = '+250' + phone
        
        # Get plan details
        plan = self.get_context("selected_plan")
        
        # Initiate payment (async task)
        from whatsapp_ussd.tasks import initiate_mobile_money_payment
        
        return StateTransition(
            next_state="payment_pending",
            context_updates={
                "payment_phone": phone,
                "payment_initiated_at": timezone.now().isoformat()
            },
            celery_tasks=[
                (
                    initiate_mobile_money_payment,
                    [self.customer.id, phone, plan['price'], plan['days']],
                    {},
                    0
                )
            ]
        )
    
    def _validate_phone_number(self, phone: str) -> tuple[bool, str]:
        """
        Validate phone number format.
        """
        # Remove spaces and special characters for validation
        clean_phone = re.sub(r'[^\d]', '', phone)
        
        # Check length (should be 10-12 digits)
        if len(clean_phone) < 9:
            return False, "Numero ntabwo ikora. Numero igomba kuba ifite imibare 10."
        
        if len(clean_phone) > 13:
            return False, "Numero ndende cyane."
        
        # Check if starts with valid Rwanda prefix
        if clean_phone.startswith('250'):
            operator_prefix = clean_phone[3:6]
        elif clean_phone.startswith('0'):
            operator_prefix = clean_phone[1:4]
        else:
            operator_prefix = clean_phone[0:3]
        
        # Valid Rwandan mobile prefixes (MTN: 078, 079; Airtel: 073, 072)
        valid_prefixes = ['078', '079', '073', '072']
        
        if operator_prefix not in valid_prefixes:
            return False, "Numero ntabwo iri muri MTN cyangwa Airtel."
        
        return True, ""
    
    def get_allowed_transitions(self) -> list:
        return ["payment_pending", "payment_input", "plan_confirmation"]