# api/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import webhook, customer, payment, exam, admin

# Router for viewsets
router = DefaultRouter()
router.register(r'customers', customer.CustomerViewSet, basename='customer')
router.register(r'payments', payment.PaymentViewSet, basename='payment')
router.register(r'exams', exam.ExamViewSet, basename='exam')

urlpatterns = [
    # WhatsApp Webhook (Production)
    path('webhook/whatsapp/', webhook.WhatsAppWebhookView.as_view(), name='whatsapp-webhook'),
    
    # WhatsApp Webhook Verification (Required by Meta)
    path('webhook/whatsapp/verify/', webhook.WhatsAppWebhookVerifyView.as_view(), name='whatsapp-verify'),
    
    # Payment Callbacks
    path('callback/payment/mtn/', payment.MTNPaymentCallbackView.as_view(), name='mtn-callback'),
    path('callback/payment/airtel/', payment.AirtelPaymentCallbackView.as_view(), name='airtel-callback'),
    
    # Exam Completion Webhook
    path('webhook/exam/complete/', exam.ExamCompletionWebhookView.as_view(), name='exam-complete'),
    
    # REST API
    path('', include(router.urls)),
    
    # Customer specific endpoints
    path('customers/<str:phone_number>/session/', customer.CustomerSessionView.as_view(), name='customer-session'),
    path('customers/<str:phone_number>/performance/', customer.CustomerPerformanceView.as_view(), name='customer-performance'),
    path('customers/<str:phone_number>/subscriptions/', customer.CustomerSubscriptionsView.as_view(), name='customer-subscriptions'),
    
    # Testing & Admin Endpoints (Development only)
    path('test/send-message/', admin.TestSendMessageView.as_view(), name='test-send-message'),
    path('test/trigger-state/', admin.TestTriggerStateView.as_view(), name='test-trigger-state'),
    path('test/simulate-payment/', admin.TestSimulatePaymentView.as_view(), name='test-simulate-payment'),
    path('test/simulate-exam/', admin.TestSimulateExamView.as_view(), name='test-simulate-exam'),
    
    # Health Check
    path('health/', admin.HealthCheckView.as_view(), name='health-check'),
    
    # Metrics (Prometheus)
    path('metrics/', admin.MetricsView.as_view(), name='metrics'),
]