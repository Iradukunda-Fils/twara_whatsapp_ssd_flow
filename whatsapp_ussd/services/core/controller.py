# core/controller.py
from typing import Optional, Dict, Any, List, Callable
import logging
from .exceptions import StateNotFoundError

from ..core.session import UserSession
from ..states.base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, MessageResponse

logger = logging.getLogger(__name__)


class StateFlowController:
    """
    Central coordinator for all state transitions and message processing.
    
    Design Rationale:
    • Single entry point for all WhatsApp messages
    • Handles error recovery and fallback states
    • Coordinates between session, states, and Celery tasks
    • Provides metrics collection hooks
    """
    
    def __init__(self):
        self.registry = StateRegistry()
        self.event_dispatcher = EventDispatcher()
    
    async def handle_message(self, phone_number: str, message: str) -> Optional[MessageResponse]:
        """
        Main entry point for processing incoming WhatsApp messages.
        
        Flow:
        1. Load user session (DB + Redis)
        2. Get current state handler
        3. Validate input and process
        4. Execute state transition
        5. Schedule Celery tasks
        6. Send response via WhatsApp
        7. Emit analytics events
        """
        try:
            # 1. Load session (creates/updates UssdUser for tracking)
            # UssdUser inherits from Customer, so we get UssdUser directly
            session: UserSession = UserSession(phone_number)
            session.add_message(message, sender='user')  # Updates total_messages and last_interaction
            
            # 2. Get state handler
            state_handler = self.registry.get_handler(
                session.current_state, 
                session
            )
            
            # 3. Process input
            transition = state_handler.process_input(message)
            
            # 4. Validate transition
            is_valid, error_msg = state_handler.validate_transition(
                transition.next_state
            )
            if not is_valid:
                return await self._handle_invalid_transition(
                    session, error_msg
                )
            
            # 5. Execute transition
            state_handler.on_exit()
            session.transition_to(
                transition.next_state, 
                **transition.context_updates
            )
            
            # 6. Schedule Celery tasks
            self._schedule_tasks(transition.celery_tasks)
            
            # 7. Enter next state and send message
            next_handler = self.registry.get_handler(
                transition.next_state, 
                session
            )
            response_message = transition.message_override or next_handler.on_enter()
            
            # 8. Send via WhatsApp and track bot message
            whatsapp_response = await response_message.asend()
            session.add_message(response_message.body, sender='bot')  # Updates UssdUser tracking
            
            # 9. Emit events
            self.event_dispatcher.emit('message_processed', {
                'phone': phone_number,
                'from_state': state_handler.state_name,
                'to_state': transition.next_state,
                'success': whatsapp_response.success
            })
            
            return whatsapp_response
            
        except StateNotFoundError as e:
            logger.error(f"State not found for {phone_number}: {e}")
            return await self._recover_to_safe_state(phone_number)
            
        except Exception as e:
            logger.exception(f"Critical error processing message: {e}")
            return await self._handle_system_error(phone_number)
    
    def _schedule_tasks(self, tasks: List[tuple]):
        """Schedule Celery tasks from state transitions"""
        for task_func, args, kwargs, countdown in tasks:
            task_func.apply_async(
                args=args,
                kwargs=kwargs,
                countdown=countdown
            )
    
    async def _handle_invalid_transition(self, session: UserSession, error: str):
        """Send error message and stay in current state"""
        error_msg = TextMessage(
            to=session.phone_number,
            body="Murakoze. Ongera mugerageze canke kanda 'Menu' kugira ngo usubire aho watangiriye."
        )
        return await error_msg.asend()
    
    async def _recover_to_safe_state(self, phone_number: str):
        """Fallback to main menu if state corrupted"""
        # Create session using UssdUser (which inherits from Customer)
        session = UserSession(phone_number)
        session.transition_to('main_menu')
        
        menu_handler = self.registry.get_handler('main_menu', session)
        message = menu_handler.on_enter()
        return await message.asend()
    
    async def _handle_system_error(self, phone_number: str):
        """Send apology message on system failure"""
        error_msg = TextMessage(
            to=phone_number,
            body="Mbabarira, habayeho ikibazo. Ongera mugerageze nyuma."
        )
        return await error_msg.asend()


class StateRegistry:
    """
    Registry pattern for state handlers.
    
    Design Rationale:
    • Singleton with lazy loading
    • Allows dynamic registration
    • Validates state graph at startup
    """
    
    _handlers: Dict[str, type[BaseStateHandler]] = {}
    _initialized = False
    
    @classmethod
    def register(cls, state_name: str, handler_class: type[BaseStateHandler]):
        """Register a state handler"""
        if state_name in cls._handlers:
            logger.warning(f"Overwriting handler for state: {state_name}")
        cls._handlers[state_name] = handler_class
    
    @classmethod
    def get_handler(cls, state_name: str, session: UserSession) -> BaseStateHandler:
        """Get state handler instance"""
        if not cls._initialized:
            cls._load_all_handlers()
        
        if state_name not in cls._handlers:
            raise StateNotFoundError(f"No handler for state: {state_name}")
        
        handler_class = cls._handlers[state_name]
        return handler_class(session)
    
    @classmethod
    def _load_all_handlers(cls):
        """Auto-discover and register all handlers"""
        try:
            from ..states import ALL_STATE_HANDLERS
            for handler_class in ALL_STATE_HANDLERS:
                cls.register(handler_class.state_name, handler_class)
            cls._initialized = True
            logger.info(f"Loaded {len(cls._handlers)} state handlers")
        except ImportError as e:
            logger.warning(f"Could not load state handlers: {e}")
            cls._initialized = True


class EventDispatcher:
    """
    Event bus for cross-cutting concerns (analytics, webhooks, etc.)
    
    Design Rationale:
    • Decouples state logic from side effects
    • Supports multiple subscribers per event
    • Non-blocking (uses Celery for heavy processing)
    """
    
    _subscribers: Dict[str, List[Callable]] = {}
    
    @classmethod
    def subscribe(cls, event_name: str, callback: Callable):
        """Register event listener"""
        if event_name not in cls._subscribers:
            cls._subscribers[event_name] = []
        cls._subscribers[event_name].append(callback)
    
    def emit(self, event_name: str, data: Dict[str, Any]):
        """Dispatch event to all subscribers"""
        if event_name not in self._subscribers:
            return
        
        for callback in self._subscribers[event_name]:
            try:
                callback(data)
            except Exception as e:
                logger.error(f"Event subscriber error: {e}", exc_info=True)




## 3. FLOW EXAMPLE (STATE DIAGRAM)

### State Transition Map
