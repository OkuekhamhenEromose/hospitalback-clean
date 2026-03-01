# hospital/storage_backends.py
from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
import logging

logger = logging.getLogger(__name__)

class MediaStorage(S3Boto3Storage):
    """
    Custom storage for media files.
    Only used when AWS credentials are available.
    """
    def __init__(self, *args, **kwargs):
        # Check if AWS settings are available and non-empty
        if not all([
            getattr(settings, 'AWS_ACCESS_KEY_ID', None),
            getattr(settings, 'AWS_SECRET_ACCESS_KEY', None),
            getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None),
        ]):
            logger.info("AWS credentials not available - using fallback")
            # Don't try to initialize S3 storage
            super().__init__(*args, **kwargs)
            return
            
        try:
            location = kwargs.get('location', '')
            if not location:
                kwargs['location'] = 'media'
            
            # Only set custom_domain if it exists
            if hasattr(settings, 'AWS_S3_CUSTOM_DOMAIN'):
                self.custom_domain = settings.AWS_S3_CUSTOM_DOMAIN
                
            super().__init__(*args, **kwargs)
            logger.info(f"MediaStorage initialized for bucket: {settings.AWS_STORAGE_BUCKET_NAME}")
            
        except Exception as e:
            logger.error(f"Error initializing MediaStorage: {e}")
            super().__init__(*args, **kwargs)