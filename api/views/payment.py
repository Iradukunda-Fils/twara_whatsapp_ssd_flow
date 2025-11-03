# api/views/payment.py
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.shortcuts import get_object_or_404
import json
import logging

from whatsapp_ussd.models import UserPayment, Customer
from api.serializers import UserPaymentSerializer
from whatsapp_ussd.services.core.session import UserSession
from whatsapp_ussd.tasks import handle_payment_success, send_payment_failed_message

logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ModelViewSet):
    """
    Payment management endpoints.
    
    Endpoints:
    - GET /api/payments/ - List all payments
    - GET /api/payments/{access_code}/ - Get payment details
    - POST /api/payments/ - Create payment (initiate)
    - PATCH /api/payments/{access_code}/ - Update payment status
    """
    
    queryset = UserPayment.objects.all()
    serializer_class = UserPaymentSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'access_code'
    
    def get_queryset(self):
        """Filter payments"""
        queryset = super().get_queryset()
        
        # Filter by status
        payment_status = self.request.query_params.get('status')
        if payment_status:
            queryset = queryset.filter(status=payment_status)
        
        # Filter by phone number
        phone = self.request.query_params.get('phone')
        if phone:
            queryset = queryset.filter(paying_number=phone)
        
        return queryset.order_by('-paid_on')
    
    @action(detail=True, methods=['post'])
    def verify(self, request, access_code=None):
        """
        Manually verify payment status.
        
        POST /api/payments/{access_code}/verify/
        """
        payment = self.get_object()
        
        # Poll payment status
        from whatsapp_ussd.tasks import poll_payment_status
        poll_payment_status.delay(access_code, attempt=0)
        
        return Response({
            "message": "Payment verification queued",
            "access_code": access_code
        })


@method_decorator(csrf_exempt, name='dispatch')
class MTNPaymentCallbackView(APIView):
    """
    MTN Mobile Money payment callback.
    
    POST /api/callback/payment/mtn/
    
    Expected payload:
    {
        "transactionId": "xxx",
        "status": "SUCCESSFUL" | "FAILED",
        "amount": 5000,
        "currency": "RWF",
        "externalId": "payment_access_code"
    }
    """
    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        """Handle MTN callback"""
        try:
            data = json.loads(request.body.decode('utf-8'))
            
            logger.info(f"MTN callback received: {data}")
            
            # Extract details
            transaction_id = data.get('transactionId')
            payment_status = data.get('status')
            external_id = data.get('externalId')  # Our access_code
            amount = data.get('amount')
            
            # Find payment
            try:
                payment = UserPayment.objects.get(access_code=external_id)
            except UserPayment.DoesNotExist:
                logger.error(f"Payment not found: {external_id}")
                return Response(
                    {"error": "Payment not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            # Update payment
            payment.ref_id = transaction_id
            
            if payment_status == 'SUCCESSFUL':
                payment.status = 'succeeded'
                payment.save(update_fields=['status', 'ref_id', 'last_updated'])
                
                # Trigger success flow
                handle_payment_success.delay(payment.access_code)
                
                logger.info(f"MTN payment succeeded: {external_id}")
            
            elif payment_status == 'FAILED':
                payment.status = 'failed'
                payment.save(update_fields=['status', 'ref_id', 'last_updated'])
                
                # Notify user
                send_payment_failed_message.delay(
                    payment.paying_number,
                    "Payment was declined by MTN"
                )
                
                logger.warning(f"MTN payment failed: {external_id}")
            
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.exception(f"MTN callback error: {e}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@method_decorator(csrf_exempt, name='dispatch')
class AirtelPaymentCallbackView(APIView):
    """
    Airtel Money payment callback.
    
    POST /api/callback/payment/airtel/
    
    Similar structure to MTN callback.
    """
    
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        """Handle Airtel callback"""
        try:
            data = json.loads(request.body.decode('utf-8'))
            
            logger.info(f"Airtel callback received: {data}")
            
            # Similar processing to MTN
            transaction_id = data.get('transactionId')
            payment_status = data.get('status')
            external_id = data.get('externalId')
            
            # Find and update payment
            try:
                payment = UserPayment.objects.get(access_code=external_id)
            except UserPayment.DoesNotExist:
                return Response(
                    {"error": "Payment not found"},
                    status=status.HTTP_404_NOT_FOUND
                )
            
            payment.ref_id = transaction_id
            
            if payment_status == 'SUCCESSFUL':
                payment.status = 'succeeded'
                payment.save(update_fields=['status', 'ref_id', 'last_updated'])
                handle_payment_success.delay(payment.access_code)
            
            elif payment_status == 'FAILED':
                payment.status = 'failed'
                payment.save(update_fields=['status', 'ref_id', 'last_updated'])
                send_payment_failed_message.delay(
                    payment.paying_number,
                    "Payment was declined by Airtel"
                )
            
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        
        except Exception as e:
            logger.exception(f"Airtel callback error: {e}")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )