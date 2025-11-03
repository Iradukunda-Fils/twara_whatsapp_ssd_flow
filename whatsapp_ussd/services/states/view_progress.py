# states/view_progress.py
from .base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, InteractiveMessage
from whatsapp_ussd.models import quiz

class ViewProgressState(BaseStateHandler):
    """
    Show user's learning progress and statistics.
    """
    
    state_name = "view_progress"
    display_name = "View Progress"
    requires_auth = True
    
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Display performance statistics.
        """
        performance = self.customer.performance
        
        if not performance or performance.total_attempts == 0:
            body = (
                f"📊 *ITERAMBERE RYAWE*\n\n"
                f"Nturakora ikizamini.\n"
                f"Tangira ikizamini cya mbere kugira ngo urebe iterambere ryawe!"
            )
            
            message = InteractiveMessage(
                to=self.customer.phone_number,
                body=body,
                header="PROGRESS"
            )
            message.add_reply_button("start_exam", "🚀 Tangira ikizamini")
            message.add_reply_button("back", "🏠 Subira")
            
            return message
        
        # Calculate statistics
        avg_score = float(performance.avg_marks or 0)
        total_attempts = performance.total_attempts
        
        # Get pass rate
        passed_exams = quiz.objects.filter(
            customer=self.customer,
            marks__gte=60
        ).count()
        pass_rate = (passed_exams / total_attempts * 100) if total_attempts > 0 else 0
        
        # Determine trend (compare recent vs overall performance)
        # Note: is_improving is not a field, calculate trend from recent quizzes
        recent_quizzes = quiz.objects.filter(
            customer=self.customer
        ).order_by('-taken')[:3]
        
        if recent_quizzes.exists():
            recent_avg = sum(float(q.marks or 0) for q in recent_quizzes) / len(recent_quizzes)
            if recent_avg > avg_score:
                trend = "📈 Urimo ukora neza!"
                trend_emoji = "✅"
            else:
                trend = "📉 Kongera imbaraga!"
                trend_emoji = "💪"
        else:
            trend = "📊 Tangira ikizamini!"
            trend_emoji = "🚀"
        
        # Build progress report
        body = (
            f"📊 *ITERAMBERE RYAWE*\n\n"
            f"Mwaramutse {self.customer.name}!\n\n"
            f"🎯 *Amanota yo kuruhuka:*\n"
            f"{avg_score:.1f}%\n\n"
            f"📝 *Ibizamini byakozwe:*\n"
            f"{total_attempts} exams\n\n"
            f"✅ *Gutsinda rate:*\n"
            f"{pass_rate:.1f}%\n\n"
            f"{trend_emoji} *Trend:*\n"
            f"{trend}\n\n"
            f"📚 *Ibice byiza:*\n"
        )
        
        # Show best categories
        categories = [
            ('Amategeko', performance.avg_amategekoMarks),
            ('Kugenda', performance.avg_KugendaMarks),
            ('Ibinyabiziga', performance.avg_IbinyabizigaMarks),
            ('Ibimenyetso', performance.avg_IbimenyetsoMarks),
        ]
        
        # Sort by score (highest first)
        sorted_cats = sorted(categories, key=lambda x: x[1] or 0, reverse=True)
        
        for cat_name, cat_score in sorted_cats[:3]:
            if cat_score:
                body += f"• {cat_name}: {cat_score:.0f}%\n"
        
        # Show weak categories
        weak_cats = [c for c in categories if c[1] and c[1] < 60]
        if weak_cats:
            body += f"\n🎯 *Ukwiye kongera imbaraga:*\n"
            for cat_name, cat_score in weak_cats:
                body += f"• {cat_name}: {cat_score:.0f}%\n"
        
        message = InteractiveMessage(
            to=self.customer.phone_number,
            body=body,
            header="YOUR PROGRESS",
            footer="Keep learning! 📚"
        )
        
        message.add_reply_button("take_exam", "🚀 Kora ikizamini")
        message.add_reply_button("back_menu", "🏠 Menu")
        
        return message
    
    def process_input(self, user_message: str) -> StateTransition:
        """
        Handle user actions after viewing progress.
        """
        choice = user_message.lower().strip()
        
        if choice == "take_exam" or "ikizamini" in choice:
            return StateTransition(
                next_state="exam_start",
                context_updates={"from_progress": True}
            )
        
        elif choice == "back_menu" or "menu" in choice:
            return StateTransition(
                next_state="main_menu",
                context_updates={}
            )
        
        # Default
        return StateTransition(
            next_state="main_menu",
            context_updates={}
        )
    


