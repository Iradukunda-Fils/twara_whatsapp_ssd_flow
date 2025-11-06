# core/session.py
from django.db import models
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from ._registry import StateRegistry

from whatsapp_ussd.models import UssdUser

class UserSession:
    """
    Manages user session state with hybrid Redis + DB storage.
    
    Design Rationale:
    • Redis: Stores active state, temp context (TTL 1 hour)
    • DB: Persists critical data (state history, user profile)
    • Atomic updates: Use Django transactions for consistency
    """
    
    REDIS_PREFIX = "twara:session"
    REDIS_TTL = 3600  # 1 hour
    
    def __init__(self, phone_number: str, name: str | None = None) -> None:
        self.phone_number = phone_number
        self.name = name
        self.redis_key = f"{self.REDIS_PREFIX}:{phone_number}"
        
        # Load or create customer
        self.customer = self._get_or_create_customer()
        
        # Load session data from Redis (or DB fallback)
        self._load_session()
        
    
    def _get_or_create_customer(self) -> UssdUser:
        """
        Get existing UssdUser or create new one.
        Since UssdUser inherits from Customer, we create UssdUser directly.
        """
        # Since UssdUser inherits from Customer, create UssdUser directly
        # This gives us all Customer fields plus tracking fields
        ussd_user, _ = UssdUser.objects.get_or_create(
            phone_number=self.phone_number,
            defaults={
                'name': self.name,
                'current_flow_state': 'welcome',
                'state_context': {},
            }
        )
        return ussd_user
    
    def _load_session(self):
        """Load session from Redis, fallback to DB"""
        cached = cache.get(self.redis_key)
        
        if cached:
            self.current_state = cached.get('state', 'welcome')
            self.context = cached.get('context', {})
            self.message_history = cached.get('history', [])
        else:
            # Fallback: Load last known state from DB
            self.current_state = self.customer.current_flow_state or 'welcome'
            self.context = self.customer.state_context or {}
            self.message_history = []
    
    def transition_to(self, new_state: str, **context_updates):
        """
        Atomic state transition with DB + Redis sync.
        
        Design Rationale:
        • Use DB transaction to ensure consistency
        • Update Redis for fast access
        • Log transition in UserEvent for analytics
        """
        # Update context
        self.context.update(context_updates)

        def _db_write():
            # Log state change
            # Since UssdUser inherits from Customer, self.customer IS the user
            from whatsapp_ussd.models import UserEvent
            UserEvent.objects.create(
                customer=self.customer,  # UssdUser IS a Customer (via inheritance)
                event_type='state_transition',
                from_state=self.current_state,
                to_state=new_state,
                metadata={'context': context_updates}
            )
            
            # Update USSD user record (DB)
            self.customer.current_flow_state = new_state
            self.customer.state_context = self.context
            self.customer.save(update_fields=[
                'current_flow_state', 
                'state_context', 
                'last_interaction'
            ])
            
            # Update Redis cache
            self.current_state = new_state

        with transaction.atomic():
            _db_write()
            transaction.on_commit(self._persist_to_redis)
    
    def _persist_to_redis(self):
        """Save session to Redis"""
        cache.set(self.redis_key, {
            'state': self.current_state,
            'context': self.context,
            'history': self.message_history[-10:]  # Keep last 10 messages
        }, timeout=self.REDIS_TTL)
    
    def add_message(self, message: str, sender: str = 'user') -> None:
        """Track conversation history and update UssdUser tracking"""
        self.message_history.append({
            'text': message,
            'sender': sender,
            'timestamp': timezone.now().isoformat()
        })
        
        # Update UssdUser tracking fields using helper method
        # Note: total_messages and last_interaction are in UssdUser, not Customer
        self.customer.increment_message_count()
        
        self._persist_to_redis()
    
    def clear(self):
        """Reset session (logout or error recovery)"""
        cache.delete(self.redis_key)
        self.current_state = 'welcome'
        self.context = {}
        self.message_history = []

        # Reset USSD user record (DB)
        self.customer.current_flow_state = 'welcome'
        self.customer.state_context = {}
        self.customer.save(update_fields=[
            'current_flow_state', 
            'state_context', 
            'last_interaction'
        ])

    def restore_if_expired(self):
        if not cache.get(self.redis_key):
            self._load_session()
            handler = StateRegistry.get_handler(self.current_state, self)
            # Use on_reenter if present, else fall back to on_enter
            if hasattr(handler, "on_reenter"):
                handler.on_reenter()
            else:
                handler.on_enter()

    
