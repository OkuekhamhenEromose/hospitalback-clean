from django.conf import settings
from django.core.files.storage import FileSystemStorage
from storages.backends.s3boto3 import S3Boto3Storage
import logging

logger = logging.getLogger(__name__)


class MediaStorage(S3Boto3Storage):
    """
    Custom storage for media files on S3.
    Falls back to FileSystemStorage if AWS credentials are missing.
    """
    location = 'media'
    file_overwrite = False
    default_acl = 'public-read'  # Make files publicly readable
    querystring_auth = False      # Disable query string auth for public reads
    
    def __init__(self, *args, **kwargs):
        if not getattr(settings, 'AWS_CREDENTIALS_PROVIDED', False):
            logger.warning('AWS credentials not configured - using FileSystemStorage')
            self.storage = FileSystemStorage()
        else:
            logger.info(f'Initializing S3 storage for bucket: {settings.AWS_STORAGE_BUCKET_NAME}')
            super().__init__(*args, **kwargs)
    
    def url(self, name):
        """Return URL for file - works with both S3 and local storage"""
        if hasattr(self, 'storage'):
            return self.storage.url(name)
        return super().url(name)