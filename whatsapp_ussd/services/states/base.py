# states/base.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from ..core.session import UserSession
from whatsapp import *

@dataclass
class StateTransition:
    """Represents the result of processing user input"""
    next_state: str
    context_updates: Dict[str, Any] = None
    celery_tasks: List[tuple] = None  # [(task_func, args, kwargs, countdown)]
    message_override: Optional['WhatsAppMessage'] = None
    validation_errors: List[str] = None

    def __post_init__(self):
        if self.context_updates is None:
            self.context_updates = {}
        if self.celery_tasks is None:
            self.celery_tasks = []
        if self.validation_errors is None:
            self.validation_errors = []


class BaseStateHandler(ABC):
    """
    Abstract base for all conversation states.
    Each state must implement entry, processing, and validation logic.
    """
    
    # State metadata
    state_name: str  # Unique identifier (e.g., "exam_result", "payment_input")
    display_name: str  # Human-readable (for admin dashboard)
    timeout_seconds: int = 3600  # Session timeout
    requires_auth: bool = True  # Whether user must be registered
    
    def __init__(self, session: 'UserSession'):
        self.session = session
        self.ussd_user = session.customer  # This is UssdUser instance
        self.context = session.context
    
    @property
    def customer(self):
        """
        Property to access the user.
        Since UssdUser inherits from Customer, this returns the UssdUser instance
        (which IS a Customer via inheritance).
        """
        # UssdUser inherits from Customer, so it IS a Customer
        return self.ussd_user
    
    @abstractmethod
    def on_enter(self) -> 'WhatsAppMessage':
        """
        Called when user transitions INTO this state.
        Returns: WhatsApp message to send immediately.
        
        Example:
            return ListMessage(
                to=self.customer.phone_number,
                body="Choose your plan:",
                button_text="View Plans"
            ).add_section("Monthly Plans", [...])
        """
        pass
    
    @abstractmethod
    def process_input(self, user_message: str) -> StateTransition:
        """
        Process user's response and determine next state.
        
        Args:
            user_message: Raw text or button payload from WhatsApp
            
        Returns:
            StateTransition with next_state, context updates, and tasks
        
        Example:
            if user_message == "ukwezi":
                return StateTransition(
                    next_state="payment_input",
                    context_updates={"selected_plan": "monthly", "amount": 5000},
                    celery_tasks=[(track_plan_selection, [self.customer.id], {}, 0)]
                )
        """
        pass
    
    def validate_transition(self, target_state: str) -> tuple[bool, str]:
        """
        Check if transition to target state is allowed.
        Override for custom validation logic.
        
        Returns:
            (is_valid, error_message)
        """
        allowed = self.get_allowed_transitions()
        if target_state not in allowed:
            return False, f"Cannot transition from {self.state_name} to {target_state}"
        return True, ""
    
    def get_allowed_transitions(self) -> List[str]:
        """
        Define valid next states (for safety checks).
        Override to specify allowed transitions.
        """
        return []  # Empty = allow all (use with caution)
    
    def on_exit(self):
        """
        Cleanup logic when leaving this state.
        Override to implement teardown (e.g., clear temp data).
        """
        pass
    
    # --- Helper Methods ---
    
    def get_context(self, key: str, default=None):
        """Retrieve value from session context"""
        return self.context.get(key, default)
    
    def update_context(self, **kwargs):
        """Update session context"""
        self.context.update(kwargs)
    
    def schedule_task(self, task_func, args=None, kwargs=None, countdown=0):
        """Helper to add Celery task to transition"""
        return (task_func, args or [], kwargs or {}, countdown)