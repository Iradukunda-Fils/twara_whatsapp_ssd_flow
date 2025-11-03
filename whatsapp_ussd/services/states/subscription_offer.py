# states/subscription_offer.py
from .base import BaseStateHandler, StateTransition
from whatsapp import InteractiveMessage, TextMessage

class SubscriptionOfferState(BaseStateHandler):
    """
    Offer subscription to failed exam users.
    Triggered 15 seconds after exam result.
    """
    
    state_name = "subscription_offer"
    display_name = "Subscription Offer"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Present subscription offer with benefits.
        """
        # Personalize based on performance
        weak_areas = self.get_context("weak_categories", [])
        
        if weak_areas:
            personalization = (
                f"Twabonye ko ukeneye kongera imbaraga muri: "
                f"{', '.join(weak_areas[:2])}.\n\n"
            )
        else:
            personalization = ""
        
        body = (
            f"{personalization}"
            f"💡 *Ese waruziko wakwihugura buri munsi ukazamura "
            f"amahirwe yawe yo gutsinda ikizamini utigoye?*\n\n"
            f"✅ Kora ibizamini byinshi nk'uko ushaka\n"
            f"✅ Raporo y'iterambere buri minsi 3\n"
            f"✅ Abakoresha Twara batsinda ku 95%\n\n"
            f"*Urabiishaka?*"
        )
        
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="WITEGURE NEZA",
            footer="Gutsinda byoroshye"
        )
        
        message.add_reply_button("accept_offer", "✅ Yego")
        message.add_reply_button("decline_offer", "❌ Oya")
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle acceptance or decline.
        """
        choice = user_message.lower().strip()
        
        if choice == "accept_offer" or "yego" in choice:
            # User accepted, show plans
            return StateTransition(
                next_state="plan_selection",
                context_updates={"offer_accepted": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Uhisemo neza! 🎉"
                )
            )
        
        elif choice == "decline_offer" or "oya" in choice:
            # User declined
            return StateTransition(
                next_state="main_menu",
                context_updates={"offer_declined": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        "Murakoze. Uza kugura code igihe cyose ukeneye.\n"
                        "Andika 'MENU' kugira ngo usubire ku menu."
                    )
                )
            )
        
        # Invalid choice
        return StateTransition(
            next_state="subscription_offer",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Kanda 'Yego' cyangwa 'Oya'."
            )
        )
    
