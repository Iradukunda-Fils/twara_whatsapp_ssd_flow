from django.apps import AppConfig



class WhatsappUssdConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'whatsapp_ussd'

    def ready(self):
        try:
            from whatsapp_ussd.services.core.registry import StateRegistry
            StateRegistry._load_all_handlers()
            StateRegistry.validate_graph()
        except Exception as e:
            import logging
            logging.error(f"Failed to initialize state handlers: {e}")
