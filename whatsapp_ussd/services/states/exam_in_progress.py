# states/exam_in_progress.py
from django.utils import timezone
from datetime import timedelta
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage
from whatsapp_ussd.models import quiz


class ExamInProgressState(BaseStateHandler):
    """
    User is currently taking exam (on external platform).
    This state waits for exam completion webhook or time expiration.
    """

    state_name = "exam_in_progress"
    display_name = "Exam In Progress"
    requires_auth = True
    timeout_seconds = 1800  # 30 minutes

    def on_enter(self):
        """
        Send exam link and start tracking.
        """
        quiz_id = self.get_context("quiz_id")

        if not quiz_id:
            new_quiz = quiz.objects.create(
                customer=self.customer,
                language=getattr(self.ussd_user, "preferred_language", "rw"),
            )
            quiz_id = new_quiz.id
            self.update_context(quiz_id=quiz_id)

        exam_url = f"https://twara.rw/exam/{quiz_id}"
        self.update_context(exam_start_time=timezone.now())

        return TextMessage(
            to=self.customer.phone_number,
            body=(
                f"🎯 *IKIZAMINI CYATANGIYE*\n\n"
                f"Kanda kuri link ikurikira:\n{exam_url}\n\n"
                f"⏱ Igihe: 18 iminota\n📝 Ibibazo: 40\n\n"
                f"Numara, uzasubira hano kugira ngo ubone amanota yawe."
            ),
            preview_url=True,
        )

    def process_input(self, user_message: str) -> StateTransition:
        """
        Detect if exam finished, help, cancel, or timeout.
        """
        msg = user_message.lower().strip()

        if "cancel" in msg or "hagarika" in msg:
            return StateTransition(
                next_state="main_menu",
                context_updates={"exam_cancelled": True},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Ikizamini cyahagaritswe. Uza kugisubiramo nyuma.",
                ),
            )

        if "help" in msg or "ubufasha" in msg:
            return StateTransition(
                next_state=self.state_name,
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        "🆘 Ubufasha:\n"
                        "• Reba niba internet yawe ikora.\n"
                        "• Subiramo link y'ikizamini.\n"
                        "• Hamagara: 0788 123 456.\n\n"
                        "Komeza ikizamini cyawe!"
                    ),
                ),
            )

        quiz_id = self.get_context("quiz_id")
        if quiz_id:
            q = quiz.objects.filter(id=quiz_id).first()
            if q and q.marks is not None:
                # Exam done!
                return StateTransition(
                    next_state="exam_result",
                    context_updates={"exam_completed": True},
                    message_override=TextMessage(
                        to=self.customer.phone_number,
                        body="🎉 Ikizamini kirarangiye! Reba amanota yawe 👇",
                    ),
                )

        start_time = self.get_context("exam_start_time")
        if start_time:
            elapsed = timezone.now() - start_time
            if elapsed > timedelta(seconds=self.timeout_seconds):
                return StateTransition(
                    next_state="exam_result",
                    context_updates={"exam_timed_out": True},
                    message_override=TextMessage(
                        to=self.customer.phone_number,
                        body="⏰ Igihe cy'ikizamini kirarangiye. Reba amanota yawe.",
                    ),
                )

        return StateTransition(
            next_state=self.state_name,
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Ikizamini kirakomeje. Numara, uzabona amanota yawe hano.",
            ),
        )

    def on_exit(self):
        """Clear temporary exam data."""
        self.update_context(exam_start_time=None)
