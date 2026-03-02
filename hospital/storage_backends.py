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

        class _S3MediaStorage(S3Boto3Storage):
            location         = 'media'
            file_overwrite   = False

            # ── Class-level attribute overrides ──────────────────────────────
            #
            # WHY THIS IS NEEDED
            # ──────────────────
            # S3Boto3Storage.__init__ reads Django settings and stores them as
            # instance attributes. In django-storages >= 1.13 the values are
            # also stored in self._config (a private dict). S3Boto3Storage.url()
            # in those versions reads from self._config, NOT from
            # self.custom_domain / self.querystring_auth. So assigning to the
            # instance AFTER __init__ (our previous approach) was silently
            # ignored — url() kept hitting Branch 1 (unsigned custom-domain
            # URL) because self._config['custom_domain'] was still set.
            #
            # Class-level attributes are read by S3Boto3Storage.__init__ and
            # stored in self._config, so they win unconditionally regardless
            # of what AWS_S3_CUSTOM_DOMAIN says in Django settings.
            #
            # Branch 1 fires when self.custom_domain is truthy. Setting it to
            # None as a class attribute ensures __init__ always initialises
            # self._config['custom_domain'] = None.
            custom_domain    = None   # prevents Branch 1 (unsigned f-string URL)

            # ── Definitive URL override ───────────────────────────────────────
            #
            # Even with custom_domain = None, self.querystring_auth in
            # self._config could still be False (if AWS_QUERYSTRING_AUTH=False
            # in settings), landing on Branch 3 (unsigned plain S3 URL).
            #
            # Overriding url() completely eliminates all branching. We call
            # boto3's generate_presigned_url() directly. This approach is:
            #   - Immune to django-storages version differences
            #   - Immune to AWS_QUERYSTRING_AUTH in settings.py
            #   - Immune to _config vs instance-attribute storage differences
            #   - Works on private buckets (no "Block all public access" changes)
            #   - Works on eu-north-1 (SigV4 is what boto3 uses for this region)
            def url(self, name, parameters=None, expire=None, http_method=None):
                """
                Always return a SigV4 pre-signed URL generated directly via boto3.
                Bypasses all S3Boto3Storage.url() branch logic entirely.
                """
                try:
                    name   = self._normalize_name(clean_name(name))
                    expire = expire if expire is not None else 3600

                    signed_url = self.bucket.meta.client.generate_presigned_url(
                        'get_object',
                        Params={'Bucket': self.bucket_name, 'Key': name},
                        ExpiresIn=expire,
                    )

                    # boto3 may return http:// for path-style endpoints
                    if signed_url and signed_url.startswith('http://'):
                        signed_url = 'https://' + signed_url[7:]

                    return signed_url

                except Exception as e:
                    logger.error(
                        'MediaStorage.url() failed to generate presigned URL '
                        'for %r: %s — falling back to unsigned URL', name, e,
                    )
                    # Fallback: at least return something rather than crashing
                    return (
                        f"https://{self.bucket_name}.s3"
                        f".{getattr(settings, 'AWS_S3_REGION_NAME', 'eu-north-1')}"
                        f".amazonaws.com/{name}"
                    )

        storage = _S3MediaStorage()

        # ── Startup verification ──────────────────────────────────────────────
        # Generate a test presigned URL at startup so the Render log immediately
        # shows whether signing is working. Look for this line after each deploy.
        try:
            test_url = storage.url('startup-test-key')
            is_signed = 'X-Amz-Signature' in test_url
            logger.info(
                'MediaStorage STARTUP CHECK — bucket=%s region=%s '
                'presigned=%s url_prefix=%s',
                settings.AWS_STORAGE_BUCKET_NAME,
                getattr(settings, 'AWS_S3_REGION_NAME', '?'),
                is_signed,
                test_url[:60],
            )
            if not is_signed:
                logger.error(
                    'MediaStorage STARTUP CHECK FAILED — URL is not presigned! '
                    'Images will return 403. Full URL: %s', test_url,
                )
        except Exception as e:
            logger.error('MediaStorage startup check raised: %s', e)

        return storage

    except Exception as exc:
        logger.error('MediaStorage: S3 init failed (%s) — falling back to FileSystemStorage', exc)
        return FileSystemStorage()


class MediaStorage(FileSystemStorage):
    """
    Proxy storage class referenced by DEFAULT_FILE_STORAGE in settings.py.
    __new__ returns the actual backend (S3 or local filesystem).
    """
    def __new__(cls, *args, **kwargs):
        return _build_storage()
