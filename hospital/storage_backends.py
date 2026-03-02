# hospital/storage_backends.py
from django.conf import settings
from django.core.files.storage import FileSystemStorage
import logging

logger = logging.getLogger(__name__)


# FIX: The original class subclassed S3Boto3Storage directly. S3Boto3Storage
# calls boto3 in __init__ and immediately raises NoCredentialsError when AWS
# env vars are empty. The __init__ credential check happened AFTER boto3 was
# already instantiated, so the guard never actually prevented the crash.
#
# Solution: __new__ factory pattern. We return an instance of the correct
# storage class before __init__ of S3Boto3Storage ever runs. Django caches
# the DEFAULT_FILE_STORAGE class, so this executes once on startup.

def _build_storage():
    """
    Return S3Boto3Storage if credentials are present, FileSystemStorage otherwise.
    Called once when MediaStorage is first instantiated.
    """
    if not getattr(settings, 'AWS_CREDENTIALS_PROVIDED', False):
        logger.warning(
            'MediaStorage: AWS credentials not configured — '
            'falling back to FileSystemStorage'
        )
        return FileSystemStorage()

    try:
        from storages.backends.s3boto3 import S3Boto3Storage

        class _S3MediaStorage(S3Boto3Storage):
            location       = 'media'
            file_overwrite = False
            # AWS_S3_CUSTOM_DOMAIN from settings.py is picked up automatically
            # by S3Boto3Storage — no need to set custom_domain here.

        storage = _S3MediaStorage()

        # ── FIX: force pre-signed URL generation ──────────────────────────────
        # S3Boto3Storage.__init__ reads AWS_S3_CUSTOM_DOMAIN from Django settings
        # and stores it as self.custom_domain. S3Boto3Storage.url() then checks:
        #
        #   if self.custom_domain:
        #       return f"https://{custom_domain}/{key}"  # ← unsigned, no query params
        #
        # This short-circuits BEFORE the generate_presigned_url() call, so
        # AWS_QUERYSTRING_AUTH = True has zero effect when custom_domain is set.
        # The returned unsigned URL hits a private bucket → 403 in the browser.
        #
        # Fix: null out custom_domain after init so url() falls through to
        # generate_presigned_url(). AWS_QUERYSTRING_AUTH = True and
        # AWS_S3_SIGNATURE_VERSION = 's3v4' (both set in settings.py) then
        # produce a valid SigV4 pre-signed URL that works with private buckets
        # regardless of the bucket's public-access policy.
        storage.custom_domain = None

        logger.info(
            'MediaStorage: S3 initialised for bucket %s (presigned URLs enabled)',
            settings.AWS_STORAGE_BUCKET_NAME,
        )
        return storage

    except Exception as exc:
        logger.error(
            'MediaStorage: S3 initialisation failed (%s) — '
            'falling back to FileSystemStorage', exc,
        )
        return FileSystemStorage()


class MediaStorage(FileSystemStorage):
    """
    Proxy storage class referenced by DEFAULT_FILE_STORAGE.

    __new__ returns the real backend (S3 or filesystem) directly so Django
    works with a fully-configured storage object. FileSystemStorage is used
    as the base class purely to satisfy isinstance checks that some third-party
    packages perform; it is never actually initialised via super().__init__().
    """

    def __new__(cls, *args, **kwargs):
        return _build_storage()