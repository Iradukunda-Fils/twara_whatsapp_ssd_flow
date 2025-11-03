# states/plan_confirmation.py
from .base import BaseStateHandler, StateTransition
from whatsapp import InteractiveMessage, TextMessage

class PlanConfirmationState(BaseStateHandler):
    """
    Confirm selected plan with detailed benefits.
    """
    
    state_name = "plan_confirmation"
    display_name = "Plan Confirmation"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show plan details and confirm purchase.
        """
        plan = self.get_context("selected_plan")
        
        if not plan:
            # No plan selected, go back
            return StateTransition(
                next_state="plan_selection",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Hitamo plan mbere."
                )
            )
        
        # Build detailed description
        body = (
            f"📦 *{plan['name'].upper()} PLAN*\n\n"
            f"💰 Igiciro: *{plan['price']:,} RWF*\n"
            f"⏱ Igihe: *{plan['days']} iminsi*\n\n"
            f"✅ *Ibikorwa:*\n"
            f"• Ibizamini bitagira ingano\n"
            f"• Raporo y'iterambere buri minsi 3\n"
            f"• Ubufasha bwa 24/7\n"
            f"• Ibibazo byose 40 (6 ibice)\n"
        )
        
        # Add success rate
        if plan['days'] >= 30:
            body += f"\n🎯 95% y'abakoresha iyi plan batsinda!\n"
        
        body += (
            f"\n💳 *Ukuntu wishyura:*\n"
            f"• MTN Mobile Money\n"
            f"• Airtel Money\n\n"
            f"Komeza cyangwa hagarika?"
        )
        
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="EMEZA PLAN",
            footer=f"Twara © {plan['price']:,}RWF"
        )
        
        message.add_reply_button("confirm_purchase", "✅ Komeza")
        message.add_reply_button("cancel_purchase", "❌ Hagarika")
        message.add_reply_button("change_plan", "🔄 Hindura")
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle confirmation or cancellation.
        """
        choice = user_message.lower().strip()
        
        if choice == "confirm_purchase" or "komeza" in choice:
            # Proceed to payment
            return StateTransition(
                next_state="payment_input",
                context_updates={"purchase_confirmed": True}
            )
        
        elif choice == "cancel_purchase" or "hagarika" in choice:
            # Cancel and return to menu
            return StateTransition(
                next_state="main_menu",
                context_updates={"purchase_cancelled": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        "Igura ryahagaritswe.\n"
                        "Uza kugura igihe cyose ukeneye."
                    )
                )
            )
        
        elif choice == "change_plan" or "hindura" in choice:
            # Go back to plan selection
            return StateTransition(
                next_state="plan_selection",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Hitamo plan izindi."
                )
            )
        
        # Invalid choice
        return StateTransition(
            next_state="plan_confirmation",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Kanda 'Komeza', 'Hagarika' cyangwa 'Hindura'."
            )
        )
    
