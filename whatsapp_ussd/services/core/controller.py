# core/controller.py
from typing import Optional, Dict, Any, List, Callable
import logging
from .exceptions import StateNotFoundError
from ._registry import StateRegistry
from ..core.session import UserSession
from ..states.base import BaseStateHandler, StateTransition
from whatsapp import TextMessage, MessageResponse, WhatsAppMessage

logger = logging.getLogger(__name__)


class StateFlowController:
    """
    Central coordinator for state transitions and message processing.
    """

    def __init__(self):
        self.registry = StateRegistry()
        self.event_dispatcher = EventDispatcher()

    def handle_message(self, phone_number: str, message: str) -> Optional[MessageResponse]:
        try:
            session = UserSession(phone_number)
            # session.clear()
            session.add_message(message, sender="user")

            handler = self.registry.get_handler(session.current_state, session)
            transition = handler.process_input(message)

            if not transition or not getattr(transition, "next_state", None):
                logger.warning("Invalid transition from %s", handler.state_name)
                return self._handle_invalid_transition(session)

            # Exit current state
            handler.on_exit()
            session.transition_to(transition.next_state, **(transition.context_updates or {}))
            self._schedule_tasks(transition.celery_tasks)

            # Enter next state (auto-send response)
            response = self._enter_state(
                transition.next_state,
                session,
                message_override=transition.message_override
            )

            # Persist outgoing message in session history (best-effort)
            try:
                # If final_response is MessageResponse we may not have a 'body' attribute
                bot_text = None
                if isinstance(response, MessageResponse):
                    # Try to find a textual body in raw_response if present
                    raw = getattr(response, "raw_response", None)
                    if isinstance(raw, dict):
                        # attempt common places (best-effort)
                        bot_text = raw.get("message", raw.get("messages", None))
                elif isinstance(response, WhatsAppMessage):
                    bot_text = getattr(response, "body", str(response))
                elif hasattr(response, "body"):
                    bot_text = getattr(response, "body", None)

                if bot_text:
                    session.add_message(str(bot_text), sender="bot")
            except Exception:
                logger.exception("Failed to record outgoing message for %s", phone_number)

            # # Emit event (best-effort)
            # try:
            #     self.event_dispatcher.emit(
            #         "message_processed",
            #         {
            #             "phone": phone_number,
            #             "from_state": handler.state_name,
            #             "to_state": transition.next_state,
            #             "success": getattr(response, "success", True),
            #         },
            #     )
            # except Exception:
            #     logger.exception("Event dispatch failed")

            # If final_response is a WhatsAppMessage, ensure the message was sent and return its MessageResponse.
            if isinstance(response, WhatsAppMessage):
                try:
                    sent = response.send()
                    return sent
                except Exception:
                    logger.exception("Failed to send WhatsAppMessage for %s", phone_number)
                    return self._handle_system_error(phone_number)

            return response

        except StateNotFoundError as e:
            logger.error("State not found for %s: %s", phone_number, e)
            return self._recover_to_safe_state(phone_number)

        except Exception:
            logger.exception("Critical error during message handling")
            return self._handle_system_error(phone_number)

    def _enter_state(self, state_name: str, session: UserSession, message_override=None):
        """Helper to enter a state safely, optionally overriding message"""
        handler = self.registry.get_handler(state_name, session)
        try:
            response = message_override or handler.on_enter()
        except Exception:
            logger.exception("Error entering state %s", state_name)
            return self._handle_system_error(session.phone_number)

        # If state returns a transition, follow it recursively
        if isinstance(response, StateTransition):
            session.transition_to(response.next_state, **(response.context_updates or {}))
            self._schedule_tasks(response.celery_tasks)
            return self._enter_state(response.next_state, session, response.message_override)

        # ✅ AUTO-SEND if it's a WhatsApp message
        if isinstance(response, WhatsAppMessage):
            try:
                sent_response = response.send()
                return sent_response
            except Exception:
                logger.exception("Failed to send WhatsApp message for %s", session.phone_number)
                return self._handle_system_error(session.phone_number)

        # ✅ If already a MessageResponse (from QuickSend etc.)
        if isinstance(response, MessageResponse):
            return response

        # If response is raw text or unsupported type
        if isinstance(response, str):
            return TextMessage(session.phone_number, response).send()

        return response


    # def _enter_state(self, state_name: str, /, *, session: UserSession, message_override=None): ...

    def _schedule_tasks(self, tasks: list[tuple[Callable, list, dict, int]]):
        """Schedule Celery tasks safely"""
        if not tasks:
            return
        for task_func, args, kwargs, countdown in tasks:
            try:
                task_func.apply_async(args=args or [], kwargs=kwargs or {}, countdown=countdown or 0)
            except Exception:
                logger.exception("Failed to schedule task %s", task_func)

    def _handle_invalid_transition(self, session: UserSession, error: str = None):
        return TextMessage(
            to=session.phone_number,
            body="Murakoze. Ongera mugerageze cyangwa kanda 'Menu' kugira ngo usubire aho watangiriye."
        ).send()

    def _recover_to_safe_state(self, phone_number: str):
        session = UserSession(phone_number)
        session.transition_to("main_menu")
        menu_handler = self.registry.get_handler("main_menu", session)
        message = menu_handler.on_enter()
        return message.send()

    def _handle_system_error(self, phone_number: str):
        return TextMessage(
            to=phone_number,
            body="Mbabarira, habayeho ikibazo. Ongera mugerageze nyuma."
        ).send()


class EventDispatcher:
    _subscribers: Dict[str, List[Callable]] = {}

    @classmethod
    def subscribe(cls, event_name: str, callback: Callable):
        cls._subscribers.setdefault(event_name, []).append(callback)

    def emit(self, event_name: str, data: Dict[str, Any]):
        for callback in list(self._subscribers.get(event_name, [])):
            try:
                callback(data)
            except Exception:
                logger.exception("Event subscriber error for %s, data=%r", event_name, data)
