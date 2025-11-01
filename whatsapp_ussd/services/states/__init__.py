# states/__init__.py
"""
State handlers registry.
Import all state handlers here for auto-discovery.
"""


from .progress_report import WeeklyProgressReportState
from .welcome import WelcomeState
from .exam_result import ExamResultState
from .name_capture import NameCaptureState
from .main_menu import MainMenuState
from .exam_start import ExamStartState
from .exam_in_progress import ExamInProgressState
from .subscription_offer import SubscriptionOfferState
from .plan_selection import PlanSelectionState
from .plan_confirmation import PlanConfirmationState
from .payment_input import PaymentInputState
from .payment_pending import PaymentPendingState
from .payment_success import PaymentSuccessState
# from .payment_failed import PaymentFailedState
from .buy_code_direct import BuyCodeDirectState
from .police_registration_info import PoliceRegistrationInfoState

# Registry of all state handlers
ALL_STATE_HANDLERS = [
    WelcomeState,
    NameCaptureState,
    MainMenuState,
    ExamStartState,
    ExamInProgressState,
    ExamResultState,
    SubscriptionOfferState,
    PlanSelectionState,
    PlanConfirmationState,
    PaymentInputState,
    PaymentPendingState,
    PaymentSuccessState,
    # PaymentFailedState,
    WeeklyProgressReportState,
    BuyCodeDirectState,
    PoliceRegistrationInfoState,
]

__all__ = [
    'WelcomeState',
    'NameCaptureState',
    'MainMenuState',
    'ExamStartState',
    'ExamInProgressState',
    'ExamResultState',
    'SubscriptionOfferState',
    'PlanSelectionState',
    'PlanConfirmationState',
    'PaymentInputState',
    'PaymentPendingState',
    'PaymentSuccessState',
    'PaymentFailedState',
    'BuyCodeDirectState',
    'PoliceRegistrationInfoState',
    'ALL_STATE_HANDLERS',
]
