# states/exam_result.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage
from whatsapp_ussd.models import quiz
from decimal import Decimal

class ExamResultState(BaseStateHandler):
    """
    Display exam results with performance feedback.
    Trigger subscription offer after 15s if failed.
    """
    
    state_name = "exam_result"
    display_name = "Exam Results"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show exam results with detailed feedback.
        """
        # Get latest quiz
        latest_quiz = quiz.objects.filter(
            customer=self.customer
        ).order_by('-taken').first()
        
        if not latest_quiz:
            # No quiz found, redirect to menu
            return StateTransition(
                next_state="main_menu",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Nta manota yabonetse. Ongera ugerageze."
                )
            )
        
        # Update performance metrics (async)
        from whatsapp_ussd.tasks import update_customer_performance
        update_customer_performance.delay(self.customer.id)
        
        # Determine pass/fail
        marks = float(latest_quiz.marks)
        passed = marks >= 60
        
        # Build result message
        if passed:
            status_emoji = "✅"
            status_text = "*WATSINZE!*"
            motivation = "\n\n🎉 Murakoze cyane! Uratera imbere neza!"
        else:
            status_emoji = "❌"
            status_text = "*WATSINZWE*"
            motivation = "\n\n💪 Ntugire ubwoba, ongera ugerageze!"
        
        # Identify weak categories
        weak_areas = self._get_weak_categories(latest_quiz)
        
        body = (
            f"{status_emoji} {status_text}\n\n"
            f"📊 *Dore uko witwaye:*\n"
            f"Amanota: *{marks:.0f}%*\n"
        )
        
        # Add category breakdown
        body += f"\n📚 *Ibice:*\n"
        body += f"• Amategeko: {latest_quiz.amategekoMarks or 0:.0f}%\n"
        body += f"• Kugenda: {latest_quiz.KugendaMarks or 0:.0f}%\n"
        body += f"• Ibinyabiziga: {latest_quiz.IbinyabizigaMarks or 0:.0f}%\n"
        body += f"• Ibimenyetso: {latest_quiz.IbimenyetsoMarks or 0:.0f}%\n"
        
        if weak_areas:
            body += f"\n🎯 *Ukwiye kongera imbaraga muri:*\n"
            for area in weak_areas:
                body += f"• {area}\n"
        
        body += motivation
        
        # Store context for next state
        self.update_context(
            last_quiz_id=latest_quiz.id,
            quiz_score=marks,
            quiz_passed=passed,
            weak_categories=weak_areas
        )
        
        # Schedule delayed offer if failed
        if not passed:
            # Increment failure count (on UssdUser, not Customer)
            self.ussd_user.failed_exams_count = (self.ussd_user.failed_exams_count or 0) + 1
            self.ussd_user.save(update_fields=['failed_exams_count'])
            
            # Schedule subscription offer after 15 seconds
            from whatsapp_ussd.tasks import trigger_subscription_offer_task
            trigger_subscription_offer_task.apply_async(
                args=[self.customer.phone_number],
                countdown=15
            )
        
        return TextMessage(
            to=self.customer.phone_number,
            body=body
        )
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle user response after seeing results.
        """
        message_lower = user_message.lower().strip()
        
        # Check if passed
        passed = self.get_context("quiz_passed", False)
        
        if "ikindi" in message_lower or "retry" in message_lower:
            # User wants to retake exam
            return StateTransition(
                next_state="exam_start",
                context_updates={"retry_count": self.get_context("retry_count", 0) + 1}
            )
        
        elif "menu" in message_lower:
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        elif not passed:
            # Failed exam, wait for timed offer
            return StateTransition(
                next_state="waiting_for_offer",
                context_updates={}
            )
        
        else:
            # Passed, return to menu
            return StateTransition(
                next_state="main_menu",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Andika 'MENU' kugira ngo usubire ku menu."
                )
            )
    
    def _get_weak_categories(self, quiz_obj) -> list:
        """
        Identify categories with < 60% score.
        """
        categories = {
            'amategekoMarks': 'Amategeko',
            'KugendaMarks': 'Kugenda mu muhanda',
            'IbinyabizigaMarks': 'Ibinyabiziga',
            'IbimenyetsoMarks': 'Ibimenyetso',
            'IbirangaMarks': 'Ibiranga',
            'ImigenzurireMarks': 'Imigenzurire',
        }
        
        weak = []
        for field, name in categories.items():
            score = getattr(quiz_obj, field, None)
            if score and float(score) < 60:
                weak.append(name)
        
        return weak
    
    def get_allowed_transitions(self) -> list:
        return ["waiting_for_offer", "exam_start", "main_menu", "subscription_offer"]