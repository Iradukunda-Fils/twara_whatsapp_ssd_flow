# states/exam_result.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage
from whatsapp_ussd.models import quiz


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
        # Prefer last_quiz_id in context, otherwise get latest by time
        last_quiz_id = self.get_context("last_quiz_id")
        if last_quiz_id:
            latest_quiz = quiz.objects.filter(id=last_quiz_id).first()
        else:
            latest_quiz = quiz.objects.filter(customer=self.customer).order_by("-taken").first()

        if not latest_quiz:
            return StateTransition(
                next_state="main_menu",
                context_updates={},
                message_override=TextMessage(
                    to=self.customer.phone_number, body="Nta manota yabonetse. Ongera ugerageze."
                ),
            )

        # Schedule async performance update through state scheduler
        from ...tasks import update_customer_performance, trigger_subscription_offer_task
        self.schedule_task(task_func=update_customer_performance, args=[self.customer.id])

        # Determine pass/fail
        marks = float(latest_quiz.marks or 0)
        passed = marks >= 60

        if passed:
            status_emoji = "✅"
            status_text = "*WATSINZE!*"
            motivation = "\n\n🎉 Murakoze cyane! Uratera imbere neza!"
        else:
            status_emoji = "❌"
            status_text = "*WATSINZWE*"
            motivation = "\n\n💪 Ntugire ubwoba, ongera ugerageze!"

        weak_areas = self._get_weak_categories(latest_quiz)

        body = (
            f"{status_emoji} {status_text}\n\n"
            f"📊 *Dore uko witwaye:*\n"
            f"Amanota: *{marks:.0f}%*\n"
        )

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

        # Update session/context
        self.update_context(
            last_quiz_id=latest_quiz.id,
            quiz_score=marks,
            quiz_passed=passed,
            weak_categories=weak_areas,
        )

        # If failed -> increment failure count and schedule offer (using schedule_task)
        if not passed:
            try:
                if self.ussd_user:
                    self.ussd_user.failed_exams_count = (self.ussd_user.failed_exams_count or 0) + 1
                    self.ussd_user.save(update_fields=["failed_exams_count"])
            except Exception:
                # don't fail the state if UA field isn't present or save fails
                pass

            self.schedule_task(
                task_func=trigger_subscription_offer_task,
                args=[self.customer.phone_number],
                kwargs={},
                countdown=15,
            )

        # Return message (no immediate next_state change here; process_input will control it)
        return TextMessage(to=self.customer.phone_number, body=body)

    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle user response after seeing results.
        """
        message_lower = user_message.lower().strip()
        passed = self.get_context("quiz_passed", False)

        if "ikindi" in message_lower or "retry" in message_lower:
            return StateTransition(next_state="exam_start", context_updates={"retry_count": self.get_context("retry_count", 0) + 1})

        if "menu" in message_lower:
            return StateTransition(next_state="main_menu", context_updates={})

        if not passed:
            # failed -> waiting for subscription offer
            return StateTransition(next_state="waiting_for_offer", context_updates={})

        return StateTransition(
            next_state="main_menu",
            context_updates={},
            message_override=TextMessage(to=self.customer.phone_number, body="Andika 'MENU' kugira ngo usubire ku menu."),
        )

    def _get_weak_categories(self, quiz_obj) -> list:
        categories = {
            "amategekoMarks": "Amategeko",
            "KugendaMarks": "Kugenda mu muhanda",
            "IbinyabizigaMarks": "Ibinyabiziga",
            "IbimenyetsoMarks": "Ibimenyetso",
            "IbirangaMarks": "Ibiranga",
            "ImigenzurireMarks": "Imigenzurire",
        }
        weak = []
        for field, name in categories.items():
            score = getattr(quiz_obj, field, None)
            if score is not None:
                try:
                    if float(score) < 60:
                        weak.append(name)
                except Exception:
                    continue
        return weak
