# states/payment_success.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, InteractiveMessage
from whatsapp_ussd.models import UserPayment
from datetime import timedelta

class PaymentSuccessState(BaseStateHandler):
    """
    Confirm successful payment and provide access code.
    """
    
    state_name = "payment_success"
    display_name = "Payment Success"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Send success message with access code and link.
        """
        # Get payment details
        payment_ref = self.get_context("payment_ref")
        
        if not payment_ref:
            return StateTransition(
                next_state="main_menu",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Ikibazo cyabaye. Hamagara support."
                )
            )
        
        # Get payment record
        try:
            payment = UserPayment.objects.get(access_code=payment_ref)
        except UserPayment.DoesNotExist:
            return StateTransition(
                next_state="main_menu",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Ikibazo cyabaye. Hamagara support."
                )
            )
        
        # Get plan details
        plan = self.get_context("selected_plan")
        
        # Build success message
        body = (
            f"✅ *YISHYUWE NEZA!*\n\n"
            f"Twakiriye ibwishyu bwawe bwa *{payment.amount_paid:,} RWF*!\n\n"
            f"🔐 *Code yawe:*\n"
            f"```{payment.access_code}```\n\n"
            f"📱 *Link yo gutangira:*\n"
            f"https://twara.rw/exam/{payment.access_code}\n\n"
            f"⏱ *Igihe:* {payment.expiration} iminsi\n"
            f"📅 *Izarangira:* {(payment.paid_on + timedelta(days=payment.expiration)).strftime('%Y-%m-%d')}\n\n"
            f"🎯 *Ibikorwa byawe:*\n"
            f"• Kora ibizamini byinshi nk'uko ushaka\n"
            f"• Reba raporo yawe buri minsi 3\n"
            f"• Hamagara support igihe cyose\n\n"
            f"Urakoze kubufatanya bwawe! 🙏"
        )
        
        # Update customer status (is_vip is in UssdUser)
        if self.ussd_user.get_active_transactions().count() > 1:
            self.ussd_user.is_vip = True
            self.ussd_user.save(update_fields=['is_vip'])
        
        # Schedule welcome message
        from whatsapp_ussd.tasks import send_welcome_to_subscriber
        send_welcome_to_subscriber.apply_async(
            args=[self.customer.phone_number],
            countdown=5
        )
        
        return TextMessage(
            to=self.customer.phone_number,
            body=body,
            preview_url=True
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle post-payment actions.
        """
        message_lower = user_message.lower().strip()
        
        if "tangira" in message_lower or "start" in message_lower:
            # Start exam immediately
            return StateTransition(
                next_state="exam_start",
                context_updates={"post_purchase_exam": True}
            )
        
        elif "menu" in message_lower:
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        # Default: show options
        return StateTransition(
            next_state="payment_success",
            context_updates={},
            message_override=InteractiveMessage(
                to=self.customer.phone_number,
                body="Ese ushaka gukora ikizamini none?",
                header="KOMEZA"
            ).add_reply_button("start_exam", "🚀 Tangira ikizamini")
             .add_reply_button("go_menu", "📋 Subira ku menu")
        )
    
    def get_allowed_transitions(self) -> list:
        return ["exam_start", "main_menu", "payment_success"]