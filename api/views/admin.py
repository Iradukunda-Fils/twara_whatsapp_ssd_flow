# api/views/admin.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.conf import settings
from django.utils import timezone
# from prometheus_client import generate_latest
import json
import logging

from whatsapp_ussd.models import Customer, UserPayment, quiz
from whatsapp_ussd.services.core.session import UserSession
from whatsapp_ussd.services.core.controller import StateFlowController
from whatsapp_ussd.services.core.registry import StateRegistry
from whatsapp import TextMessage, ListMessage, InteractiveMessage

logger = logging.getLogger(__name__)


class TestSendMessageView(APIView):
    """
    Test endpoint to send WhatsApp messages.
    
    POST /api/test/send-message/
    
    Body:
    {
        "phone_number": "250788123456",
        "message_type": "text" | "list" | "interactive",
        "body": "Message text",
        "options": {...}  // Optional, depends on message type
    }
    """
    
    permission_classes = [IsAuthenticated] if settings.DEBUG else [IsAdminUser]
    
    def post(self, request):
        """Send test message"""
        try:
            phone_number = request.data.get('phone_number')
            message_type = request.data.get('message_type', 'text')
            body = request.data.get('body', 'Test message from Twara')
            options = request.data.get('options', {})
            
            if not phone_number:
                return Response(
                    {"error": "phone_number is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create message based on type
            if message_type == 'text':
                message = TextMessage(
                    to=phone_number,
                    body=body,
                    preview_url=options.get('preview_url', False)
                )
            
            elif message_type == 'list':
                message = ListMessage(
                    to=phone_number,
                    body=body,
                    button_text=options.get('button_text', 'Select'),
                    header=options.get('header', 'Menu')
                )
                
                # Add test sections
                sections = options.get('sections', [
                    {
                        "title": "Test Section",
                        "rows": [
                            {"id": "test_1", "title": "Option 1", "description": "Test option 1"},
                            {"id": "test_2", "title": "Option 2", "description": "Test option 2"}
                        ]
                    }
                ])
                
                for section in sections:
                    message.add_section(section['title'], section['rows'])
            
            elif message_type == 'interactive':
                message = InteractiveMessage(
                    to=phone_number,
                    body=body,
                    header=options.get('header'),
                    footer=options.get('footer')
                )
                
                # Add test buttons
                buttons = options.get('buttons', [
                    {"id": "btn_1", "title": "Button 1"},
                    {"id": "btn_2", "title": "Button 2"}
                ])
                
                for btn in buttons[:3]:  # Max 3 buttons
                    message.add_reply_button(btn['id'], btn['title'])
            
            else:
                return Response(
                    {"error": f"Unsupported message type: {message_type}"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Send message
            response = message.send()
            
            return Response({
                "success": response.success,
                "message_id": response.message_id,
                "error": response.error_message
            })
        
        except Exception as e:
            logger.exception(f"Test send message error: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TestTriggerStateView(APIView):
    """
    Manually trigger state transition for testing.
    
    POST /api/test/trigger-state/
    
    Body:
    {
        "phone_number": "250788123456",
        "state": "main_menu",
        "context": {"key": "value"}  // Optional
    }
    """
    
    permission_classes = [IsAuthenticated] if settings.DEBUG else [IsAdminUser]
    
    def post(self, request):
        """Trigger state transition"""
        try:
            phone_number = request.data.get('phone_number')
            target_state = request.data.get('state')
            context_updates = request.data.get('context', {})
            
            if not all([phone_number, target_state]):
                return Response(
                    {"error": "phone_number and state are required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get or create customer
            customer, created = Customer.objects.get_or_create(
                phone_number=phone_number,
                defaults={'name': 'Test User'}
            )
            
            # Get session
            session = UserSession(phone_number)
            
            # Transition to state
            session.transition_to(target_state, **context_updates)
            
            # Get state handler and send message
            handler = StateRegistry.get_handler(target_state, session)
            message = handler.on_enter()
            
            if message:
                response = message.send()
                
                return Response({
                    "success": True,
                    "previous_state": session.current_state,
                    "current_state": target_state,
                    "message_sent": response.success,
                    "message_id": response.message_id
                })
            else:
                return Response({
                    "success": True,
                    "previous_state": session.current_state,
                    "current_state": target_state,
                    "message_sent": False
                })
        
        except Exception as e:
            logger.exception(f"Trigger state error: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TestSimulatePaymentView(APIView):
    """
    Simulate payment completion for testing.
    
    POST /api/test/simulate-payment/
    
    Body:
    {
        "access_code": "ABC123",
        "status": "succeeded" | "failed",
        "reason": "optional failure reason"
    }
    """
    
    permission_classes = [IsAuthenticated] if settings.DEBUG else [IsAdminUser]
    
    def post(self, request):
        """Simulate payment callback"""
        try:
            access_code = request.data.get('access_code')
            payment_status = request.data.get('status', 'succeeded')
            failure_reason = request.data.get('reason', 'Test failure')
            
            if not access_code:
                return Response(
                    {"error": "access_code is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find payment
            try:
                payment = UserPayment.objects.get(access_code=access_code)
            except UserPayment.DoesNotExist:
                return Response(
                    {"error": "Payment not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update payment status
            payment.status = payment_status
            payment.ref_id = f"TEST_{access_code}"
            payment.save(update_fields=['status', 'ref_id', 'last_updated'])
            
            # Trigger appropriate flow
            if payment_status == 'succeeded':
                from whatsapp_ussd.tasks import handle_payment_success
                handle_payment_success.delay(access_code)
                
                return Response({
                    "success": True,
                    "message": "Payment success flow triggered",
                    "access_code": access_code
                })
            
            else:
                from whatsapp_ussd.tasks import send_payment_failed_message
                send_payment_failed_message.delay(
                    payment.paying_number,
                    failure_reason
                )
                
                return Response({
                    "success": True,
                    "message": "Payment failure flow triggered",
                    "access_code": access_code,
                    "reason": failure_reason
                })
        
        except Exception as e:
            logger.exception(f"Simulate payment error: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TestSimulateExamView(APIView):
    """
    Simulate exam completion for testing.
    
    POST /api/test/simulate-exam/
    
    Body:
    {
        "phone_number": "250788123456",
        "marks": 75,
        "category_scores": {
            "amategekoMarks": 80,
            "KugendaMarks": 70,
            ...
        }
    }
    """
    
    permission_classes = [IsAuthenticated] if settings.DEBUG else [IsAdminUser]
    
    def post(self, request):
        """Simulate exam completion"""
        try:
            phone_number = request.data.get('phone_number')
            marks = request.data.get('marks', 75)
            category_scores = request.data.get('category_scores', {})
            
            if not phone_number:
                return Response(
                    {"error": "phone_number is required"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get customer
            customer = Customer.objects.get(phone_number=phone_number)
            
            # Create quiz record
            quiz_obj = quiz.objects.create(
                customer=customer,
                marks=marks,
                amategekoMarks=category_scores.get('amategekoMarks', marks),
                KugendaMarks=category_scores.get('KugendaMarks', marks),
                IbinyabizigaMarks=category_scores.get('IbinyabizigaMarks', marks),
                IbimenyetsoMarks=category_scores.get('IbimenyetsoMarks', marks),
                IbirangaMarks=category_scores.get('IbirangaMarks', marks),
                ImigenzurireMarks=category_scores.get('ImigenzurireMarks', marks)
            )
            
            # Trigger exam result flow
            session = UserSession(phone_number)
            session.update_context(quiz_id=quiz_obj.id)
            session.transition_to('exam_result')
            
            handler = StateRegistry.get_handler('exam_result', session)
            message = handler.on_enter()
            
            if message:
                response = message.send()
                
                return Response({
                    "success": True,
                    "quiz_id": quiz_obj.id,
                    "marks": marks,
                    "message_sent": response.success
                })
            
            return Response({
                "success": True,
                "quiz_id": quiz_obj.id,
                "marks": marks
            })
        
        except Customer.DoesNotExist:
            return Response(
                {"error": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        except Exception as e:
            logger.exception(f"Simulate exam error: {e}")
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class HealthCheckView(APIView):
    """
    Health check endpoint for load balancers.
    
    GET /api/health/
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        """Check system health"""
        try:
            # Check database
            Customer.objects.count()
            
            # Check Redis
            from django.core.cache import cache
            cache.set('health_check', '1', timeout=10)
            cache.get('health_check')
            
            # Check Celery workers
            from celery import current_app
            inspector = current_app.control.inspect()
            workers = inspector.active()
            
            celery_healthy = workers is not None and len(workers) > 0
            
            return Response({
                "status": "healthy",
                "timestamp": timezone.now().isoformat(),
                "services": {
                    "database": "ok",
                    "redis": "ok",
                    "celery": "ok" if celery_healthy else "degraded"
                }
            })
        
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return Response(
                {
                    "status": "unhealthy",
                    "error": str(e)
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )


class MetricsView(APIView):
    """
    Prometheus metrics endpoint.
    
    GET /api/metrics/
    """
    
    authentication_classes = []
    permission_classes = []
    
    def get(self, request):
        """Return Prometheus metrics"""
        from django.http import HttpResponse
        
        # metrics = generate_latest()
        metrics = None
        return HttpResponse(metrics, content_type='text/plain')