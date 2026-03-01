from django.core.management.base import BaseCommand
from hospital.models import BlogPost, upload_image_to_s3_simple
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix all blog post images by uploading them to S3'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-upload even if already exists in S3'
        )
    
    def handle(self, *args, **options):
        force = options.get('force', False)
        
        self.stdout.write("[INFO] Fixing blog post images in S3...")
        self.stdout.write(f"[INFO] Force mode: {'ON' if force else 'OFF'}")
        
        posts = BlogPost.objects.all()
        total_posts = posts.count()
        self.stdout.write(f"[INFO] Found {total_posts} blog posts to process")
        
        total_uploaded = 0
        total_skipped = 0
        total_failed = 0
        
        for index, post in enumerate(posts, 1):
            self.stdout.write(f"\n[{index}/{total_posts}] Processing: '{post.title}' (ID: {post.id})")
            
            # Process each image field
            if post.featured_image and post.featured_image.name:
                result = self.process_image(post.featured_image, post, 'featured_image', force)
                if result == 'uploaded':
                    total_uploaded += 1
                elif result == 'skipped':
                    total_skipped += 1
                else:
                    total_failed += 1
            
            if post.image_1 and post.image_1.name:
                result = self.process_image(post.image_1, post, 'image_1', force)
                if result == 'uploaded':
                    total_uploaded += 1
                elif result == 'skipped':
                    total_skipped += 1
                else:
                    total_failed += 1
            
            if post.image_2 and post.image_2.name:
                result = self.process_image(post.image_2, post, 'image_2', force)
                if result == 'uploaded':
                    total_uploaded += 1
                elif result == 'skipped':
                    total_skipped += 1
                else:
                    total_failed += 1
        
        self.stdout.write("\n" + "="*50)
        self.stdout.write(self.style.SUCCESS(f"[SUCCESS] All blog post images processed!"))
        self.stdout.write(f"[INFO] Total uploaded: {total_uploaded}")
        self.stdout.write(f"[INFO] Total skipped (already exist): {total_skipped}")
        self.stdout.write(f"[INFO] Total failed: {total_failed}")
    
    def process_image(self, image_field, post, field_name, force=False):
        """Helper method to process individual image"""
        self.stdout.write(f"  [UPLOAD] {field_name}: {image_field.name}")
        
        # Check if file exists locally
        if not image_field.storage.exists(image_field.name):
            self.stdout.write(self.style.WARNING(f"    [SKIP] Local file not found"))
            return 'failed'
        
        # Upload to S3
        success = upload_image_to_s3_simple(image_field, post, field_name)
        
        if success:
            self.stdout.write(self.style.SUCCESS(f"    [SUCCESS] Uploaded"))
            return 'uploaded'
        else:
            self.stdout.write(self.style.ERROR(f"    [FAILED] Could not upload"))
            return 'failed'