# states/base.py
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Tuple, Callable
from dataclasses import dataclass
from ..core.session import UserSession
from whatsapp import *

@dataclass
class StateTransition:
    """Represents the result of processing user input"""
    next_state: str
    context_updates: Dict[str, Any] = None
    message_override: Optional[Any] = None
    validation_errors: List[str] = None
    celery_tasks: list[tuple[Callable[..., Any], list[Any], dict[str, Any], int]] = None  # [(task_func, args, kwargs, countdown)]

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
    celery_tasks: list[tuple[Callable[..., Any], list[Any], dict[str, Any], int]] = []
    
    
    def __init__(self, session: Optional["UserSession"] = None):
        self.session = session
        # Safe access for validation or dry runs
        self.ussd_user = getattr(session, "customer", None) if session else None
        self.context = getattr(session, "context", {}) if session else {}
    
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
    def process_input(self, user_message: str) -> 'StateTransition':
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
        from ._registry_config import STATE_TRANSITION_MAP
        return STATE_TRANSITION_MAP.get(self.state_name, [])
    
    def on_exit(self):
        """
        Cleanup logic when leaving this state.
        Override to implement teardown (e.g., clear temp data).
        """
        pass

    def on_reenter(self) -> 'WhatsAppMessage':
        """Default re-enter behaviour: treat as fresh enter."""
        return self.on_enter()
    
    # --- Helper Methods ---
    
    def get_context(self, key: str, default=None):
        """Retrieve value from session context"""
        return self.context.get(key, default)
    
    def update_context(self, **kwargs):
        """Update session context"""
        self.context.update(kwargs)
    

    def schedule_task(
        self,
        task_func: Callable,
        args: list[Any],
        kwargs: dict[str, Any] | None = None,
        countdown: int = 0
    ) -> None:
        """Helper to add Celery task to transition"""
        if kwargs is None:
            kwargs = {}
            
        task = (task_func, args, kwargs, countdown)
        self.celery_tasks.append(task)

        return task

