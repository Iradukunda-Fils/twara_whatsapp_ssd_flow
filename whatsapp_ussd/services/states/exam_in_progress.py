# states/exam_in_progress.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage
from whatsapp_ussd.models import quiz

class ExamInProgressState(BaseStateHandler):
    """
    User is currently taking exam (on external platform).
    This state waits for exam completion webhook.
    """
    
    state_name = "exam_in_progress"
    display_name = "Exam In Progress"
    requires_auth = True
    timeout_seconds = 1800  # 30 minutes max
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Provide exam link and wait.
        """
        # Get or create quiz session
        quiz_id = self.get_context("quiz_id")
        
        if not quiz_id:
            # This should have been created in exam_start
            # Fallback: create here
            new_quiz = quiz.objects.create(
                customer=self.customer,
                language=getattr(self.ussd_user, 'preferred_language', 'rw')
            )
            quiz_id = new_quiz.id
            self.update_context(quiz_id=quiz_id)
        
        # Generate exam link
        exam_url = f"https://twara.rw/exam/{quiz_id}"
        
        return TextMessage(
            to=self.customer.phone_number,
            body=(
                f"🎯 *IKIZAMINI CYATANGIYE*\n\n"
                f"Kanda kuri link ikurikira:\n"
                f"{exam_url}\n\n"
                f"⏱ Igihe: 18 iminota\n"
                f"📝 Ibibazo: 40\n\n"
                f"Numara, uzasubira hano kugira ngo "
                f"ubone amanota yawe. Amahirwe! 🍀"
            ),
            preview_url=True
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Wait for exam completion (handled by webhook).
        User can cancel or request help.
        """
        message_lower = user_message.lower().strip()
        
        if "hagarika" in message_lower or "cancel" in message_lower:
            return StateTransition(
                next_state="main_menu",
                context_updates={"exam_cancelled": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Ikizamini cyahagaritswe. Uza kureba igihe cyose."
                )
            )
        
        elif "help" in message_lower or "ubufasha" in message_lower:
            return StateTransition(
                next_state="exam_in_progress",  # Stay in state
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        "🆘 *UBUFASHA*\n\n"
                        "Niba ufite ikibazo:\n"
                        "1. Reba niba internet ikora\n"
                        "2. Subiramo link\n"
                        "3. Hamagara: 0788 123 456\n\n"
                        "Komeza ikizamini!"
                    )
                )
            )
        
        # Default: remind user to complete exam
        return StateTransition(
            next_state="exam_in_progress",
            context_updates={},
            message_override=TextMessage(
                to=self.customer.phone_number,
                body=(
                    "Ikizamini kirakomeje.\n"
                    "Numara, uza kubona amanota yawe hano."
                )
            )
        )
    
    def get_allowed_transitions(self) -> list:
        return ["exam_result", "main_menu", "exam_in_progress"]
    
    def on_exit(self):
        """Clear temporary exam data"""
        self.update_context(exam_start_time=None)