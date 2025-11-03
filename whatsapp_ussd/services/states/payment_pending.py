# states/payment_pending.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage
from whatsapp_ussd.models import UserPayment

class PaymentPendingState(BaseStateHandler):
    """
    Wait for payment confirmation.
    Display instructions and polling status.
    """
    
    state_name = "payment_pending"
    display_name = "Payment Pending"
    requires_auth = True
    timeout_seconds = 300  # 5 minutes
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show payment instructions and wait.
        """
        plan = self.get_context("selected_plan")
        payment_phone = self.get_context("payment_phone")
        
        # Get customer name (first name only)
        first_name = self.customer.name.split()[0] if self.customer.name else "Customer"
        
        body = (
            f"📱 *KWISHYURA*\n\n"
            f"Mwaramutse {first_name}!\n\n"
            f"Ugiye kubona ubutumwa bwo kwishyura "
            f"amafaranga *{plan['price']:,} RWF* kuri "
            f"Mobile Money yawe ({payment_phone}).\n\n"
            f"⏱ *Nyuma yo kwishyura:*\n"
            f"1. Injiza PIN yawe\n"
            f"2. Emeza kwishyura\n"
            f"3. Uzabona ubutumwa hano\n\n"
            f"Tegereza gato... ⏳"
        )
        
        # Start payment polling (background task)
        payment_ref = self.get_context("payment_ref")
        if payment_ref:
            from ...tasks import poll_payment_status
            poll_payment_status.delay(payment_ref, attempt=0)
        
        return TextMessage(
            to=self.customer.phone_number,
            body=body
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle user input while waiting for payment.
        """
        message_lower = user_message.lower().strip()
        
        if "hagarika" in message_lower or "cancel" in message_lower:
            # Cancel payment
            payment_ref = self.get_context("payment_ref")
            if payment_ref:
                # Mark payment as cancelled in database
                try:
                    payment = UserPayment.objects.get(access_code=payment_ref)
                    payment.status = "failed"
                    payment.save(update_fields=['status'])
                except UserPayment.DoesNotExist:
                    pass
            
            return StateTransition(
                next_state="main_menu",
                context_updates={"payment_cancelled": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Kwishyura byahagaritswe. Uza kugerageza igihe cyose."
                )
            )
        
        elif "help" in message_lower or "ubufasha" in message_lower:
            return StateTransition(
                next_state="payment_pending",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        "🆘 *UBUFASHA*\n\n"
                        "Niba udashobora kwishyura:\n"
                        "1. Reba niba ufite amafaranga ahagije\n"
                        "2. Reba niba Mobile Money ikora\n"
                        "3. Hamagara: 0788 123 456\n\n"
                        "Cyangwa andika 'HAGARIKA' kugira ngo uhagarike."
                    )
                )
            )
        
        # Default: remind user to complete payment
        return StateTransition(
            next_state="payment_pending",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body=(
                    "Tegereza gato...\n"
                    "Urashobora kuhagarika wandika 'HAGARIKA'."
                )
            )
        )
    
