# hospital/middleware.py
import time
import logging
from django.db import connection
from django.conf import settings

logger = logging.getLogger(__name__)

class QueryCountDebugMiddleware:
    """Middleware to log database query counts and times"""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Store start time on request for duration calculation
        request.start_time = time.time()
        
        response = self.get_response(request)
        
        # Log query count after request
        if settings.DEBUG:
            duration = time.time() - request.start_time
            queries = len(connection.queries)
            
            if queries > 50:  # Alert on too many queries
                logger.warning(
                    f"High query count: {queries} queries in {duration:.2f}s "
                    f"for {request.path}"
                )
            
            # Log slow queries
            slow_queries = [
                q for q in connection.queries 
                if float(q.get('time', 0)) > 0.1  # Queries taking >100ms
            ]
            if slow_queries:
                logger.warning(f"Slow queries detected: {len(slow_queries)} for {request.path}")
                
        return response