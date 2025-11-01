# tasks.py
from celery import shared_task
from celery.schedules import crontab
from django.utils import timezone
from django.db import transaction
from django.db.models import F, ExpressionWrapper
from django.db import models
from datetime import timedelta
import logging

from whatsapp_ussd.models import Customer, UserPayment, quiz, Performance, UssdUser

# Note: UssdUser inherits from Customer, so use UssdUser for all user operations
# Customer is kept for backward compatibility and for non-USSD users
from whatsapp_ussd.services.core.session import UserSession
from whatsapp_ussd.services.core.controller import StateFlowController, StateRegistry
from whatsapp import TextMessage, InteractiveMessage

logger = logging.getLogger(__name__)


# --- HIGH PRIORITY TASKS (User-Facing) ---

@shared_task(queue='high_priority', bind=True)
def trigger_subscription_offer(self, phone_number: str):
    """
    Delayed task to send subscription offer after exam failure.
    
    Design Rationale:
    • Runs 15 seconds after exam completion
    • Checks if user is still in waiting state
    • Only sends if no other interaction occurred
    """
    try:
        session = UserSession(phone_number)
        
        # Verify user is still waiting (didn't navigate away)
        if session.current_state != "waiting_offer":
            logger.info(f"User {phone_number} moved to {session.current_state}, skipping offer")
            return
        
        # Transition to offer state
        controller = StateFlowController()
        session.transition_to("subscription_offer")
        
        # Send offer message
        offer_handler = StateRegistry.get_handler("subscription_offer", session)
        message = offer_handler.on_enter()
        response = message.send()
        
        if not response.success:
            raise Exception(f"Failed to send offer: {response.error_message}")
        
        logger.info(f"Subscription offer sent to {phone_number}")
        
    except Exception as exc:
        logger.error(f"Error sending subscription offer: {exc}", exc_info=True)
        self.retry(exc=exc, countdown=30)


@shared_task(queue='high_priority')
def send_whatsapp_message(payload: dict, phone_number: str):
    """
    Generic task for sending WhatsApp messages asynchronously.
    
    Design Rationale:
    • Decouples message sending from state transitions
    • Allows retry logic without blocking user flow
    • Tracks delivery status in DB
    """
    try:
        from whatsapp import WhatsAppClient, WHATSAPP_CLIENT
        client = WHATSAPP_CLIENT
        # Build MessageResponse from payload
        from whatsapp import MessageResponse
        response = client.send(payload)
        
        if not response.success:
            logger.error(f"WhatsApp send failed: {response.error_message}")
            raise Exception(response.error_message)
        
        # Log successful send (if UserEvent model exists)
        # Use UssdUser directly since it inherits from Customer
        try:
            from whatsapp_ussd.models import UserEvent
            # Try to get UssdUser first (preferred), fallback to Customer if doesn't exist
            try:
                ussd_user = UssdUser.objects.get(phone_number=phone_number)
            except UssdUser.DoesNotExist:
                # Create UssdUser from existing Customer data
                from whatsapp_ussd.models import Customer
                customer = Customer.objects.get(phone_number=phone_number)
                ussd_user = UssdUser.objects.create(
                    phone_number=customer.phone_number,
                    name=customer.name,
                    exam_date=customer.exam_date,
                    feedback=customer.feedback,
                )
            
            UserEvent.objects.create(
                customer=ussd_user,  # UssdUser IS a Customer (via inheritance)
                event_type='message_sent',
                metadata={'message_id': response.message_id if hasattr(response, 'message_id') else None}
            )
        except ImportError:
            pass
        
        return response.message_id
        
    except Exception as exc:
        logger.error(f"Error sending WhatsApp message: {exc}", exc_info=True)
        raise


# --- DEFAULT PRIORITY TASKS (Background Processing) ---

@shared_task(queue='default', bind=True, max_retries=5)
def update_customer_performance(self, customer_id: int):
    """
    Recalculate performance metrics after quiz completion.
    
    Design Rationale:
    • Offloads expensive aggregation queries
    • Runs asynchronously to avoid blocking exam results
    • Retries on DB lock conflicts
    """
    try:
        # Get UssdUser directly (preferred) or Customer (fallback)
        # Since UssdUser inherits from Customer, try UssdUser first
        try:
            ussd_user = UssdUser.objects.get(id=customer_id)
            customer = ussd_user  # UssdUser IS a Customer
        except UssdUser.DoesNotExist:
            # Fallback to Customer if not a UssdUser instance
            customer = Customer.objects.get(id=customer_id)
        
        performance, _ = Performance.objects.get_or_create(customer=customer)
        
        # Update performance metrics using Performance model method
        performance.update_performance()
        
        # Check if coaching needed (3+ failures)
        # Use UssdUser for tracking (convert Customer to UssdUser if needed)
        if isinstance(customer, UssdUser):
            ussd_user = customer
        else:
            # Try to get existing UssdUser or create from Customer
            try:
                ussd_user = UssdUser.objects.get(phone_number=customer.phone_number)
            except UssdUser.DoesNotExist:
                # Create UssdUser with Customer data (UssdUser inherits Customer fields)
                ussd_user = UssdUser.objects.create(
                    phone_number=customer.phone_number,
                    name=customer.name,
                    exam_date=customer.exam_date,
                    feedback=customer.feedback,
                    Has_been_contacted=customer.Has_been_contacted,
                    last_contacted=customer.last_contacted,
                )
        
        if ussd_user.failed_exams_count >= 3 and not ussd_user.needs_coaching:
            ussd_user.needs_coaching = True
            ussd_user.save(update_fields=['needs_coaching'])
            
            # Trigger coaching offer
            send_coaching_offer.delay(ussd_user.phone_number)
        
        logger.info(f"Performance updated for customer {customer_id}")
        
    except Exception as exc:
        logger.error(f"Error updating performance: {exc}", exc_info=True)
        self.retry(exc=exc, countdown=60)


@shared_task(queue='default', bind=True, max_retries=10)
def poll_payment_status(self, payment_ref: str, attempt: int = 0):
    """
    Poll Mobile Money API for payment confirmation.
    
    Design Rationale:
    • Handles async payment webhooks
    • Retries every 10s for up to 5 minutes
    • Transitions user state on success/failure
    """
    try:
        payment = UserPayment.objects.get(access_code=payment_ref)
        
        if payment.status == "succeeded":
            logger.info(f"Payment {payment_ref} already confirmed")
            return
        
        # Call Mobile Money API (MTN/Airtel)
        # TODO: Implement Mobile Money integration
        # For now, simulate payment check
        try:
            from whatsapp_ussd.integrations.momo import check_payment_status
            status = check_payment_status(payment.ref_id)
        except ImportError:
            logger.warning("Mobile Money integration not implemented, skipping payment check")
            status = "FAILED"
        
        if status == "SUCCESSFUL":
            payment.status = "succeeded"
            payment.save(update_fields=['status', 'last_updated'])
            
            # Trigger payment success flow
            handle_payment_success.delay(payment.access_code)
            
        elif status == "FAILED":
            payment.status = "failed"
            payment.save(update_fields=['status', 'last_updated'])
            
            # Notify user
            # TODO: Implement send_payment_failed_message task
            logger.warning(f"Payment failed for {payment.paying_number}")
            
        elif attempt < 30:  # Max 5 minutes (30 * 10s)
            # Still pending, retry
            self.retry(
                args=[payment_ref, attempt + 1],
                countdown=10
            )
        else:
            # Timeout
            payment.status = "failed"
            payment.save(update_fields=['status', 'last_updated'])
            logger.warning(f"Payment {payment_ref} timeout after 5 minutes")
            
    except Exception as exc:
        logger.error(f"Error polling payment: {exc}", exc_info=True)
        if attempt < 30:
            self.retry(exc=exc, countdown=10)


@shared_task(queue='default')
def handle_payment_success(payment_code: str):
    """
    Process successful payment and activate subscription.
    
    Design Rationale:
    • Atomic transaction ensures consistency
    • Sends confirmation with access code
    • Transitions user to confirmation state
    """
    try:
        with transaction.atomic():
            payment = UserPayment.objects.select_for_update().get(
                access_code=payment_code
            )
            
            # Get or create UssdUser for the paying customer
            # Since UssdUser inherits from Customer, use UssdUser directly
            try:
                ussd_user = UssdUser.objects.get(phone_number=payment.paying_number)
            except UssdUser.DoesNotExist:
                # Create UssdUser with phone number
                ussd_user = UssdUser.objects.create(phone_number=payment.paying_number)
            
            if ussd_user.get_active_transactions().count() > 1:
                ussd_user.is_vip = True
                ussd_user.save(update_fields=['is_vip'])
            
            # Send confirmation message with code
            message = TextMessage(
                to=ussd_user.phone_number,
                body=f"✅ Twakiriye ibwishyu bwawe bwa {payment.amount_paid}RWF!\n\n"
                     f"🔐 Code yawe: *{payment.access_code}*\n\n"
                     f"📱 Kanda hano kugira ngo utangire: https://twara.rw/exam/{payment.access_code}\n\n"
                     f"Urakoze kubufatanya bwawe! 🙏"
            )
            message.send()
            
            # Transition to confirmation state
            session = UserSession(ussd_user.phone_number, name=ussd_user.name)
            session.transition_to('payment_confirmed', payment_code=payment_code)
            
            # Schedule welcome message after 5 seconds
            # TODO: Implement send_welcome_to_subscriber task
            logger.info(f"Payment confirmed for {ussd_user.phone_number}")
            
        logger.info(f"Payment {payment_code} processed successfully")
        
    except Exception as exc:
        logger.error(f"Error handling payment success: {exc}", exc_info=True)
        raise


# --- LOW PRIORITY TASKS (Batch/Scheduled) ---

@shared_task(queue='low_priority')
def send_daily_reminders():
    """
    Celery Beat task: Send daily quiz reminders to active subscribers.
    Schedule: Every day at 8:00 AM
    
    Design Rationale:
    • Targets users with active subscriptions
    • Personalizes based on performance trends
    • Tracks reminder engagement
    """
    from django.utils import timezone
    from datetime import timedelta
    
    # Get USSD users with active subs who haven't taken quiz today
    # Since UssdUser inherits from Customer, it has all Customer fields + tracking fields
    active_ussd_users = UssdUser.objects.filter(
        last_interaction__lt=timezone.now() - timedelta(hours=12)
    ).distinct()
    
    # Filter to only USSD users with active transactions
    # Since UssdUser IS a Customer, it has get_active_transactions() method
    active_ussd_users_filtered = [
        ussd_user 
        for ussd_user in active_ussd_users 
        if ussd_user.get_active_transactions().exists()
    ]
    
    sent_count = 0
    
    # Process through UssdUser directly (it IS a Customer)
    for ussd_user in active_ussd_users_filtered:
        try:
            # Skip if user took quiz today
            # Since UssdUser inherits from Customer, we can use it directly
            latest_quiz = quiz.objects.filter(
                customer=ussd_user,
                taken__date=timezone.now().date()
            ).exists()
            
            if latest_quiz:
                continue
            
            # Personalized message based on performance
            # UssdUser IS a Customer, so it has performance relationship
            performance = ussd_user.performance
            # Note: is_improving is not a field, let's check improvement differently
            if performance and performance.avg_marks and performance.avg_marks >= 60:
                message_body = f"🎉 Mwaramutse {ussd_user.name}!\n\n" \
                              f"Uri kwiteza imbere! Amanota yawe yazamutse ku {performance.avg_marks}%.\n\n" \
                              f"Kora ikizamini cya none kugira ngo ukomeze!"
            else:
                # Determine weak area based on lowest average category marks
                weak_area = "Amategeko"  # Default
                if performance:
                    category_scores = {
                        'Amategeko': performance.avg_amategekoMarks or 0,
                        'Kugenda': performance.avg_KugendaMarks or 0,
                        'Ibinyabiziga': performance.avg_IbinyabizigaMarks or 0,
                    }
                    if category_scores:
                        weak_area = min(category_scores, key=category_scores.get) or "Amategeko"
                
                message_body = f"☀️ Mwaramutse {ussd_user.name}!\n\n" \
                              f"Reka twiteze ku *{weak_area}* uyu munsi.\n\n" \
                              f"Kora ikizamini cya none!"
            
            # Send reminder
            message = InteractiveMessage(
                to=ussd_user.phone_number,
                body=message_body,
                header="IKIZAMINI CYA NONE"
            ).add_reply_button("start_quiz", "🚀 Tangira") \
             .add_reply_button("skip_today", "⏰ Nzakora nyuma")
            
            response = message.send()
            
            if response.success:
                sent_count += 1
                
            # Log engagement - UssdUser IS a Customer via inheritance
            try:
                from whatsapp_ussd.models import UserEvent
                UserEvent.objects.create(
                    customer=ussd_user,  # UssdUser inherits from Customer
                    event_type='daily_reminder_sent',
                    metadata={'message_id': response.message_id if hasattr(response, 'message_id') else None}
                )
            except ImportError:
                pass
            
        except Exception as exc:
            logger.error(f"Error sending reminder to {ussd_user.phone_number}: {exc}")
            continue
    
    logger.info(f"Sent {sent_count} daily reminders")
    return sent_count


@shared_task(queue='low_priority')
def check_expiring_subscriptions():
    """
    Celery Beat task: Notify users 2 days before subscription expires.
    Schedule: Every day at 10:00 AM
    """
    from datetime import timedelta
    
    expiring_soon = UserPayment.objects.annotate(
        expiration_date=ExpressionWrapper(
            F('paid_on') + F('expiration') * timedelta(days=1),
            output_field=models.DateTimeField()
        )
    ).filter(
        status='succeeded',
        expiration_date__lte=timezone.now() + timedelta(days=2),
        expiration_date__gt=timezone.now()
    )
    
    for payment in expiring_soon:
        # Get or create UssdUser directly (inherits from Customer)
        try:
            ussd_user = UssdUser.objects.get(phone_number=payment.paying_number)
        except UssdUser.DoesNotExist:
            # Create UssdUser with phone number
            ussd_user = UssdUser.objects.create(phone_number=payment.paying_number)
        
        days_left = (payment.expiration_date - timezone.now()).days
        
        message = TextMessage(
            to=ussd_user.phone_number,
            body=f"⚠️ Mwaramutse {ussd_user.name}!\n\n"
                 f"Code yawe izarangira mu minsi {days_left}.\n\n"
                 f"Kanda hano kugira ngo ukomeze: https://twara.rw/renew"
        )
        message.send()
        
        try:
            from whatsapp_ussd.models import UserEvent
            UserEvent.objects.create(
                customer=ussd_user,  # UssdUser IS a Customer via inheritance
                event_type='expiration_warning',
                metadata={'payment_code': payment.access_code, 'days_left': days_left}
            )
        except ImportError:
            pass


@shared_task(queue='low_priority')
def send_coaching_offer(phone_number: str):
    """
    Offer personalized coaching for users who failed 3+ times.
    Uses UssdUser directly since it inherits from Customer.
    """
    # Get or create UssdUser (inherits from Customer)
    try:
        ussd_user = UssdUser.objects.get(phone_number=phone_number)
    except UssdUser.DoesNotExist:
        # Create UssdUser with phone number
        ussd_user = UssdUser.objects.create(phone_number=phone_number)
    
    message = TextMessage(
        to=ussd_user.phone_number,
        body=f"Mwaramutse {ussd_user.name} 👋\n\n"
             f"Tubonye ko wagize ingorane mu kizamini.\n\n"
             f"Twafitiye coaching plan ihariye yakugezaho ku ntera yo gutsinda!\n\n"
             f"🎯 1-on-1 training\n"
             f"📚 Personalized study plan\n"
             f"✅ 98% success rate\n\n"
             f"Urafite ubushake? Andika 'COACHING' kugira ngo ubone amakuru."
    )
    message.send()


# --- CELERY BEAT SCHEDULE ---
# Note: This should be configured in celery.py or settings
# app.conf.beat_schedule = {
#     'daily-quiz-reminders': {
#         'task': 'whatsapp_ussd.tasks.send_daily_reminders',
#         'schedule': crontab(hour=8, minute=0),  # 8:00 AM
#     },
#     'check-expiring-subscriptions': {
#         'task': 'whatsapp_ussd.tasks.check_expiring_subscriptions',
#         'schedule': crontab(hour=10, minute=0),  # 10:00 AM
#     },
#     'cleanup-expired-sessions': {
#         'task': 'whatsapp_ussd.tasks.cleanup_expired_sessions',
#         'schedule': crontab(hour=2, minute=0),  # 2:00 AM
#     },
# }


# --- PERFORMANCE OPTIMIZATION ---

@shared_task(queue='low_priority')
def cleanup_expired_sessions():
    """
    Clean up stale Redis sessions to free memory.
    """
    from django.core.cache import cache
    
    # Get all USSD users inactive for 24+ hours
    # Since UssdUser inherits from Customer, it has phone_number directly
    stale_ussd_users = UssdUser.objects.filter(
        last_interaction__lt=timezone.now() - timedelta(hours=24)
    )
    
    cleaned = 0
    for ussd_user in stale_ussd_users:
        # UssdUser IS a Customer, so it has phone_number directly
        cache_key = f"twara:session:{ussd_user.phone_number}"
        if cache.delete(cache_key):
            cleaned += 1
    
    logger.info(f"Cleaned {cleaned} expired sessions")
    return cleaned


# --- Additional Tasks (Duplicate definitions to fix imports) ---

@shared_task(queue='high_priority', bind=True)
def trigger_subscription_offer_task(self, phone_number: str):
    """
    Delayed task to send subscription offer after exam failure.
    Triggered 15 seconds after exam result.
    """
    try:
        session = UserSession(phone_number)
        
        # Verify user is still waiting (didn't navigate away)
        if session.current_state != "waiting_for_offer":
            logger.info(f"User {phone_number} moved to {session.current_state}, skipping offer")
            return
        
        # Transition to offer state
        session.transition_to("subscription_offer")
        
        # Send offer message
        offer_handler = StateRegistry.get_handler("subscription_offer", session)
        message = offer_handler.on_enter()
        
        if message:
            response = message.send()
            
            if not response.success:
                raise Exception(f"Failed to send offer: {response.error_message}")
        
        logger.info(f"Subscription offer sent to {phone_number}")
        
    except Exception as exc:
        logger.error(f"Error sending subscription offer: {exc}", exc_info=True)
        self.retry(exc=exc, countdown=30, max_retries=3)


@shared_task(queue='default')
def create_exam_session(customer_id: int):
    """
    Create quiz record when user starts exam.
    """
    try:
        # Get UssdUser (preferred) or Customer (fallback)
        try:
            ussd_user = UssdUser.objects.get(id=customer_id)
            customer = ussd_user  # UssdUser IS a Customer
        except UssdUser.DoesNotExist:
            customer = Customer.objects.get(id=customer_id)
        
        # Create new quiz
        new_quiz = quiz.objects.create(
            customer=customer,
            language=getattr(customer, 'preferred_language', None) or 'rw'
        )
        
        logger.info(f"Created exam session {new_quiz.id} for customer {customer_id}")
        
        return new_quiz.id
        
    except Exception as exc:
        logger.error(f"Error creating exam session: {exc}", exc_info=True)
        raise


@shared_task(queue='default', bind=True, max_retries=30)
def initiate_mobile_money_payment(self, customer_id: int, phone: str, amount: int, days: int):
    """
    Initiate Mobile Money payment via API.
    """
    try:
        # Get UssdUser (preferred) or Customer (fallback)
        try:
            ussd_user = UssdUser.objects.get(id=customer_id)
            customer = ussd_user  # UssdUser IS a Customer
        except UssdUser.DoesNotExist:
            customer = Customer.objects.get(id=customer_id)
        
        # Create payment record
        payment = UserPayment.objects.create(
            paying_number=phone,
            amount_paid=amount,
            expiration=days,
            status="pending"
        )
        
        # Call Mobile Money API (if available)
        try:
            from whatsapp_ussd.integrations.mobile_money import MobileMoneyAPI
            
            api = MobileMoneyAPI()
            result = api.request_payment(phone, amount)
            
            if result.get('success'):
                payment.ref_id = result.get('transaction_id')
                payment.save(update_fields=['ref_id'])
                
                # Update session context
                session = UserSession(customer.phone_number)
                session.context.update({'payment_ref': payment.access_code})
                session._persist_to_redis()
                
                # Start polling for payment status
                poll_payment_status.delay(payment.access_code, attempt=0)
                
                logger.info(f"Payment initiated: {payment.access_code}")
                
                return payment.access_code
            else:
                payment.status = "failed"
                payment.save(update_fields=['status'])
                
                # Notify user of failure
                send_payment_failed_message.delay(customer.phone_number, "Payment initiation failed")
                
                raise Exception(f"Payment API error: {result.get('error')}")
        except ImportError:
            logger.warning("Mobile Money integration not available")
            payment.status = "pending"
            payment.save(update_fields=['status'])
            # Continue without API call
        
    except Exception as exc:
        logger.error(f"Error initiating payment: {exc}", exc_info=True)
        self.retry(exc=exc, countdown=30)


@shared_task(queue='default', bind=True, max_retries=30)
def poll_payment_status(self, payment_ref: str, attempt: int = 0):
    """
    Poll Mobile Money API for payment confirmation.
    Retries every 10 seconds for up to 5 minutes.
    """
    try:
        payment = UserPayment.objects.get(access_code=payment_ref)
        
        if payment.status == "succeeded":
            logger.info(f"Payment {payment_ref} already confirmed")
            return
        
        # Check payment status via API (if available)
        try:
            from whatsapp_ussd.integrations.mobile_money import MobileMoneyAPI
            
            api = MobileMoneyAPI()
            status = api.check_payment_status(payment.ref_id)
        except ImportError:
            logger.warning("Mobile Money integration not available, skipping poll")
            return
        
        if status == "SUCCESSFUL":
            # Payment succeeded
            payment.status = "succeeded"
            payment.save(update_fields=['status', 'last_updated'])
            
            # Get or create UssdUser
            try:
                ussd_user = UssdUser.objects.get(phone_number=payment.paying_number)
            except UssdUser.DoesNotExist:
                ussd_user = UssdUser.objects.create(phone_number=payment.paying_number)
            
            # Transition to success state
            session = UserSession(ussd_user.phone_number)
            session.transition_to("payment_success", payment_ref=payment_ref)
            
            # Send success message
            handler = StateRegistry.get_handler("payment_success", session)
            message = handler.on_enter()
            
            if message:
                message.send()
            
            logger.info(f"Payment {payment_ref} succeeded")
            
        elif status == "FAILED":
            # Payment failed
            payment.status = "failed"
            payment.save(update_fields=['status', 'last_updated'])
            
            # Get or create UssdUser
            try:
                ussd_user = UssdUser.objects.get(phone_number=payment.paying_number)
            except UssdUser.DoesNotExist:
                ussd_user = UssdUser.objects.create(phone_number=payment.paying_number)
            
            session = UserSession(ussd_user.phone_number)
            session.transition_to("payment_failed", payment_failure_reason="Payment was declined")
            
            # Send failure message
            handler = StateRegistry.get_handler("payment_failed", session)
            message = handler.on_enter()
            
            if message:
                message.send()
            
            logger.warning(f"Payment {payment_ref} failed")
            
        elif attempt < 30:  # Max 5 minutes (30 * 10s)
            # Still pending, retry
            self.retry(
                args=[payment_ref, attempt + 1],
                countdown=10
            )
        else:
            # Timeout after 5 minutes
            payment.status = "failed"
            payment.save(update_fields=['status', 'last_updated'])
            
            send_payment_failed_message.delay(
                payment.paying_number,
                "Payment timeout - please try again"
            )
            
            logger.warning(f"Payment {payment_ref} timeout after 5 minutes")
        
    except Exception as exc:
        logger.error(f"Error polling payment: {exc}", exc_info=True)
        if attempt < 30:
            self.retry(exc=exc, countdown=10)


@shared_task(queue='high_priority')
def send_payment_failed_message(phone_number: str, reason: str):
    """
    Send payment failure notification.
    """
    try:
        session = UserSession(phone_number)
        session.context.update({'payment_failure_reason': reason})
        session._persist_to_redis()
        session.transition_to("payment_failed")
        
        handler = StateRegistry.get_handler("payment_failed", session)
        message = handler.on_enter()
        
        if message:
            message.send()
        
    except Exception as exc:
        logger.error(f"Error sending payment failed message: {exc}", exc_info=True)


@shared_task(queue='high_priority')
def send_welcome_to_subscriber(phone_number: str):
    """
    Send welcome message to new subscriber after payment.
    """
    try:
        # Get or create UssdUser
        try:
            ussd_user = UssdUser.objects.get(phone_number=phone_number)
        except UssdUser.DoesNotExist:
            ussd_user = UssdUser.objects.create(phone_number=phone_number)
        
        message = TextMessage(
            to=phone_number,
            body=(
                f"🎉 *Murakaza neza kuri Twara Premium!*\n\n"
                f"{ussd_user.name or 'Mukiriya'}, Subscription yawe yatangiye!\n\n"
                f"✅ Ushobora gukora ibizamini byinshi\n"
                f"✅ Reba raporo yawe buri minsi 3\n"
                f"✅ Tubahiriza 24/7\n\n"
                f"Tangira none: Andika 'IKIZAMINI'\n\n"
                f"Amahirwe menshi! 🍀"
            )
        )
        message.send()
        
    except Exception as exc:
        logger.error(f"Error sending welcome message: {exc}", exc_info=True)