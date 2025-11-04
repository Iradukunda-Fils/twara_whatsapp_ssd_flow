# core/controller.py
from typing import Optional, Dict, Any, List, Callable
import logging
from .exceptions import StateNotFoundError
from .registry import StateRegistry
from ..core.session import UserSession
from ..states.base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, MessageResponse

logger = logging.getLogger(__name__)


class StateFlowController:
    """
    Central coordinator for all state transitions and message processing.
    """

    def __init__(self):
        self.registry = StateRegistry()
        self.event_dispatcher = EventDispatcher()

    def handle_message(self, phone_number: str, message: str) -> Optional[MessageResponse]:
        """
        Main entry point for processing incoming WhatsApp messages.
        Synchronous version of previous async handler.
        """
        try:
            # 1. Load session
            session = UserSession(phone_number)
            # session.clear()
            session.add_message(message, sender='user')

            # 2. Get state handler
            state_handler = self.registry.get_handler(session.current_state, session)

            # 3. Process input
            transition = state_handler.process_input(message)
            if not transition or not getattr(transition, "next_state", None):
                logger.error("Invalid transition from state %s: %s", state_handler.state_name, transition)
                return self._handle_invalid_transition(session, "Internal error")


            # 4. Validate transition
            is_valid, error_msg = state_handler.validate_transition(transition.next_state)
            if not is_valid:
                return self._handle_invalid_transition(session, error_msg)

            # 5. Execute transition
            state_handler.on_exit()
            session.transition_to(transition.next_state, **transition.context_updates)

            # 6. Schedule Celery tasks for previous state
            if hasattr(transition, "celery_tasks"):
                self._schedule_tasks(transition.celery_tasks)

            # 7. Enter next state and send message
            next_handler = self.registry.get_handler(transition.next_state, session)

            response_message = transition.message_override or next_handler.on_enter()

            # 8. Schedule Celery tasks for the new state
            if getattr(next_handler, "celery_tasks", None):
                self._schedule_tasks(next_handler.celery_tasks)

            # 9. Send via WhatsApp synchronously
            if not response_message:
                logger.error("No response message from state %s", transition.next_state)
                return self._handle_invalid_transition(session, "Internal error")
            
            if isinstance(response_message, StateTransition):
                response_message.message_override.send()

            whatsapp_response = response_message.send()  # synchronous version
            session.add_message(response_message.body if isinstance(response_message, TextMessage) else str(response_message), sender='bot')

            # 10. Emit events
            self.event_dispatcher.emit('message_processed', {
                'phone': phone_number,
                'from_state': state_handler.state_name,
                'to_state': transition.next_state,
                'success': getattr(whatsapp_response, 'success', True)
            })

            return whatsapp_response

        except StateNotFoundError as e:
            logger.error(f"State not found for {phone_number}: {e}")
            return self._recover_to_safe_state(phone_number)

        except Exception as e:
            logger.exception(f"Critical error processing message: {e}")
            return self._handle_system_error(phone_number)

    def _schedule_tasks(self, tasks: List[tuple]):
        """Schedule Celery tasks from state transitions"""
        for task_func, args, kwargs, countdown in tasks:
            task_func.apply_async(args=args, kwargs=kwargs, countdown=countdown)

    def _handle_invalid_transition(self, session: UserSession, error: str):
        """Send error message and stay in current state"""
        error_msg = TextMessage(
            to=session.phone_number,
            body="Murakoze. Ongera mugerageze cangwa kanda 'Menu' kugira ngo usubire aho watangiriye."
        )
        return error_msg.send()  # synchronous

    def _recover_to_safe_state(self, phone_number: str):
        """Fallback to main menu if state corrupted"""
        session = UserSession(phone_number)
        session.transition_to('main_menu')

        menu_handler = self.registry.get_handler('main_menu', session)
        message = menu_handler.on_enter()
        return message.send()

    def _handle_system_error(self, phone_number: str):
        """Send apology message on system failure"""
        error_msg = TextMessage(
            to=phone_number,
            body="Mbabarira, habayeho ikibazo. Ongera mugerageze nyuma."
        )
        return error_msg.send()


class EventDispatcher:
    """
    Event bus for cross-cutting concerns (analytics, webhooks, etc.)
    """

    _subscribers: Dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(cls, event_name: str, callback: Callable):
        """Register event listener"""
        cls._subscribers.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, data: Dict[str, Any]):
        """Dispatch event to all subscribers"""
        for callback in list(self._subscribers.get(event_name, [])):
            try:
                callback(data)
            except Exception:
                logger.exception("Event subscriber error")
