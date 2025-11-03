# api/views/exam.py
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
import json
import logging

from whatsapp_ussd.models import quiz, Customer
from api.serializers import quizSerializer
from whatsapp_ussd.services.core.session import UserSession
from whatsapp_ussd.services.core.registry import StateRegistry

logger = logging.getLogger(__name__)


class ExamViewSet(viewsets.ModelViewSet):
    """
    Exam/quiz management endpoints.
    
    Endpoints:
    - GET /api/exams/ - List all exams
    - GET /api/exams/{id}/ - Get exam details
    - POST /api/exams/ - Create exam
    - PATCH /api/exams/{id}/ - Update exam (submit answers)
    """
    
    queryset = quiz.objects.all()
    serializer_class = quizSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter exams"""
        queryset = super().get_queryset()
        
        # Filter by customer
        phone = self.request.query_params.get('phone')
        if phone:
            queryset = queryset.filter(customer__phone_number=phone)
        
        # Filter by date
        date_from = self.request.query_params.get('date_from')
        if date_from:
            queryset = queryset.filter(taken__gte=date_from)
        
        return queryset.order_by('-taken')


@method_decorator(csrf_exempt, name='dispatch')
class ExamCompletionWebhookView(APIView):
    """
    Exam completion webhook from external exam platform.
    
    POST /api/webhook/exam/complete/
    
    Expected payload:
    {
        "quiz_id": 123,
        "phone_number": "250788123456",
        "marks": 75.5,
        "category_scores": {
            "amategekoMarks": 80,
            "KugendaMarks": 70,
            "IbinyabizigaMarks": 75,
            "IbimenyetsoMarks": 78
        },
        "failed_questions": [1, 5, 10],
        "succeeded_questions": [2, 3, 4, ...]
    }
    """
    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        """Handle exam completion"""
        try:
            data = json.loads(request.body.decode('utf-8'))
            
            logger.info(f"Exam completion webhook: {data}")
            
            # Extract data
            quiz_id = data.get('quiz_id')
            phone_number = data.get('phone_number')
            marks = data.get('marks')
            category_scores = data.get('category_scores', {})
            failed_questions = data.get('failed_questions', [])
            succeeded_questions = data.get('succeeded_questions', [])
            
            # Validate
            if not all([quiz_id, phone_number, marks is not None]):
                return Response(
                    {"error": "Missing required fields"},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Find quiz
            try:
                quiz_obj = quiz.objects.get(id=quiz_id)
            except quiz.DoesNotExist:
                return Response(
                    {"error": "quiz not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update quiz with results
            quiz_obj.marks = marks
            quiz_obj.amategekoMarks = category_scores.get('amategekoMarks')
            quiz_obj.KugendaMarks = category_scores.get('KugendaMarks')
            quiz_obj.IbinyabizigaMarks = category_scores.get('IbinyabizigaMarks')
            quiz_obj.IbimenyetsoMarks = category_scores.get('IbimenyetsoMarks')
            quiz_obj.IbirangaMarks = category_scores.get('IbirangaMarks')
            quiz_obj.ImigenzurireMarks = category_scores.get('ImigenzurireMarks')
            quiz_obj.failed_questions = failed_questions
            quiz_obj.succeeded_questions = succeeded_questions
            quiz_obj.save()
            
            # Get customer
            customer = Customer.objects.get(phone_number=phone_number)
            
            # Transition to exam_result state
            session = UserSession(phone_number)
            session.update_context(quiz_id=quiz_id, exam_completed=True)
            session.transition_to('exam_result')
            
            # Send exam result message
            from whatsapp_ussd.services.core.registry import StateRegistry
            handler = StateRegistry.get_handler('exam_result', session)
            message = handler.on_enter()
            
            if message:
                response = message.send()
                
                if not response.success:
                    logger.error(f"Failed to send exam result: {response.error_message}")
            
            logger.info(f"Exam {quiz_id} completed for {phone_number} with score {marks}%")
            
            return Response({
                "status": "success",
                "quiz_id": quiz_id,
                "marks": marks,
                "message": "Results sent to customer"
            }, status=status.HTTP_200_OK)
        
        except Customer.DoesNotExist:
            logger.error(f"Customer not found: {phone_number}")
            return Response(
                {"error": "Customer not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        except Exception as e:
            logger.exception(f"Exam completion webhook error: {e}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )