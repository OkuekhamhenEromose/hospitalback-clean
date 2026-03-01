# hospital/base_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from django.core.cache import cache
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
import hashlib
import json
import logging

logger = logging.getLogger(__name__)

class CacheMixin:
    """Mixin to add caching capabilities to views"""
    
    cache_timeout = 300  # 5 minutes default
    cache_key_prefix = None
    
    def get_cache_key(self, request, prefix=None):
        """Generate unique cache key based on request"""
        prefix = prefix or self.cache_key_prefix or self.__class__.__name__
        
        # Create a dict of relevant request parameters
        params = {
            'path': request.path,
            'query': dict(request.GET.items()),
            'user': 'auth' if request.user.is_authenticated else 'anon',
        }
        
        # Create hash
        key = hashlib.md5(
            json.dumps(params, sort_keys=True).encode()
        ).hexdigest()
        
        return f"{prefix}:{key}"
    
    def get_cached_data(self, key):
        """Get data from cache"""
        return cache.get(key)
    
    def set_cached_data(self, key, data):
        """Set data in cache"""
        cache.set(key, data, self.cache_timeout)
    
    def invalidate_cache(self, pattern=None):
        """Invalidate cache by pattern"""
        if pattern:
            cache.delete_pattern(pattern)
        else:
            cache.delete_pattern(f"{self.cache_key_prefix}:*")


class OptimizedAPIView(APIView, CacheMixin):
    """Base class for optimized API views with caching"""
    
    @method_decorator(cache_page(300))
    @method_decorator(vary_on_headers('Authorization'))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)