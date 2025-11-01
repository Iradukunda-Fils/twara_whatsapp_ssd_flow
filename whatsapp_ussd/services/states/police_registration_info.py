# states/police_registration_info.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, InteractiveMessage

class PoliceRegistrationInfoState(BaseStateHandler):
    """
    Provide information about registering for police exam.
    """
    
    state_name = "police_registration_info"
    display_name = "Police Registration Info"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show registration instructions.
        """
        body = (
            f"🚓 *KWIYANDIKISHA KURI POLICE*\n\n"
            f"Kugira ngo wiyandikishe ikizamini cya Police:\n\n"
            f"📍 *Aho ugana:*\n"
            f"• RURA Office - Kigali\n"
            f"• District Offices\n\n"
            f"📋 *Ibyangombwa:*\n"
            f"• Indangamuntu (ID)\n"
            f"• Ifoto 2 (passport size)\n"
            f"• Medical Certificate\n"
            f"• 50,000 RWF (registration fee)\n\n"
            f"⏰ *Igihe:*\n"
            f"Ku wa mbere - Ku wa gatanu\n"
            f"8:00 AM - 5:00 PM\n\n"
            f"📞 *Ubufasha:*\n"
            f"Tel: 4729\n"
            f"Email: info@rura.rw\n\n"
            f"💡 *Icyabanza:*\n"
            f"Witegure ikizamini kuri Twara mbere yo "
            f"kwiyandikisha! 95% y'abakoresha Twara batsinda."
        )
        
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="POLICE INFO",
            footer="Twara - Kwitegura neza"
        )
        
        message.add_reply_button("start_prep", "📚 Tangira kwitegura")
        message.add_reply_button("back_menu", "🏠 Subira ku menu")
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle user action after viewing info.
        """
        choice = user_message.lower().strip()
        
        if choice == "start_prep" or "tangira" in choice or "witegura" in choice:
            # Check if user has subscription
            has_sub = self.customer.get_active_transactions().exists()
            
            if has_sub:
                return StateTransition(
                    next_state="exam_start",
                    context_updates={"from_police_info": True}
                )
            else:
                return StateTransition(
                    next_state="plan_selection",
                    context_updates={"from_police_info": True},
                    message_override=TextMessage(
                        to=self.customer.phone_number,
                        body="Hitamo plan yo kwitegura:"
                    )
                )
        
        elif choice == "back_menu" or "menu" in choice:
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        # Default: return to menu
        return StateTransition(
            next_state="main_menu",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Andika 'MENU' kugira ngo usubire ku menu."
            )
        )
    
    def get_allowed_transitions(self) -> list:
        return ["exam_start", "plan_selection", "main_menu"]