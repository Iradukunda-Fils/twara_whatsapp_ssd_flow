from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Customer, UssdUser, UserPayment, quiz, Performance, UserEvent


# ------------------------
# Customer Admin
# ------------------------

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'phone_number',
        'Has_been_contacted',
        'last_contacted',
        'subscription_status',
        'get_total_amount_paid',
        'view_payments_link',
    )
    list_filter = ('Has_been_contacted', 'exam_date')
    search_fields = ('name', 'phone_number')
    readonly_fields = ('get_total_amount_paid', 'subscription_status')
    ordering = ('name',)

    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'phone_number', 'exam_date', 'feedback')
        }),
        ('Contact Status', {
            'fields': ('Has_been_contacted', 'last_contacted'),
            'classes': ('collapse',)
        }),
        ('Subscription Info', {
            'fields': ('subscription_status', 'get_total_amount_paid'),
        }),
    )

    def view_payments_link(self, obj):
        """Create a clickable link to view UserPayments filtered by this phone number."""
        url = (
            reverse("admin:whatsapp_ussd_userpayment_changelist")
            + f"?paying_number__exact={obj.phone_number}"
        )
        return format_html('<a href="{}" target="_blank">View Payments</a>', url)
    view_payments_link.short_description = "Payments"


# ------------------------
# USSD User Admin
# ------------------------

@admin.register(UssdUser)
class UssdUserAdmin(CustomerAdmin):
    list_display = (
        'name',
        'phone_number',
        'current_flow_state',
        'total_messages',
        'last_interaction',
        'preferred_language',
        'failed_exams_count',
        'needs_coaching',
        'is_vip',
        'subscription_status',
        'view_payments_link',
    )
    list_filter = (
        'current_flow_state',
        'preferred_language',
        'needs_coaching',
        'is_vip',
        'Has_been_contacted',
    )
    readonly_fields = ('total_messages', 'last_interaction', 'subscription_status')

    fieldsets = (
        ('User Info', {
            'fields': ('name', 'phone_number', 'preferred_language')
        }),
        ('Flow & State', {
            'fields': ('current_flow_state', 'state_context'),
            'classes': ('collapse',)
        }),
        ('Activity', {
            'fields': ('total_messages', 'last_interaction', 'failed_exams_count', 'needs_coaching', 'is_vip'),
        }),
        ('Subscription Info', {
            'fields': ('subscription_status',),
        }),
    )


# ------------------------
# UserPayment Admin
# ------------------------

@admin.register(UserPayment)
class UserPaymentAdmin(admin.ModelAdmin):
    list_display = ('access_code', 'paying_number', 'amount_paid', 'status', 'paid_on', 'expiration')
    list_filter = ('status',)
    search_fields = ('access_code', 'paying_number')
    readonly_fields = ('access_code', 'paid_on', 'last_updated')


# ------------------------
# Quiz Admin
# ------------------------

@admin.register(quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ('customer', 'user', 'taken', 'marks', 'amategekoMarks', 'KugendaMarks')
    list_filter = ('language',)
    search_fields = ('customer__phone_number', 'user__username')
    readonly_fields = ('taken',)


# ------------------------
# Performance Admin
# ------------------------

@admin.register(Performance)
class PerformanceAdmin(admin.ModelAdmin):
    list_display = ('customer', 'user', 'avg_marks', 'avg_amategekoMarks', 'avg_KugendaMarks', 'total_attempts', 'last_quiz_date')
    search_fields = ('customer__phone_number', 'user__username')
    readonly_fields = ('avg_marks', 'avg_amategekoMarks', 'avg_KugendaMarks', 'avg_IbinyabizigaMarks',
                       'avg_IbimenyetsoMarks', 'avg_IbirangaMarks', 'avg_ImigenzurireMarks', 'total_attempts', 'last_quiz_date')


# ------------------------
# UserEvent Admin
# ------------------------

@admin.register(UserEvent)
class UserEventAdmin(admin.ModelAdmin):
    list_display = ('event_type', 'customer', 'from_state', 'to_state', 'timestamp')
    list_filter = ('event_type',)
    search_fields = ('customer__phone_number', 'event_type')
    readonly_fields = ('timestamp', 'metadata')
    ordering = ('-timestamp',)
