# api/views/customer.py
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from whatsapp_ussd.models import Customer, quiz, Performance, UserPayment
from api.serializers import (
    CustomerSerializer, 
    PerformanceSerializer,
    quizSerializer,
    UserPaymentSerializer
)
from whatsapp_ussd.services.core.session import UserSession
import logging

logger = logging.getLogger(__name__)


class CustomerViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for customers.
    
    Endpoints:
    - GET /api/customers/ - List all customers
    - POST /api/customers/ - Create customer
    - GET /api/customers/{id}/ - Get customer details
    - PUT /api/customers/{id}/ - Update customer
    - DELETE /api/customers/{id}/ - Delete customer
    """
    
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'phone_number'
    
    def get_queryset(self):
        """Filter based on query params"""
        queryset = super().get_queryset()
        
        # Filter by subscription status
        has_subscription = self.request.query_params.get('has_subscription')
        if has_subscription == 'true':
            queryset = queryset.filter(
                userpayment__status='succeeded'
            ).distinct()
        
        # Filter by last interaction
        active_only = self.request.query_params.get('active_only')
        if active_only == 'true':
            from datetime import timedelta
            from django.utils import timezone
            cutoff = timezone.now() - timedelta(days=7)
            queryset = queryset.filter(last_interaction__gte=cutoff)
        
        return queryset
    
    @action(detail=True, methods=['get'])
    def stats(self, request, phone_number=None):
        """
        Get customer statistics.
        
        GET /api/customers/{phone_number}/stats/
        """
        customer = self.get_object()
        
        # Calculate stats
        total_exams = quiz.objects.filter(customer=customer).count()
        passed_exams = quiz.objects.filter(
            customer=customer, 
            marks__gte=60
        ).count()
        
        active_subs = customer.get_active_transactions().count()
        total_paid = customer.get_total_amount_paid()
        
        performance = customer.performance if hasattr(customer, 'performance') else None
        
        stats = {
            'total_exams': total_exams,
            'passed_exams': passed_exams,
            'pass_rate': (passed_exams / total_exams * 100) if total_exams > 0 else 0,
            'active_subscriptions': active_subs,
            'total_paid': total_paid,
            'average_score': float(performance.avg_marks) if performance and performance.avg_marks else 0,
            'subscription_status': customer.subscription_status
        }
        
        return Response(stats)


class CustomerSessionView(APIView):
    """
    Get customer's current session state.
    
    GET /api/customers/{phone_number}/session/
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, phone_number):
        """Get current session state"""
        try:
            customer = get_object_or_404(Customer, phone_number=phone_number)
            session = UserSession(phone_number)
            
            data = {
                'phone_number': phone_number,
                'customer_name': customer.name,
                'current_state': session.current_state,
                'context': session.context,
                'message_history': session.message_history[-5:],  # Last 5 messages
                'last_interaction': customer.last_interaction
            }
            
            return Response(data)
        
        except Exception as e:
            logger.error(f"Error getting session: {e}", exc_info=True)
            return Response(
                {"error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CustomerPerformanceView(APIView):
    """
    Get customer's performance metrics.
    
    GET /api/customers/{phone_number}/performance/
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, phone_number):
        """Get performance data"""
        customer = get_object_or_404(Customer, phone_number=phone_number)
        
        try:
            performance = Performance.objects.get(customer=customer)
            serializer = PerformanceSerializer(performance)
            
            # Add recent quizzes
            recent_quizzes = quiz.objects.filter(
                customer=customer
            ).order_by('-taken')[:10]
            
            quiz_serializer = quizSerializer(recent_quizzes, many=True)
            
            data = {
                'performance': serializer.data,
                'recent_quizzes': quiz_serializer.data
            }
            
            return Response(data)
        
        except Performance.DoesNotExist:
            return Response(
                {"message": "No performance data yet"},
                status=status.HTTP_404_NOT_FOUND
            )


class CustomerSubscriptionsView(APIView):
    """
    Get customer's subscription history.
    
    GET /api/customers/{phone_number}/subscriptions/
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request, phone_number):
        """Get all subscriptions"""
        customer = get_object_or_404(Customer, phone_number=phone_number)
        
        # Get all transactions
        transactions = UserPayment.objects.filter(
            paying_number=phone_number
        ).order_by('-paid_on')
        
        serializer = UserPaymentSerializer(transactions, many=True)
        
        return Response({
            'subscriptions': serializer.data,
            'active_count': customer.get_active_transactions().count(),
            'total_spent': customer.get_total_amount_paid()
        })