# hospital/management/commands/fix_blog_images.py
from django.core.management.base import BaseCommand
from hospital.models import BlogPost
from hospital.models import upload_image_to_s3_simple
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix blog post images by uploading them to S3'

    def handle(self, *args, **options):
        self.stdout.write("🔄 Fixing blog post images...")
        
        posts = BlogPost.objects.all()
        for post in posts:
            self.stdout.write(f"\n📝 Processing: {post.title}")
            
            # Check each image field
            if post.featured_image and post.featured_image.name:
                self.stdout.write(f"  📤 Uploading featured image: {post.featured_image.name}")
                success = upload_image_to_s3_simple(post.featured_image, post, 'featured_image')
                self.stdout.write(f"    {'✅ Success' if success else '❌ Failed'}")
            
            if post.image_1 and post.image_1.name:
                self.stdout.write(f"  📤 Uploading image 1: {post.image_1.name}")
                success = upload_image_to_s3_simple(post.image_1, post, 'image_1')
                self.stdout.write(f"    {'✅ Success' if success else '❌ Failed'}")
            
            if post.image_2 and post.image_2.name:
                self.stdout.write(f"  📤 Uploading image 2: {post.image_2.name}")
                success = upload_image_to_s3_simple(post.image_2, post, 'image_2')
                self.stdout.write(f"    {'✅ Success' if success else '❌ Failed'}")
        
        self.stdout.write("\n✅ All blog post images processed!")