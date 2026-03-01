# hospital/management/commands/warm_blog_cache.py
#
# Addresses: "Redis cache not warmed for blog on deploy"
#
# Run this as part of your Render deploy script so that the first real user
# request after a deploy or Redis flush is served from cache instead of hitting
# the database cold.  Add to your Render "Build Command" or a post-deploy hook:
#
#   python manage.py migrate && python manage.py warm_blog_cache
#
# This command is safe to run repeatedly — it just overwrites existing keys.
from django.core.management.base import BaseCommand
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Pre-populate Redis with serialised blog data to eliminate cold-cache on deploy'

    def add_arguments(self, parser):
        parser.add_argument(
            '--ttl',
            type=int,
            default=300,
            help='Cache TTL in seconds (default: 300 = 5 minutes)',
        )

    def handle(self, *args, **options):
        ttl = options['ttl']

        # Guard: if Redis is not configured, skip warmup gracefully
        try:
            cache.set('_warm_probe', '1', 5)
            cache.delete('_warm_probe')
        except Exception as exc:
            self.stdout.write(
                self.style.WARNING(f'Cache backend unavailable — skipping warmup: {exc}')
            )
            return

        warmed = 0

        # ── Blog list (first page, no filters) ─────────────────────────────
        # Key format must match CacheMixin.get_cache_key() in base_views.py:
        #   f"{prefix}:{request.path}:{request.GET.urlencode()}"
        # For the root blog list with no query params this resolves to:
        #   "blog_list:/api/hospital/blog/:"
        try:
            from hospital.models import BlogPost
            from hospital.serializers import BlogPostListSerializer

            posts = (
                BlogPost.objects
                .filter(published=True)
                .select_related('author')
                .only(
                    'id', 'title', 'slug', 'description',
                    'featured_image', 'image_1', 'image_2',
                    'published', 'published_date', 'created_at',
                    'author__fullname', 'author__role',
                )
                .order_by('-published_date', '-created_at')[:20]
            )
            data = BlogPostListSerializer(posts, many=True).data
            cache.set('blog_list:/api/hospital/blog/:', data, ttl)
            self.stdout.write(f'  ✓ blog_list  ({len(data)} posts)')
            warmed += 1
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  ✗ blog_list failed: {exc}'))

        # ── Latest posts (default limit=6) ──────────────────────────────────
        # Key: "blog_latest:/api/hospital/blog/latest/:"
        try:
            latest = (
                BlogPost.objects
                .filter(published=True)
                .select_related('author')
                .only(
                    'id', 'title', 'slug', 'description',
                    'featured_image', 'image_1', 'image_2',
                    'published_date', 'created_at',
                    'author__fullname', 'author__role',
                )
                .order_by('-published_date', '-created_at')[:6]
            )
            latest_data = BlogPostListSerializer(latest, many=True).data
            cache.set('blog_latest:/api/hospital/blog/latest/:', latest_data, ttl)
            self.stdout.write(f'  ✓ blog_latest ({len(latest_data)} posts)')
            warmed += 1
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f'  ✗ blog_latest failed: {exc}'))

        if warmed:
            self.stdout.write(
                self.style.SUCCESS(f'Cache warmed successfully ({warmed} key groups, TTL={ttl}s)')
            )
        else:
            self.stdout.write(self.style.WARNING('No cache keys were warmed'))