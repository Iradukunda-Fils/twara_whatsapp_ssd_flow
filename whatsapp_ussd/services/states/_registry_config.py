# states/registry_config.py
"""
Configuration for state transitions and validations.
"""

STATE_TRANSITION_MAP = {
    "welcome": ["name_capture", "main_menu"],
    "name_capture": ["name_capture", "main_menu"],
    "main_menu": [
        "exam_start", 
        "buy_code_direct", 
        "police_registration_info",
        "view_progress",
        "subscription_status",
        "main_menu"
    ],
    "exam_start": ["exam_in_progress", "main_menu", "subscription_offer"],
    "exam_in_progress": ["exam_result", "main_menu", "exam_in_progress"],
    "exam_result": ["waiting_for_offer", "exam_start", "main_menu", "subscription_offer"],
    "waiting_for_offer": ["subscription_offer", "main_menu", "exam_start", "waiting_for_offer"],
    "subscription_offer": ["plan_selection", "main_menu", "subscription_offer"],
    "plan_selection": ["plan_confirmation", "plan_selection", "main_menu"],
    "plan_confirmation": ["payment_input", "plan_selection", "main_menu", "plan_confirmation"],
    "payment_input": ["payment_pending", "payment_input", "plan_confirmation"],
    "payment_pending": ["payment_success", "payment_failed", "main_menu", "payment_pending"],
    "payment_success": ["exam_start", "main_menu", "payment_success"],
    "payment_failed": ["payment_input", "main_menu", "payment_failed"],
    "buy_code_direct": ["plan_selection"],
    "police_registration_info": ["exam_start", "plan_selection", "main_menu"],
    "view_progress": ["exam_start", "main_menu"],
    "subscription_status": ["plan_selection", "main_menu"],
    # "weekly_progress_report": ["exam_start", "detailed_performance", "main_menu"]  # #** Nont Working **# #
}

# State timeouts (in seconds)
STATE_TIMEOUTS = {
    "welcome": 3600,  # 1 hour
    "name_capture": 1800,  # 30 minutes
    "main_menu": 7200,  # 2 hours
    "exam_start": 600,  # 10 minutes
    "exam_in_progress": 1800,  # 30 minutes
    "exam_result": 300,  # 5 minutes
    "waiting_for_offer": 60,  # 1 minute
    "subscription_offer": 600,  # 10 minutes
    "plan_selection": 600,  # 10 minutes
    "plan_confirmation": 600,  # 10 minutes
    "payment_input": 600,  # 10 minutes
    "payment_pending": 300,  # 5 minutes
    "payment_success": 300,  # 5 minutes
    "payment_failed": 600,  # 10 minutes
    "buy_code_direct": 600,  # 10 minutes
    "police_registration_info": 600,  # 10 minutes
    "view_progress": 600,  # 10 minutes
    "subscription_status": 600,  # 10 minutes
}

# State display names for admin dashboard
STATE_DISPLAY_NAMES = {
    "welcome": "Welcome",
    "name_capture": "Name Capture",
    "main_menu": "Main Menu",
    "exam_start": "Exam Start",
    "exam_in_progress": "Taking Exam",
    "exam_result": "Exam Results",
    "waiting_for_offer": "Waiting for Offer",
    "subscription_offer": "Subscription Offer",
    "plan_selection": "Plan Selection",
    "plan_confirmation": "Plan Confirmation",
    "payment_input": "Payment Input",
    "payment_pending": "Payment Pending",
    "payment_success": "Payment Success",
    "payment_failed": "Payment Failed",
    "buy_code_direct": "Buy Code Direct",
    "police_registration_info": "Police Info",
    "view_progress": "View Progress",
    "subscription_status": "Subscription Status",
}