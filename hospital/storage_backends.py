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

        storage = _S3MediaStorage()

        # ══════════════════════════════════════════════════════════════════════
        # WHY IMAGE URLs WERE RETURNING 403
        # ══════════════════════════════════════════════════════════════════════
        #
        # S3Boto3Storage.url() has three branches, checked in order:
        #
        #   Branch 1  if self.custom_domain:
        #                 return f"https://{custom_domain}/{name}"
        #                 # ← plain unsigned URL — always fired because
        #                 #   AWS_S3_CUSTOM_DOMAIN is set in settings.py
        #
        #   Branch 2  elif self.querystring_auth:
        #                 return generate_presigned_url(...)
        #                 # ← SigV4 pre-signed URL, works with private buckets
        #
        #   Branch 3  else:
        #                 return unsigned_s3_url_without_query_params
        #                 # ← also returns 403 against a private bucket
        #
        # AWS S3 buckets created after April 2023 have "Block all public access"
        # enabled by default (including this eu-north-1 bucket). A plain unsigned
        # URL against a private bucket returns 403 in the browser.
        #
        # Fix A — disable custom_domain:
        #   Setting custom_domain = None prevents Branch 1 from firing.
        #   Control falls through to Branch 2 or 3.
        storage.custom_domain = None

        # Fix B — force presigned URL generation:
        #   The original settings.py had AWS_QUERYSTRING_AUTH = False, which
        #   made S3Boto3Storage.__init__ set self.querystring_auth = False.
        #   With custom_domain = None and querystring_auth = False, url() takes
        #   Branch 3 and still returns an unsigned URL → still 403.
        #
        #   Setting querystring_auth = True HERE (on the instance, after init)
        #   forces Branch 2 regardless of what AWS_QUERYSTRING_AUTH says in
        #   settings.py. This file is now the single source of truth for URL
        #   signing — independent of whether settings.py has been updated.
        storage.querystring_auth = True

        # Set a reasonable expiry. 3600 s = 1 hour.
        storage.querystring_expire = 3600

        logger.info(
            'MediaStorage: S3 ready — bucket=%s, region=%s. '
            'custom_domain=None, querystring_auth=True → '
            'presigned SigV4 URLs (1 h expiry).',
            settings.AWS_STORAGE_BUCKET_NAME,
            getattr(settings, 'AWS_S3_REGION_NAME', 'unknown'),
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