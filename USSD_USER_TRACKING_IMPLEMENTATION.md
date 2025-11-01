# UssdUser Tracking Implementation Guide

## Overview
This document outlines how **UssdUser** model is now used for all user tracking, progress monitoring, and activity analytics throughout the codebase.

---

## ✅ What's Already Implemented

### 1. **Message Tracking**
- ✅ `total_messages` counter increments automatically via `session.add_message()`
- ✅ `last_interaction` timestamp updated automatically
- ✅ Implemented in `UserSession.add_message()` → calls `ussd_user.increment_message_count()`

### 2. **State Tracking**
- ✅ `current_flow_state` and `state_context` stored in UssdUser
- ✅ State transitions update UssdUser via `session.transition_to()`

### 3. **Activity Queries**
- ✅ `send_daily_reminders()` - Filters by `UssdUser.last_interaction`
- ✅ `cleanup_expired_sessions()` - Uses `UssdUser.last_interaction`
- ✅ All queries use UssdUser for activity-based filtering

### 4. **Event Logging**
- ✅ `UserEvent` model now tracks both `customer` and `ussd_user`
- ✅ All event logging includes UssdUser reference for analytics

### 5. **Behavioral Flags**
- ✅ `failed_exams_count` - Updated in `update_customer_performance` task
- ✅ `needs_coaching` - Set based on `failed_exams_count` in UssdUser
- ✅ `is_vip` - Set in payment success handler using UssdUser

---

## 📋 UssdUser Helper Methods

### `increment_message_count()`
Automatically increments message count and updates last interaction.

```python
ussd_user.increment_message_count()  # total_messages++, last_interaction = now
```

### `update_last_interaction()`
Updates last interaction timestamp.

```python
ussd_user.update_last_interaction()
```

### `get_activity_summary()`
Returns comprehensive activity data for progress tracking.

```python
summary = ussd_user.get_activity_summary()
# Returns:
# {
#     'total_messages': 42,
#     'last_interaction': datetime(...),
#     'current_state': 'exam_result',
#     'failed_exams': 2,
#     'needs_coaching': False,
#     'is_vip': True,
#     'days_since_last_interaction': 3,
#     'preferred_language': 'rw'
# }
```

---

## 🎯 Usage Patterns

### When to Use Customer
- User identification (name, phone_number)
- Payment/subscription data
- Quiz results
- Basic profile information

### When to Use UssdUser
- **All activity tracking** (messages, interactions)
- **State management** (current state, context)
- **Progress monitoring** (failed exams, coaching needs)
- **Session data** (last interaction, preferred language)
- **Behavioral flags** (VIP status, coaching needs)

---

## 🔧 Implementation Guidelines

### State Handlers
```python
class MyStateHandler(BaseStateHandler):
    def on_enter(self):
        customer = self.customer  # Customer for user data
        ussd_user = self.ussd_user  # UssdUser for tracking
        
        # Use customer for data access
        phone = customer.phone_number
        
        # Use ussd_user for tracking/progress
        if ussd_user.failed_exams_count >= 3:
            # Show coaching offer
            pass
```

### Tasks
```python
@shared_task
def my_task(customer_id: int):
    customer = Customer.objects.get(id=customer_id)
    ussd_user, _ = UssdUser.objects.get_or_create(customer=customer)
    
    # Update tracking via UssdUser
    ussd_user.failed_exams_count += 1
    ussd_user.save()
```

### Queries for Activity/Progress
```python
# ✅ CORRECT - Use UssdUser for activity queries
active_users = UssdUser.objects.filter(
    last_interaction__gte=timezone.now() - timedelta(hours=24)
).select_related('customer')

# ❌ WRONG - Don't query Customer for activity fields
# active_users = Customer.objects.filter(last_interaction__gte=...)  # This field doesn't exist!
```

---

## 📝 Patterns to Follow

### 1. Quiz Result Processing (When Implementing Exam States)

When processing quiz results that indicate failure, update UssdUser:

```python
# In exam_result state handler or task
def process_quiz_result(customer, quiz_score):
    ussd_user, _ = UssdUser.objects.get_or_create(customer=customer)
    
    if quiz_score < 60:  # Failed
        ussd_user.failed_exams_count = (ussd_user.failed_exams_count or 0) + 1
        ussd_user.save(update_fields=['failed_exams_count'])
        
        # Check if coaching needed
        if ussd_user.failed_exams_count >= 3:
            ussd_user.needs_coaching = True
            ussd_user.save(update_fields=['needs_coaching'])
```

### 2. Message Sending
Always update UssdUser tracking:

```python
# Automatically handled by session.add_message()
session.add_message(message, sender='bot')  # Updates total_messages, last_interaction
```

### 3. Activity Queries
Always query through UssdUser:

```python
# Find active users (interacted in last 24h)
active = UssdUser.objects.filter(
    last_interaction__gte=timezone.now() - timedelta(hours=24)
).select_related('customer')

for ussd_user in active:
    customer = ussd_user.customer
    # Use customer for user data, ussd_user for tracking
```

### 4. Progress Reports
Use UssdUser activity data:

```python
ussd_user = session.customer  # This is UssdUser
summary = ussd_user.get_activity_summary()

report = f"Total messages: {summary['total_messages']}\n"
report += f"Last active: {summary['days_since_last_interaction']} days ago\n"
report += f"Failed exams: {summary['failed_exams']}"
```

---

## ⚠️ Common Mistakes to Avoid

### ❌ Wrong: Accessing tracking fields on Customer
```python
customer.last_interaction  # ❌ This field is in UssdUser!
customer.failed_exams_count  # ❌ This field is in UssdUser!
```

### ✅ Correct: Access via UssdUser
```python
ussd_user = UssdUser.objects.get(customer=customer)
ussd_user.last_interaction  # ✅
ussd_user.failed_exams_count  # ✅
```

### ❌ Wrong: Querying Customer for activity
```python
Customer.objects.filter(last_interaction__lt=...)  # ❌ Field doesn't exist!
```

### ✅ Correct: Query UssdUser
```python
UssdUser.objects.filter(last_interaction__lt=...)  # ✅
```

---

## 🔄 Migration Checklist

If you have existing code that needs updating:

- [ ] Find all references to `customer.last_interaction` → Use `ussd_user.last_interaction`
- [ ] Find all references to `customer.failed_exams_count` → Use `ussd_user.failed_exams_count`
- [ ] Find all references to `customer.needs_coaching` → Use `ussd_user.needs_coaching`
- [ ] Find all references to `customer.is_vip` → Use `ussd_user.is_vip`
- [ ] Find all references to `customer.current_flow_state` → Use `ussd_user.current_flow_state`
- [ ] Update all activity queries to use `UssdUser.objects.filter(...)` instead of `Customer.objects.filter(...)`
- [ ] Ensure all UserEvent creation includes `ussd_user` parameter
- [ ] Use `ussd_user.increment_message_count()` instead of manual counter updates

---

## 📊 Analytics Queries Examples

### Get Most Active Users
```python
active_users = UssdUser.objects.filter(
    total_messages__gte=50,
    last_interaction__gte=timezone.now() - timedelta(days=7)
).order_by('-total_messages')[:10]
```

### Get Users Needing Coaching
```python
needs_coaching = UssdUser.objects.filter(
    needs_coaching=True,
    last_interaction__gte=timezone.now() - timedelta(days=30)
).select_related('customer')
```

### Get VIP Users Activity
```python
vip_users = UssdUser.objects.filter(
    is_vip=True
).order_by('-last_interaction')
```

### Get User Engagement Stats
```python
# Average messages per user
avg_messages = UssdUser.objects.aggregate(
    avg=Avg('total_messages')
)['avg']

# Users active in last 24 hours
active_24h = UssdUser.objects.filter(
    last_interaction__gte=timezone.now() - timedelta(hours=24)
).count()
```

---

## ✅ Summary

**All user tracking, progress monitoring, and activity analytics now rely on UssdUser model:**

- ✅ Message counts tracked in UssdUser
- ✅ Interaction timestamps in UssdUser
- ✅ State management in UssdUser
- ✅ Progress metrics in UssdUser
- ✅ Behavioral flags in UssdUser
- ✅ All queries use UssdUser for activity filtering
- ✅ All events log UssdUser reference

**Customer model is now only used for:**
- Basic user identification
- Payment/subscription data
- Quiz results
- Profile information

The separation ensures clean data architecture and proper tracking of user progress and activity!

