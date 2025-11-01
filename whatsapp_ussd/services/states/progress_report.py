# states/progress_report.py
from typing import List
from datetime import timedelta
from django.utils import timezone
from django.db.models import Avg

from ..core.session import UserSession
from ..states.base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, InteractiveMessage, WhatsAppMessage
from whatsapp_ussd.models import quiz

class WeeklyProgressReportState(BaseStateHandler):
    """
    Sends weekly performance summary with actionable insights.
    """
    
    state_name = "weekly_progress_report"
    display_name = "Weekly Progress Report"
    requires_auth = True
    
    def on_enter(self) -> WhatsAppMessage:
        """
        Generate personalized report with charts and recommendations.
        Uses UssdUser directly (which inherits from Customer).
        """
        # Since UssdUser inherits from Customer, self.ussd_user IS a Customer
        ussd_user = self.ussd_user
        
        # Get performance data (UssdUser has performance relationship via Customer)
        performance = ussd_user.performance
        
        # Get this week's quizzes (UssdUser can be used as Customer in ForeignKey)
        week_start = timezone.now() - timedelta(days=7)
        weekly_quizzes = quiz.objects.filter(
            customer=ussd_user,  # UssdUser IS a Customer
            taken__gte=week_start
        ).order_by('taken')
        
        if not weekly_quizzes.exists():
            return TextMessage(
                to=ussd_user.phone_number,
                body=f"Mwaramutse {ussd_user.name}!\n\n"
                     f"Ntago wakora ikizamini muri iki cyumweru.\n"
                     f"Kanda hano kugira ngo utangire: 🚀"
            )
        
        # Calculate weekly stats
        weekly_avg = weekly_quizzes.aggregate(Avg('marks'))['marks__avg']
        total_attempts = weekly_quizzes.count()
        passed_count = weekly_quizzes.filter(marks__gte=60).count()
        
        # Trend analysis
        if performance and performance.avg_marks:
            improvement = weekly_avg - performance.avg_marks
            trend_emoji = "📈" if improvement > 0 else "📉"
            trend_text = f"({improvement:+.1f}% from last period)"
        else:
            trend_emoji = "📊"
            trend_text = ""
        
        # Build report
        report = f"📊 *RAPORO YICYUMWERU*\n\n"
        report += f"Mwaramutse {ussd_user.name}!\n\n"
        report += f"{trend_emoji} *Amanota y'iki cyumweru:* {weekly_avg:.1f}% {trend_text}\n"
        report += f"✅ *Ibizamini byakozwe:* {total_attempts}\n"
        report += f"🎯 *Watsinze:* {passed_count}/{total_attempts}\n\n"
        
        # Weak areas
        weak_categories = self._identify_weak_areas(weekly_quizzes)
        if weak_categories:
            report += f"🎓 *Witeze kuri:*\n"
            for category in weak_categories[:3]:
                report += f"  • {category}\n"
        
        # Motivational message
        if weekly_avg >= 80:
            report += f"\n🌟 Urimo ukora neza cyane! Komeza!"
        elif weekly_avg >= 60:
            report += f"\n💪 Urimo ukora neza! Ongera uteze imbere!"
        else:
            report += f"\n🎯 Kongera imbaraga! Uzagerayo!"
        
        # Call to action
        report += f"\n\n👉 Kora ikindi kizamini none!"
        
        return InteractiveMessage(
            to=ussd_user.phone_number,
            body=report,
            header="RAPORO Y'ICYUMWERU"
        ).add_reply_button("start_quiz", "🚀 Tangira ikizamini") \
         .add_reply_button("view_details", "📈 Reba ibisobanuro")
    
    def process_input(self, user_message: str) -> StateTransition:
        """Handle user response to report"""
        
        if user_message == "start_quiz":
            return StateTransition(
                next_state="exam",
                context_updates={"triggered_by": "weekly_report"}
            )
        
        elif user_message == "view_details":
            return StateTransition(
                next_state="detailed_performance",
                context_updates={}
            )
        
        # Default: return to menu
        return StateTransition(
            next_state="main_menu",
            context_updates={}
        )
    
    def get_allowed_transitions(self) -> List[str]:
        return ["exam", "detailed_performance", "main_menu"]
    
    def _identify_weak_areas(self, quizzes) -> List[str]:
        """Identify categories with <70% average"""
        categories = {
            'amategekoMarks': 'Amategeko',
            'KugendaMarks': 'Kugenda mu muhanda',
            'IbinyabizigaMarks': 'Ibinyabiziga',
            'IbimenyetsoMarks': 'Ibimenyetso',
        }
        
        weak = []
        for field, name in categories.items():
            avg = quizzes.aggregate(Avg(field))[f'{field}__avg']
            if avg and avg < 70:
                weak.append(f"{name} ({avg:.0f}%)")
        
        return weak