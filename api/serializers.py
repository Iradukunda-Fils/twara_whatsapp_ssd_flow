# api/serializers.py
from rest_framework import serializers
from whatsapp_ussd.models import Customer, UserPayment, quiz, Performance, UserEvent
from django.utils import timezone
from datetime import timedelta


class CustomerSerializer(serializers.ModelSerializer):
    """Customer serializer with computed fields"""
    
    subscription_status = serializers.CharField(read_only=True)
    total_exams = serializers.SerializerMethodField()
    active_subscriptions = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'phone_number', 'name', 'exam_date', 'feedback',
            'current_flow_state', 'preferred_language',
            'subscription_status', 'total_exams', 'active_subscriptions',
            'failed_exams_count', 'needs_coaching', 'is_vip',
            'last_interaction', 'total_messages'
        ]
        read_only_fields = [
            'subscription_status', 'total_exams', 'active_subscriptions',
            'last_interaction', 'total_messages'
        ]
    
    def get_total_exams(self, obj):
        return quiz.objects.filter(customer=obj).count()
    
    def get_active_subscriptions(self, obj):
        return obj.get_active_transactions().count()


class UserPaymentSerializer(serializers.ModelSerializer):
    """Payment serializer with expiration info"""
    
    expiration_date = serializers.SerializerMethodField()
    days_remaining = serializers.SerializerMethodField()
    is_active = serializers.SerializerMethodField()
    
    class Meta:
        model = UserPayment
        fields = [
            'access_code', 'ref_id', 'paying_number', 'paid_on',
            'amount_paid', 'expiration', 'status', 'is_used',
            'exams', 'last_updated', 'expiration_date',
            'days_remaining', 'is_active'
        ]
        read_only_fields = [
            'access_code', 'paid_on', 'last_updated',
            'expiration_date', 'days_remaining', 'is_active'
        ]
    
    def get_expiration_date(self, obj):
        if obj.paid_on and obj.expiration:
            exp_date = obj.paid_on + timedelta(days=obj.expiration)
            return exp_date.isoformat()
        return None
    
    def get_days_remaining(self, obj):
        if obj.paid_on and obj.expiration and obj.status == 'succeeded':
            exp_date = obj.paid_on + timedelta(days=obj.expiration)
            remaining = (exp_date - timezone.now()).days
            return max(0, remaining)
        return 0
    
    def get_is_active(self, obj):
        if obj.status != 'succeeded':
            return False
        if obj.paid_on and obj.expiration:
            exp_date = obj.paid_on + timedelta(days=obj.expiration)
            return timezone.now() < exp_date
        return False


class quizSerializer(serializers.ModelSerializer):
    """quiz serializer with calculated fields"""
    
    passed = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    
    class Meta:
        model = quiz
        fields = [
            'id', 'language', 'taken', 'customer', 'customer_name',
            'marks', 'amategekoMarks', 'KugendaMarks',
            'IbinyabizigaMarks', 'IbimenyetsoMarks',
            'IbirangaMarks', 'ImigenzurireMarks',
            'failed_questions', 'succeeded_questions', 'passed'
        ]
        read_only_fields = ['id', 'taken', 'customer_name', 'passed']
    
    def get_passed(self, obj):
        return obj.marks >= 60 if obj.marks else False


class PerformanceSerializer(serializers.ModelSerializer):
    """Performance serializer"""
    
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    pass_rate = serializers.SerializerMethodField()
    
    class Meta:
        model = Performance
        fields = [
            'customer', 'customer_name', 'avg_marks',
            'avg_amategekoMarks', 'avg_KugendaMarks',
            'avg_IbinyabizigaMarks', 'avg_IbimenyetsoMarks',
            'avg_IbirangaMarks', 'avg_ImigenzurireMarks',
            'mastered_questions', 'total_attempts',
            'last_quiz_date', 'is_improving', 'pass_rate'
        ]
        read_only_fields = ['customer_name', 'pass_rate']
    
    def get_pass_rate(self, obj):
        if obj.total_attempts == 0:
            return 0
        
        passed = quiz.objects.filter(
            customer=obj.customer,
            marks__gte=60
        ).count()
        
        return (passed / obj.total_attempts) * 100


class UserEventSerializer(serializers.ModelSerializer):
    """Event log serializer"""
    
    customer_phone = serializers.CharField(source='customer.phone_number', read_only=True)
    
    class Meta:
        model = UserEvent
        fields = [
            'id', 'customer', 'customer_phone', 'event_type',
            'from_state', 'to_state', 'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'customer_phone', 'timestamp']