
"""
Main entry point for the application.
The update_performance method has been moved to the Performance model.
"""


def main():
    """Main entry point for the application."""
    import os
    import django
    
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ussd_settings.settings')
    django.setup()
    
    print("Twara WhatsApp Flow application initialized.")


if __name__ == "__main__":
    main()
