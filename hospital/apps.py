# hospital/apps.py
from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class HospitalConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'hospital'

    def ready(self):
        """
        Force MediaStorage to initialize at gunicorn boot so the STARTUP CHECK
        log appears immediately — not on the first user request.

        Also clears all blog/profile cache keys so stale None image URLs
        from before a storage fix are never served to users after a deploy.
        """
        self._init_storage()
        self._bust_image_cache()

    @staticmethod
    def _init_storage():
        """Trigger _build_storage() so the presigned-URL startup check runs."""
        try:
            from django.core.files.storage import default_storage
            # Accessing _wrapped forces the lazy proxy to call __new__
            _ = default_storage._wrapped
        except Exception as e:
            logger.error('HospitalConfig.ready: storage init failed: %s', e)

    @staticmethod
    def _bust_image_cache():
        """
        Clear all cache keys that contain image URLs after a deploy.
        Stale keys (with None or unsigned URLs) would be served for up to
        300 s otherwise, making it appear the storage fix didn't work.
        """
        try:
            from django.core.cache import cache
            for prefix in ('blog_list:', 'blog_latest:', 'blog_detail:',
                           'appointments:', 'appointment_detail:'):
                try:
                    cache.delete_pattern(f'{prefix}*')
                except AttributeError:
                    pass  # LocMemCache in local dev — no-op is fine
            logger.info('HospitalConfig.ready: image cache busted on startup')
        except Exception as e:
            logger.warning('HospitalConfig.ready: cache bust failed (non-fatal): %s', e)