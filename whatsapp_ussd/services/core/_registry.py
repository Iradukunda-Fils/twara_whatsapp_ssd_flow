from __future__ import annotations
from .exceptions import StateNotFoundError
from typing import Dict, Type
import logging
import pkgutil
import importlib
from pathlib import Path
import inspect
import threading

logger = logging.getLogger(__name__)


class StateRegistry:
    """
    Central registry for all conversation state handlers.

    Design Goals:
    • Dynamic discovery of states via pkgutil
    • Singleton behavior (shared registry)
    • Startup validation of state graph integrity
    • Developer-friendly debugging info
    """

    _handlers: Dict[str, Type["BaseStateHandler"]] = {}
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    # ----------------------------
    # Registration & Retrieval
    # ----------------------------

    @classmethod
    def register(cls, state_name: str, handler_class: Type["BaseStateHandler"]):
        """Register a state handler by name."""
        from ..states import BaseStateHandler

        if not state_name or not isinstance(state_name, str):
            raise ValueError("state_name must be a non-empty string")

        if not issubclass(handler_class, BaseStateHandler):
            raise TypeError(f"{handler_class} must inherit from BaseStateHandler")

        if state_name in cls._handlers:
            logger.warning(f"Overwriting existing state handler for '{state_name}'")

        cls._handlers[state_name] = handler_class
        logger.debug(f"Registered state handler: {state_name} -> {handler_class.__name__}")

    @classmethod
    def get_handler(cls, state_name: str, session: "UserSession") -> "BaseStateHandler":
        """Return an initialized handler instance for a given state."""

        if not cls._initialized:
            cls._load_all_handlers()

        handler_class = cls._handlers.get(state_name)
        if not handler_class:
            raise StateNotFoundError(f"No handler registered for state: {state_name}")

        return handler_class(session)

    # ----------------------------
    # Auto-Discovery
    # ----------------------------

    # @classmethod
    # def _load_all_handlers(cls):
    #     """Discover all state handler classes from the states package."""
    #     from ..states import BaseStateHandler

    #     base_path = Path(__file__).parent.parent / "states"
    #     package = "whatsapp_ussd.services.states"

    #     logger.info(f"Auto-discovering state handlers in: {base_path}")

    #     for _, module_name, _ in pkgutil.iter_modules([str(base_path)]):
    #         try:
    #             module = importlib.import_module(f"{package}.{module_name}")
    #         except Exception as e:
    #             logger.error(f"Failed to import {module_name}: {e}", exc_info=True)
    #             continue

    #         for name, obj in inspect.getmembers(module, inspect.isclass):
    #             if issubclass(obj, BaseStateHandler) and obj is not BaseStateHandler:
    #                 if not hasattr(obj, "state_name"):
    #                     logger.warning(f"Handler {name} missing 'state_name', skipping.")
    #                     continue
    #                 cls.register(obj.state_name, obj)

    #     cls._initialized = True
    #     cls.validate_graph()
    #     logger.info(f"✅ Loaded {len(cls._handlers)} state handlers successfully")

    @classmethod
    def _load_all_handlers(cls):
        """Discover all state handler classes from the states package."""
        if cls._initialized:
            return

        with cls._lock:

            from ..states import BaseStateHandler

            base_path = Path(__file__).parent.parent / "states"
            package = "whatsapp_ussd.services.states"

            logger.info(f"Auto-discovering state handlers in: {base_path}")

            for _, module_name, _ in pkgutil.iter_modules([str(base_path)]):
                try:
                    module = importlib.import_module(f"{package}.{module_name}")
                except Exception as e:
                    logger.error(f"Failed to import {module_name}: {e}", exc_info=True)
                    continue

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseStateHandler) and obj is not BaseStateHandler:
                        if not hasattr(obj, "state_name"):
                            logger.warning(f"Handler {name} missing 'state_name', skipping.")
                            continue
                        if obj.state_name in cls._handlers:
                            continue  # Skip already registered handler
                        cls.register(obj.state_name, obj)

            cls._initialized = True
            cls.validate_graph()
            logger.info(f"✅ Loaded {len(cls._handlers)} state handlers successfully")


    # ----------------------------
    # Validation & Debugging
    # ----------------------------

    @classmethod
    def validate_graph(cls):
        """
        Ensure all declared transitions lead to valid states.
        Raises ValueError if dangling transitions are found.
        """

        unknown_transitions = []

        for handler_class in cls._handlers.values():
            try:
                handler = handler_class(session=None)
                allowed = handler.get_allowed_transitions() or []
            except Exception as e:
                logger.warning(f"Could not instantiate {handler_class.__name__}: {e}")
                continue

            for target_state in allowed:
                if target_state not in cls._handlers:
                    unknown_transitions.append((handler_class.state_name, target_state))

        if unknown_transitions:
            error_message = "\n".join(
                f"  • {src} → {dst}" for src, dst in unknown_transitions
            )
            raise ValueError(
                f"❌ Invalid state transitions detected:\n{error_message}"
            )

        logger.info("✅ State graph validation passed (no missing transitions).")

    # ----------------------------
    # Developer Utilities
    # ----------------------------

    @classmethod
    def list_states(cls) -> Dict[str, str]:
        """Return a simple mapping of all registered states and their handler names."""
        if not cls._initialized:
            cls._load_all_handlers()
        return {k: v.__name__ for k, v in cls._handlers.items()}
