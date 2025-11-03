# states/payment_failed.py
from .base import BaseStateHandler, StateTransition
from whatsapp import InteractiveMessage, TextMessage
import logging

logger = logging.getLogger(__name__)


class PaymentFailedState(BaseStateHandler):
    """
    Handle payment failure with comprehensive retry options.
    Provides troubleshooting help and alternative payment methods.
    """
    
    state_name = "payment_failed"
    display_name = "Payment Failed"
    requires_auth = True
    timeout_seconds = 600  # 10 minutes
    
    # Common failure reasons mapping
    FAILURE_REASONS = {
        "insufficient_funds": "Amafaranga ntahagije kuri Mobile Money yawe",
        "invalid_pin": "PIN ntabwo ari yo",
        "transaction_timeout": "Igihe cyarengeje. Ongera ugerageze",
        "user_cancelled": "Wahagaritse kwishyura",
        "network_error": "Ikibazo cya network. Ongera ugerageze",
        "account_blocked": "Konti yawe yahagaritswe. Hamagara Mobile Money",
        "daily_limit_exceeded": "Warenze limit yo ku munsi",
        "default": "Ikibazo cyabaye mu kwishyura"
    }
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show failure message with troubleshooting and retry options.
        """
        # Get failure details from context
        failure_code = self.get_context("payment_failure_code", "default")
        failure_reason = self.get_context(
            "payment_failure_reason", 
            self.FAILURE_REASONS.get(failure_code, self.FAILURE_REASONS["default"])
        )
        
        # Get plan details
        plan = self.get_context("selected_plan")
        payment_phone = self.get_context("payment_phone", "")
        
        # Determine which provider was used
        if payment_phone.startswith('+25078') or payment_phone.startswith('078'):
            provider = "MTN Mobile Money"
            support_number = "*182#"
        elif payment_phone.startswith('+25073') or payment_phone.startswith('073'):
            provider = "Airtel Money"
            support_number = "*182#"
        else:
            provider = "Mobile Money"
            support_number = "*182#"
        
        # Build comprehensive failure message
        body = (
            f"❌ *KWISHYURA NTIBYAKUNZE*\n\n"
            f"Mbabarira {self.customer.name}, kwishyura kwawe ntabwo "
            f"kwakunda.\n\n"
            f"📋 *Ibisobanuro:*\n"
            f"{failure_reason}\n\n"
            f"💰 *Igiciro:* {plan['price']:,} RWF\n"
            f"📱 *Numero:* {payment_phone}\n"
            f"💳 *Provider:* {provider}\n\n"
        )
        
        # Add troubleshooting tips based on failure reason
        if failure_code == "insufficient_funds":
            body += (
                f"🔍 *Kugenzura:*\n"
                f"1. Reba solde yawe: {support_number}\n"
                f"2. Ongera wishyujemo amafaranga\n"
                f"3. Gerageza ikindi konti\n\n"
            )
        elif failure_code == "invalid_pin":
            body += (
                f"🔍 *Kugenzura:*\n"
                f"1. Reba PIN yawe\n"
                f"2. Niba wataye PIN, hamagara {support_number}\n\n"
            )
        elif failure_code == "daily_limit_exceeded":
            body += (
                f"🔍 *Ibisubizo:*\n"
                f"1. Tegereza ejo\n"
                f"2. Koresha ikindi konti\n"
                f"3. Hamagara {support_number} kugira ngo bazamure limit\n\n"
            )
        else:
            body += (
                f"🔍 *Ikibazo gishobora kuba:*\n"
                f"• Amafaranga ntahagije ({plan['price']:,} RWF needed)\n"
                f"• Mobile Money ntikiri gukora\n"
                f"• Network problem\n"
                f"• PIN yawe si yo\n\n"
            )
        
        body += (
            f"💡 *Ushaka gukora iki?*"
        )
        
        # Log failure for analytics
        self._log_payment_failure(failure_code, failure_reason)
        
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="PAYMENT FAILED",
            footer="Twara Support: 0788 123 456"
        )
        
        # Add action buttons
        message.add_reply_button("retry_payment", "🔄 Ongera gerageza")
        message.add_reply_button("change_number", "📱 Hindura numero")
        message.add_reply_button("get_help", "🆘 Nsaba ubufasha")
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle retry, change number, or get help.
        """
        choice = user_message.lower().strip()
        
        if choice == "retry_payment" or "ongera" in choice or "retry" in choice:
            # Retry with same phone number
            payment_phone = self.get_context("payment_phone")
            
            return StateTransition(
                next_state="payment_input",
                context_updates={
                    "retry_payment": True,
                    "retry_count": self.get_context("retry_count", 0) + 1,
                    "previous_failure": self.get_context("payment_failure_code")
                },
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        f"🔄 *ONGERA GERAGEZA*\n\n"
                        f"Reba niba:\n"
                        f"• Ufite amafaranga ahagije\n"
                        f"• Mobile Money ikora\n"
                        f"• PIN yawe ari yo\n\n"
                        f"Kanda kuri link uzakura kugira ngo wemeze kwishyura."
                    )
                )
            )
        
        elif choice == "change_number" or "hindura" in choice or "change" in choice:
            # Change phone number
            return StateTransition(
                next_state="payment_input",
                context_updates={
                    "change_payment_number": True,
                    "previous_payment_phone": self.get_context("payment_phone")
                },
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        f"📱 *HINDURA NUMERO*\n\n"
                        f"Shyiraho numero nshya yo kwishyura.\n\n"
                        f"Numero igomba kuba:\n"
                        f"• Ifite amafaranga ahagije\n"
                        f"• MTN (078/079) cyangwa Airtel (073/072)\n\n"
                        f"Andika numero:"
                    )
                )
            )
        
        elif choice == "get_help" or "ubufasha" in choice or "help" in choice:
            # Provide comprehensive help
            return StateTransition(
                next_state="payment_failed",  # Stay in same state
                context_updates={"help_requested": True},
                message_override=self._get_help_message()
            )
        
        elif "cancel" in choice or "hagarika" in choice:
            # Cancel and return to menu
            return StateTransition(
                next_state="main_menu",
                context_updates={"payment_cancelled_after_failure": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        "Kwishyura byahagaritswe.\n\n"
                        "Uza kugerageza igihe cyose.\n"
                        "Niba ukeneye ubufasha, hamagara:\n"
                        "📞 0788 123 456"
                    )
                )
            )
        
        elif "menu" in choice:
            # Go to main menu
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        # Invalid choice - show options again
        return StateTransition(
            next_state="payment_failed",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body=(
                    "Hitamo kimwe muri:\n"
                    "• 🔄 Ongera gerageza\n"
                    "• 📱 Hindura numero\n"
                    "• 🆘 Nsaba ubufasha\n"
                    "• ❌ Hagarika"
                )
            )
        )
    
    def _get_help_message(self) -> TextMessage:
        """
        Generate comprehensive help message.
        """
        plan = self.get_context("selected_plan")
        
        body = (
            f"🆘 *UBUFASHA BWO KWISHYURA*\n\n"
            f"*Plan:* {plan['name']}\n"
            f"*Igiciro:* {plan['price']:,} RWF\n\n"
            f"📋 *Ibyangombwa:*\n"
            f"1. Konti ya Mobile Money (MTN/Airtel)\n"
            f"2. Amafaranga {plan['price']:,} RWF\n"
            f"3. PIN yawe\n\n"
            f"🔍 *Ibibazo bikunze kubaho:*\n\n"
            f"*1. Amafaranga ntahagije*\n"
            f"Igisubizo: Reba solde (*182#) wishyujemo amafaranga\n\n"
            f"*2. PIN si yo*\n"
            f"Igisubizo: Hindura PIN yawe (*182#)\n\n"
            f"*3. Daily limit*\n"
            f"Igisubizo: Tegereza ejo cyangwa koresha ikindi konti\n\n"
            f"*4. Network error*\n"
            f"Igisubizo: Reba niba internet ikora, ongera ugerageze\n\n"
            f"📞 *Hamagara Support:*\n"
            f"• Twara: 0788 123 456\n"
            f"• MTN: 100\n"
            f"• Airtel: 111\n\n"
            f"⏰ *Igihe:* 24/7\n\n"
            f"Andika 'RETRY' kugira ngo wongeye ugerageze."
        )
        
        return TextMessage(
            to=self.customer.phone_number,
            body=body
        )
    
    def _log_payment_failure(self, failure_code: str, failure_reason: str):
        """
        Log payment failure for analytics and monitoring.
        """
        try:
            from ...models import UserEvent
            
            UserEvent.objects.create(
                customer=self.customer,
                event_type='payment_failed',
                metadata={
                    'failure_code': failure_code,
                    'failure_reason': failure_reason,
                    'payment_phone': self.get_context("payment_phone"),
                    'plan': self.get_context("selected_plan"),
                    'retry_count': self.get_context("retry_count", 0)
                }
            )
            
            # Alert if multiple failures
            retry_count = self.get_context("retry_count", 0)
            if retry_count >= 3:
                logger.warning(
                    f"Customer {self.customer.phone_number} has failed payment "
                    f"{retry_count} times. May need manual intervention."
                )
                
                # Send alert to support team
                from ...tasks import alert_support_team
                alert_support_team.delay(
                    customer_id=self.customer.id,
                    issue="Multiple payment failures",
                    retry_count=retry_count
                )
        
        except Exception as e:
            logger.error(f"Error logging payment failure: {e}", exc_info=True)
    
    
    def on_exit(self):
        """
        Cleanup when leaving failure state.
        """
        # Clear failure context if transitioning to payment input
        if self.get_context("retry_payment") or self.get_context("change_payment_number"):
            # Keep retry count but clear failure details
            self.update_context(
                payment_failure_code=None,
                payment_failure_reason=None
            )

