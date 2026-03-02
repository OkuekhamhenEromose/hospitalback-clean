from django.conf import settings
from django.core.files.storage import FileSystemStorage
import logging

logger = logging.getLogger(__name__)


def _build_storage():
    if not getattr(settings, 'AWS_CREDENTIALS_PROVIDED', False):
        logger.warning('MediaStorage: AWS credentials not configured — falling back to FileSystemStorage')
        return FileSystemStorage()

    try:
        from storages.backends.s3boto3 import S3Boto3Storage
        from storages.utils import clean_name
        import boto3
        from botocore.config import Config

        class _S3MediaStorage(S3Boto3Storage):
            location       = 'media'
            file_overwrite = False
            custom_domain  = None  # prevents unsigned custom-domain URL branch

            def url(self, name, parameters=None, expire=None, http_method=None):
                """
                Generate a SigV4 pre-signed URL using an explicit boto3 client.

                WHY AN EXPLICIT CLIENT:
                ─────────────────────────────────────────────────────────────────
                self.bucket.meta.client inherits from S3Boto3Storage's internal
                boto3 session. That session is NOT guaranteed to have:
                  1. Explicit credentials (it may fall back to env/instance-profile
                     discovery at an unexpected priority)
                  2. Signature Version 4 configured (required for eu-north-1)

                Creating boto3.client() explicitly with credentials from Django
                settings and config=Config(signature_version='s3v4') eliminates
                all ambiguity and is immune to S3Boto3Storage version differences.

                EXPIRE PRIORITY:
                  1. expire argument (caller override)
                  2. AWS_QUERYSTRING_EXPIRE from Django settings
                  3. Hard default of 86400 s (24 h)

                Using AWS_QUERYSTRING_EXPIRE here keeps settings.py as the single
                source of truth rather than duplicating the value in two places.
                """
                try:
                    name   = self._normalize_name(clean_name(name))
                    expire = (
                        expire
                        if expire is not None
                        else getattr(settings, 'AWS_QUERYSTRING_EXPIRE', 86400)
                    )

                    client = boto3.client(
                        's3',
                        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                        region_name=getattr(settings, 'AWS_S3_REGION_NAME', 'eu-north-1'),
                        # eu-north-1 only accepts Signature Version 4
                        config=Config(signature_version='s3v4'),
                    )

                    signed_url = client.generate_presigned_url(
                        'get_object',
                        Params={
                            'Bucket': settings.AWS_STORAGE_BUCKET_NAME,
                            'Key': name,
                        },
                        ExpiresIn=expire,
                    )

                    # boto3 occasionally returns http:// for path-style endpoints
                    if signed_url and signed_url.startswith('http://'):
                        signed_url = 'https://' + signed_url[7:]

                    return signed_url

                except Exception as e:
                    logger.error(
                        'MediaStorage.url() FAILED to generate presigned URL '
                        'for %r: %s — falling back to unsigned URL (will 403 on private bucket)',
                        name, e, exc_info=True,
                    )
                    # Last-resort fallback — callers see something rather than an exception.
                    # NOTE: this URL will return 403 on private buckets. If this error
                    # appears in logs the credentials / region config must be investigated.
                    region = getattr(settings, 'AWS_S3_REGION_NAME', 'eu-north-1')
                    return (
                        f"https://{settings.AWS_STORAGE_BUCKET_NAME}"
                        f".s3.{region}.amazonaws.com/{name}"
                    )

        storage = _S3MediaStorage()

        # ── Startup verification ──────────────────────────────────────────────
        # Generates a test presigned URL immediately so the first Render log
        # line after each deploy tells you whether signing is working.
        # Look for "STARTUP CHECK" after every deploy — if presigned=False
        # images WILL return 403 and nothing in the request path will fix it.
        try:
            test_url  = storage.url('startup-test-key')
            is_signed = 'X-Amz-Signature' in test_url
            logger.info(
                'MediaStorage STARTUP CHECK — bucket=%s region=%s '
                'presigned=%s url_prefix=%.80s',
                settings.AWS_STORAGE_BUCKET_NAME,
                getattr(settings, 'AWS_S3_REGION_NAME', '?'),
                is_signed,
                test_url,
            )
            if not is_signed:
                logger.error(
                    'MediaStorage STARTUP CHECK FAILED — URL is NOT presigned! '
                    'All image requests will return 403. Full URL: %s', test_url,
                )
        except Exception as e:
            logger.error('MediaStorage startup check raised: %s', e, exc_info=True)

        return storage

    except Exception as exc:
        logger.error(
            'MediaStorage: S3 init failed (%s) — falling back to FileSystemStorage',
            exc, exc_info=True,
        )
        return FileSystemStorage()


class MediaStorage(FileSystemStorage):
    """
    Proxy storage class referenced by DEFAULT_FILE_STORAGE in settings.py.
    __new__ returns the actual backend (S3 or local filesystem).
    """
    def __new__(cls, *args, **kwargs):
        return _build_storage()
