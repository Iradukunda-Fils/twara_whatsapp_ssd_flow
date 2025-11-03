from django.db import models
from django.db.models import ExpressionWrapper, F, Sum, CASCADE
from django.utils import timezone
from django.utils.timesince import timesince
from django.contrib.auth.models import User
from datetime import timedelta
from shortuuid.django_fields import ShortUUIDField


from django.db import models
from django.db.models import ExpressionWrapper, F, Sum, Avg
from django.utils import timezone
from django.utils.timesince import timesince
from django.contrib.auth.models import User
from datetime import timedelta
from shortuuid.django_fields import ShortUUIDField


# ------------------------
# Core Customer Models
# ------------------------

class Customer(models.Model):
    name = models.CharField(max_length=255, null=True, blank=True)
    phone_number = models.CharField(max_length=15, unique=True)
    exam_date = models.DateField(null=True, blank=True)
    feedback = models.TextField(null=True, blank=True)
    Has_been_contacted=models.BooleanField(default=False)
    last_contacted=models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['phone_number']),
            models.Index(fields=['exam_date']),
        ]
        ordering = ['name']
    
    def __str__(self):
        return self.name or f'Customer {self.phone_number}'

    def get_transactions(self):
        return UserPayment.objects.filter(paying_number=self.phone_number)

    def get_active_transactions(self):
        now = timezone.now()
        return self.get_transactions().annotate(
            expiration_date=ExpressionWrapper(
                F('paid_on') + F('expiration') * timedelta(days=1),
                output_field=models.DateTimeField()
            )
        ).filter(expiration_date__gt=now)

    def get_expired_transactions(self):
        now = timezone.now()
        return self.get_transactions().annotate(
            expiration_date=ExpressionWrapper(
                F('paid_on') + F('expiration') * timedelta(days=1),
                output_field=models.DateTimeField()
            )
        ).filter(expiration_date__lte=now)

    def get_last_expired_subscription(self):
        return self.get_expired_transactions().order_by('-expiration_date').first()

    def get_total_subscriptions(self):
        return self.get_transactions().count()

    def get_total_amount_paid(self):
        return self.get_transactions().aggregate(total=Sum('amount_paid'))['total'] or 0
    @property
    def subscription_status(self):
        active_transactions = self.get_active_transactions()
        if active_transactions.exists():
            return "Active"
        last_expired = self.get_last_expired_subscription()
        if last_expired:
            return f"RWF {last_expired.amount_paid:.2f} code expired {timesince(last_expired.expiration_date)} ago"
        return "No subscriptions"


class UssdUser(Customer):
    """
    Represents a USSD user with session/state tracking.
    Inherits from Customer.
    """
    current_flow_state = models.CharField(max_length=50, default='welcome', db_index=True)
    state_context = models.JSONField(default=dict, blank=True)

    total_messages = models.IntegerField(default=0)
    last_interaction = models.DateTimeField(auto_now=True, db_index=True)
    preferred_language = models.CharField(max_length=5, default='rw')

    failed_exams_count = models.IntegerField(default=0)
    needs_coaching = models.BooleanField(default=False)
    is_vip = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['current_flow_state']),
            models.Index(fields=['last_interaction']),
        ]

    def __str__(self):
        return f"USSD User: {self.phone_number} ({self.current_flow_state})"

    # --- Activity Helpers ---
    def increment_message_count(self):
        self.total_messages += 1
        self.last_interaction = timezone.now()
        self.save(update_fields=['total_messages', 'last_interaction'])

    def update_last_interaction(self):
        self.last_interaction = timezone.now()
        self.save(update_fields=['last_interaction'])

    def get_activity_summary(self):
        return {
            'total_messages': self.total_messages,
            'last_interaction': self.last_interaction,
            'current_state': self.current_flow_state,
            'failed_exams': self.failed_exams_count,
            'needs_coaching': self.needs_coaching,
            'is_vip': self.is_vip,
            'days_since_last_interaction': (timezone.now() - self.last_interaction).days if self.last_interaction else None,
            'preferred_language': self.preferred_language,
            'phone_number': self.phone_number,
            'name': self.name,
        }

    
    class Meta:
        indexes = [
            models.Index(fields=['current_flow_state']),
            models.Index(fields=['last_interaction']),
        ]


# Alias for backward compatibility or convenience
USSD_USER = UssdUser

# ------------------------
# Payments / Subscriptions
# ------------------------

class UserPayment(models.Model):
    STATUS_CHOICES = [
        ("pending", "PENDING"),
        ("failed", "FAILED"),
        ("succeded", "SUCCESS"),
    ]

    access_code = ShortUUIDField(
        length=6,
        max_length=40,
        alphabet="ABCDEFG1234",
        primary_key=True,
    )

    ref_id = models.CharField(max_length=120, default="abc")

    paying_number = models.CharField(max_length=12)
    paid_on = models.DateTimeField(auto_now=True)
    amount_paid = models.IntegerField()
    is_used = models.BooleanField(default=False)
    exams = models.IntegerField(null=True)
    expiration = models.IntegerField(null=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    last_updated = models.DateTimeField(null=True, auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['paying_number']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.paying_number} | {self.amount_paid} | {self.status}"





# ------------------------
# Quiz & Performance
# ------------------------

class quiz(models.Model):
    language = models.CharField(max_length=10, null=True, blank=True, default='rw')
    taken = models.DateTimeField(auto_now_add=True, null=True)
    customer = models.ForeignKey(Customer, null=True, blank=True, on_delete=models.SET_NULL)
    user = models.ForeignKey(User, null=True, blank=True, on_delete=CASCADE)
    marks = models.DecimalField(null=True, max_digits=5, decimal_places=2)
    amategekoMarks = models.DecimalField(
        null=True, max_digits=5, decimal_places=2)
    KugendaMarks = models.DecimalField(
        null=True, max_digits=5, decimal_places=2)
    IbinyabizigaMarks = models.DecimalField(
        null=True, max_digits=5, decimal_places=2)
    IbimenyetsoMarks = models.DecimalField(
        null=True, max_digits=5, decimal_places=2)
    IbirangaMarks = models.DecimalField(
        null=True, max_digits=5, decimal_places=2)
    ImigenzurireMarks = models.DecimalField(
        null=True, max_digits=5, decimal_places=2)

    def __str__(self):
        return f"Quiz for {self.customer or self.user} on {self.taken}"

class Performance(models.Model):
    # UssdUser inherits from Customer, so this can reference either
    customer = models.OneToOneField(Customer,null=True, blank=True, on_delete=models.CASCADE, related_name="performance")
    user = models.ForeignKey(User, null=True, blank=True, on_delete=CASCADE)
    
    # Average scores for the last 5 quizzes (or all if less than 5)
    avg_marks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_amategekoMarks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_KugendaMarks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_IbinyabizigaMarks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_IbimenyetsoMarks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_IbirangaMarks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    avg_ImigenzurireMarks = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    mastered_questions=models.IntegerField(default=0)
    
    total_attempts = models.IntegerField(default=0)
    last_quiz_date = models.DateTimeField(null=True, blank=True)
    
    def update_performance(self):
        """
        Update performance metrics for this Performance instance.
        Calculates averages from the last 5 quizzes (or all if less than 5).
        """
        from django.db.models import Avg
        
        # Get quizzes based on whether we have user or customer
        if self.user:
            quizzes = quiz.objects.filter(user=self.user).order_by('-taken')
        elif self.customer:
            quizzes = quiz.objects.filter(customer=self.customer).order_by('-taken')
        else:
            # No user or customer, skip update
            return
        
        self.total_attempts = quizzes.count()
        
        if self.total_attempts > 0:
            self.last_quiz_date = quizzes.first().taken
        
        # Get last 5 quizzes (or all if less than 5)
        last_five_quizzes = quizzes[:5] if quizzes.count() >= 5 else quizzes
        
        if last_five_quizzes:
            # Calculate averages using aggregation for efficiency
            aggregates = last_five_quizzes.aggregate(
                avg_marks=Avg('marks'),
                avg_amategekoMarks=Avg('amategekoMarks'),
                avg_KugendaMarks=Avg('KugendaMarks'),
                avg_IbinyabizigaMarks=Avg('IbinyabizigaMarks'),
                avg_IbimenyetsoMarks=Avg('IbimenyetsoMarks'),
                avg_IbirangaMarks=Avg('IbirangaMarks'),
                avg_ImigenzurireMarks=Avg('ImigenzurireMarks'),
            )
            
            self.avg_marks = aggregates['avg_marks']
            self.avg_amategekoMarks = aggregates['avg_amategekoMarks']
            self.avg_KugendaMarks = aggregates['avg_KugendaMarks']
            self.avg_IbinyabizigaMarks = aggregates['avg_IbinyabizigaMarks']
            self.avg_IbimenyetsoMarks = aggregates['avg_IbimenyetsoMarks']
            self.avg_IbirangaMarks = aggregates['avg_IbirangaMarks']
            self.avg_ImigenzurireMarks = aggregates['avg_ImigenzurireMarks']
        
        self.save()
    
    def __str__(self):
        if self.customer:
            return f"Performance for {self.customer.phone_number}"
        elif self.user:
            return f"Performance for {self.user.username}"
        return "Performance (no user/customer)"



# ------------------------
# Event Logging / Analytics
# ------------------------

class UserEvent(models.Model):
    """
    Immutable log of all state transitions and user actions.
    Used for analytics, debugging, and audit trails.
    
    Note: Since UssdUser inherits from Customer, we primarily use UssdUser.
    The customer field can reference either Customer or UssdUser (which IS a Customer).
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='events')
    event_type = models.CharField(max_length=50, db_index=True)
    from_state = models.CharField(max_length=50, null=True, blank=True)
    to_state = models.CharField(max_length=50, null=True, blank=True)
    metadata = models.JSONField(default=dict)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['customer', '-timestamp']),
            models.Index(fields=['event_type', '-timestamp']),
        ]
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.event_type} - {self.customer.phone_number} at {self.timestamp}"

    @property
    def ussd_user(self):
        if isinstance(self.customer, UssdUser):
            return self.customer
        try:
            return UssdUser.objects.get(pk=self.customer.pk)
        except UssdUser.DoesNotExist:
            return None