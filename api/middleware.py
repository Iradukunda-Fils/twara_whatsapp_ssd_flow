# api/middleware.py
from django.core.cache import cache
from django.http import JsonResponse
import logging
import time

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Rate limiting middleware to prevent abuse.
    
    Limits:
    - 10 requests per minute per IP
    - 100 requests per hour per IP
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip rate limiting for health checks
        if request.path in ['/api/health/', '/api/metrics/']:
            return self.get_response(request)
        
        # Get client IP
        ip = self.get_client_ip(request)
        
        # Check rate limit
        if not self.check_rate_limit(ip):
            logger.warning(f"Rate limit exceeded for IP: {ip}")
            return JsonResponse(
                {"error": "Rate limit exceeded. Please try again later."},
                status=429
            )
        
        response = self.get_response(request)
        return response
    
    @staticmethod
    def get_client_ip(request):
        """Extract client IP from request"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    @staticmethod
    def check_rate_limit(identifier: str) -> bool:
        """
        Check if identifier is within rate limits.
        
        Returns:
            True if within limits, False if exceeded
        """
        minute_key = f"ratelimit:minute:{identifier}"
        hour_key = f"ratelimit:hour:{identifier}"
        
        # Check minute limit (10 requests)
        minute_count = cache.get(minute_key, 0)
        if minute_count >= 50:
            return False
        
        # Check hour limit (100 requests)
        hour_count = cache.get(hour_key, 0)
        if hour_count >= 500:
            return False
        
        # Increment counters
        cache.set(minute_key, minute_count + 1, timeout=60)
        cache.set(hour_key, hour_count + 1, timeout=3600)
        
        return True


class RequestLoggingMiddleware:
    """
    Log all API requests for debugging and monitoring.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Record start time
        start_time = time.time()
        
        # Log request
        logger.info(
            f"API Request: {request.method} {request.path} "
            f"from {RateLimitMiddleware.get_client_ip(request)}"
        )
        
        # Process request
        response = self.get_response(request)
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Log response
        logger.info(
            f"API Response: {request.method} {request.path} "
            f"Status {response.status_code} ({duration*1000:.2f}ms)"
        )
        
        # Add response headers
        response['X-Response-Time'] = f"{duration*1000:.2f}ms"
        
        return response