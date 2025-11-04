# states/exam_start.py
from .base import BaseStateHandler, StateTransition
from whatsapp import InteractiveMessage, TextMessage
from whatsapp_ussd.models import quiz
from django.utils import timezone


class ExamStartState(BaseStateHandler):
    """
    Confirm exam start and provide instructions.
    """

    state_name = "exam_start"
    display_name = "Exam Start"
    requires_auth = True

    def on_enter(self) -> 'WhatsAppMessage':
        """
        Show exam instructions with start button.
        """
        has_subscription = self.customer.get_active_transactions().exists()
        total_exams = quiz.objects.filter(customer=self.customer).count()

        if total_exams == 0:
            # First free exam
            body = (
                f"Murakoze {self.customer.name}!\n\n"
                f"Iki ni ikizamini cyawe cya mbere (kubuntu).\n\n"
                f"📋 *Amabwiriza:*\n"
                f"• Ibibazo 40\n"
                f"• Igihe: 18 iminota\n"
                f"• Gutsinda: 60%+\n\n"
                f"Kanda aho hasi utangire!"
            )
        elif has_subscription:
            # Active subscriber
            performance = getattr(self.customer, "performance", None)
            if performance and performance.avg_marks:
                body = (
                    f"Murakomeye {self.customer.name}!\n\n"
                    f"Amanota yawe yo kuruhuka: {performance.avg_marks:.0f}%\n\n"
                    f"📋 Ikizamini gishya:\n"
                    f"• Ibibazo 40\n"
                    f"• Igihe: 18 iminota\n\n"
                    f"Witegure gutsinda! 💪"
                )
            else:
                body = (
                    f"Murakomeye {self.customer.name}!\n\n"
                    f"📋 Ikizamini:\n"
                    f"• Ibibazo 40\n"
                    f"• Igihe: 18 iminota\n"
                    f"• Gutsinda: 60%+\n\n"
                    f"Kanda aho hasi utangire!"
                )
        else:
            # No subscription
            return StateTransition(
                next_state="subscription_offer",
                context_updates={"offer_reason": "no_free_exams"},
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body=(
                        f"Murakoze {self.customer.name}!\n\n"
                        f"Wakoreye ikizamini cya mbere kubuntu.\n\n"
                        f"Kugira ngo ukomeze kwitegura, "
                        f"ugomba kugura code yo kwiga."
                    ),
                ),
            )

        # Create WhatsApp interactive message
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="IKIZAMINI",
            footer="Twara © 2024",
        )

        message.add_reply_button("start_exam", "🚀 Tangira")
        message.add_reply_button("cancel", "❌ Hagarika")

        return message

    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle start or cancel actions.
        """
        choice = user_message.lower().strip()

        if choice == "start_exam" or "tangira" in choice:
            # Create quiz session asynchronously
            from ...tasks import create_exam_session

            self.schedule_task(task_func=create_exam_session, args=[self.customer.id])

            return StateTransition(
                next_state="exam_in_progress",
                context_updates={
                    "exam_start_time": timezone.now().isoformat(),
                },
                celery_tasks=self.celery_tasks
            )

        elif choice == "cancel" or "hagarika" in choice:
            return StateTransition(
                next_state="main_menu",
                message_override=TextMessage(
                    to=self.customer.phone_number,
                    body="Ikizamini cyahagaritswe. Uza kureba igihe cyose.",
                ),
            )

        # Invalid response
        return StateTransition(
            next_state=self.state_name,
            message_override=TextMessage(
                to=self.customer.phone_number,
                body="Kanda *'Tangira'* cyangwa *'Hagarika'* kugira ngo ukomeze.",
            ),
        )
