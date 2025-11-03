
# states/subscription_status.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, InteractiveMessage
from datetime import timedelta
from django.utils import timezone
from whatsapp_ussd.models import quiz

class SubscriptionStatusState(BaseStateHandler):
    """
    Show subscription details and renewal options.
    """
    
    state_name = "subscription_status"
    display_name = "Subscription Status"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Display subscription information.
        """
        active_subs = self.customer.get_active_transactions()
        
        if not active_subs.exists():
            # No active subscription
            body = (
                f"📦 *SUBSCRIPTION YAWE*\n\n"
                f"Nta subscription ukora.\n\n"
                f"Gura code yo kwitegura:\n"
                f"• Ibizamini byinshi\n"
                f"• Raporo y'iterambere\n"
                f"• 95% success rate\n\n"
                f"Ushaka kugura?"
            )
            
            message = InteractiveMessage(
                to=self.customer.phone_number,
                body=body,
                header="NO SUBSCRIPTION"
            )
            message.add_reply_button("buy_now", "🛒 Gura code")
            message.add_reply_button("back", "🏠 Subira")
            
            return message
        
        # Get most recent active subscription
        latest_sub = active_subs.order_by('-paid_on').first()
        
        # Calculate expiration
        expiration_date = latest_sub.paid_on + timedelta(days=latest_sub.expiration)
        days_left = (expiration_date - timezone.now()).days
        
        # Status emoji
        if days_left > 7:
            status_emoji = "✅"
            status_text = "ACTIVE"
        elif days_left > 3:
            status_emoji = "⚠️"
            status_text = "EXPIRING SOON"
        else:
            status_emoji = "🔴"
            status_text = "EXPIRES SOON!"
        
        # Count exams taken
        exams_with_sub = quiz.objects.filter(
            customer=self.customer,
            taken__gte=latest_sub.paid_on
        ).count()
        
        body = (
            f"📦 *SUBSCRIPTION YAWE*\n\n"
            f"{status_emoji} Status: *{status_text}*\n\n"
            f"🔐 Code: ```{latest_sub.access_code}```\n"
            f"💰 Amount: {latest_sub.amount_paid:,} RWF\n"
            f"📅 Started: {latest_sub.paid_on.strftime('%Y-%m-%d')}\n"
            f"⏰ Expires: {expiration_date.strftime('%Y-%m-%d')}\n"
            f"📊 Days left: *{days_left} days*\n\n"
            f"📝 *Ibikorwa:*\n"
            f"• Exams taken: {exams_with_sub}\n"
            f"• Unlimited exams ✅\n"
            f"• Progress reports ✅\n"
            f"• 24/7 support ✅\n"
        )
        
        # Add renewal reminder if expiring soon
        if days_left <= 7:
            body += f"\n⚠️ Subscription yawe izarangira vuba!\nGura code nshya kugira ngo ukomeze."
        
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="SUBSCRIPTION INFO",
            footer=f"Twara © {latest_sub.access_code}"
        )
        
        if days_left <= 7:
            message.add_reply_button("renew", "🔄 Renew")
        
        message.add_reply_button("back_menu", "🏠 Menu")
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle renewal or navigation.
        """
        choice = user_message.lower().strip()
        
        if choice == "buy_now" or choice == "renew" or "gura" in choice:
            return StateTransition(
                next_state="plan_selection",
                context_updates={"renewal": True}
            )
        
        elif choice == "back" or choice == "back_menu" or "menu" in choice:
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        # Default
        return StateTransition(
            next_state="main_menu",
            context_updates={}
        )
    
