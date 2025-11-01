# Model Method Refactoring Summary

## Problem
The `update_performance` method was a standalone function that took `self` as a parameter, indicating it should be a model method. Additionally, the codebase needed to handle the distinction between `Customer` (core user data) and `UssdUser` (session/state tracking).

## Solution Implemented

### 1. **Moved `update_performance` to Performance Model**
   - ✅ Added `update_performance()` as an instance method on the `Performance` model
   - ✅ The method now has proper access to `self.user` and `self.customer`
   - ✅ Uses efficient Django aggregation queries
   - ✅ Automatically saves the instance after updating

### 2. **Created UssdUser Model**
   - ✅ Separated session state tracking from customer core data
   - ✅ `UssdUser` has a ForeignKey to `Customer`
   - ✅ Contains state tracking fields (`current_flow_state`, `state_context`)
   - ✅ Contains session metadata (`last_interaction`, `preferred_language`)
   - ✅ Added `USSD_USER` alias for backward compatibility

### 3. **Updated Session Management**
   - ✅ `UserSession.customer` now returns `UssdUser` instead of `Customer`
   - ✅ `_get_or_create_customer()` creates both `Customer` and `UssdUser`
   - ✅ State transitions update `UssdUser` model
   - ✅ UserEvent logging uses the underlying `Customer` from `UssdUser.customer`

### 4. **Fixed State Handlers**
   - ✅ Added `customer` property in `BaseStateHandler` for backward compatibility
   - ✅ Property automatically extracts `Customer` from `UssdUser`
   - ✅ State handlers can still use `self.customer.phone_number`, `self.customer.name`, etc.
   - ✅ Works transparently with existing state handler code

### 5. **Updated Task Integration**
   - ✅ `tasks.py` now calls `performance.update_performance()` directly
   - ✅ No need to import from `main.py` anymore

## Usage Examples

### Before (Standalone Function)
```python
from main import update_performance

performance = Performance.objects.get(id=1)
update_performance(performance)  # ❌ Function, not method
```

### After (Model Method)
```python
performance = Performance.objects.get(id=1)
performance.update_performance()  # ✅ Clean method call
```

### Accessing Customer from State Handlers
```python
class MyState(BaseStateHandler):
    def on_enter(self):
        # self.customer is automatically the Customer model
        phone = self.customer.phone_number  # ✅ Works!
        name = self.customer.name  # ✅ Works!
        
        # Access UssdUser if needed
        state = self.ussd_user.current_flow_state  # ✅ Also works!
```

## Architecture Benefits

1. **Separation of Concerns**
   - `Customer`: Core user data (phone, name, transactions)
   - `UssdUser`: Session state (current state, context, metadata)
   - `Performance`: Analytics data (scores, averages)

2. **Data Integrity**
   - State data separate from user data
   - Multiple sessions possible per customer (if needed)
   - Clean foreign key relationships

3. **Code Organization**
   - Model methods belong to models
   - Easier to test
   - Better IDE autocomplete support

## Migration Notes

If you have existing code that accesses `session.customer` directly expecting a `Customer`:

**Old code:**
```python
customer = session.customer  # Was Customer
phone = customer.phone_number
```

**New code (still works!):**
```python
customer = session.customer  # Is now UssdUser
phone = customer.customer.phone_number  # Access underlying Customer
```

**Better (in state handlers):**
```python
# BaseStateHandler automatically handles this
customer = self.customer  # Returns Customer via property
phone = customer.phone_number  # ✅ Works!
```

## Files Modified

1. `whatsapp_ussd/models.py`
   - Added `update_performance()` method to `Performance`
   - Created `UssdUser` model
   - Added `USSD_USER` alias

2. `whatsapp_ussd/services/core/session.py`
   - Updated to use `UssdUser` instead of `Customer`
   - Fixed UserEvent creation to use `UssdUser.customer`

3. `whatsapp_ussd/services/states/base.py`
   - Added `customer` property for backward compatibility

4. `whatsapp_ussd/tasks.py`
   - Updated to call `performance.update_performance()`

5. `main.py`
   - Removed `update_performance` function (now model method)

## Database Migration Required

After these changes, you'll need to:

1. Create a migration for the new `UssdUser` model:
   ```bash
   python manage.py makemigrations
   ```

2. Migrate existing data (if any):
   - Create `UssdUser` records for existing `Customer` records
   - Migrate state data from `Customer` to `UssdUser`

## Testing Recommendations

1. Test `update_performance()` method:
   ```python
   performance = Performance.objects.get(id=1)
   performance.update_performance()
   assert performance.total_attempts > 0
   ```

2. Test state handler customer access:
   ```python
   handler = MyStateHandler(session)
   assert handler.customer.phone_number == "+250..."
   ```

3. Test session transitions:
   ```python
   session.transition_to('exam')
   assert session.customer.current_flow_state == 'exam'
   ```

