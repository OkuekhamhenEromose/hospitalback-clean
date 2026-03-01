# hospital/management/commands/auto_fix_blog_images.py
from django.core.management.base import BaseCommand
from django.conf import settings
from hospital.models import BlogPost
import boto3
from PIL import Image
import io
import hashlib
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Automatically create missing blog images in S3'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Check what would be created without actually creating'
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.SUCCESS('🔍 Scanning for missing blog images...'))
        
        # Setup S3
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        # Get all blog posts
        blog_posts = BlogPost.objects.all()
        self.stdout.write(f"📝 Found {blog_posts.count()} blog posts")
        
        created_count = 0
        
        for post in blog_posts:
            self.stdout.write(f"\n📄 Processing: '{post.title}'")
            
            # Check each image field
            for field_name in ['featured_image', 'image_1', 'image_2']:
                image_field = getattr(post, field_name)
                if not image_field:
                    continue
                
                filename = image_field.name
                s3_key = f"media/{filename}"
                
                # Check if exists in S3
                try:
                    s3.head_object(Bucket=bucket_name, Key=s3_key)
                    self.stdout.write(f"   ✅ {field_name}: Already exists in S3")
                    continue
                except:
                    self.stdout.write(f"   ⚠️  {field_name}: Missing from S3 ({filename})")
                    
                    if dry_run:
                        self.stdout.write(f"   🚫 Dry run: Would create {filename}")
                        continue
                    
                    # Create placeholder
                    try:
                        # Determine size
                        if field_name == 'featured_image':
                            width, height = 800, 400
                        else:
                            width, height = 400, 300
                        
                        # Generate color from title + field
                        color_source = f"{post.id}_{field_name}_{post.title}"
                        color_hash = hashlib.md5(color_source.encode()).hexdigest()[:6]
                        
                        # Create image
                        img = Image.new('RGB', (width, height), color=f'#{color_hash}')
                        buffer = io.BytesIO()
                        
                        # Determine format
                        if filename.lower().endswith('.webp'):
                            img.save(buffer, format='WEBP', quality=85)
                            content_type = 'image/webp'
                        elif filename.lower().endswith('.png'):
                            img.save(buffer, format='PNG')
                            content_type = 'image/png'
                        else:
                            img.save(buffer, format='JPEG', quality=85)
                            content_type = 'image/jpeg'
                        
                        buffer.seek(0)
                        image_data = buffer.getvalue()
                        
                        # Upload to S3
                        s3.put_object(
                            Bucket=bucket_name,
                            Key=s3_key,
                            Body=image_data,
                            ContentType=content_type,
                            ACL='public-read',
                            Metadata={
                                'blog_title': post.title[:100],
                                'field': field_name,
                                'post_id': str(post.id),
                                'placeholder': 'true',
                                'auto_created': 'yes'
                            }
                        )
                        
                        created_count += 1
                        self.stdout.write(f"   ✅ Created placeholder ({len(image_data)} bytes)")
                        
                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"   ❌ Failed to create: {e}"))
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS('📊 FIX COMPLETED'))
        self.stdout.write(self.style.SUCCESS('='*50))
        
        if dry_run:
            self.stdout.write("🚫 DRY RUN - No files were created")
            self.stdout.write(f"Would create: {created_count} images")
        else:
            self.stdout.write(f"✅ Created: {created_count} missing blog images")
            
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write("🎉 All blog images should now display!")
        self.stdout.write("🔄 Refresh your frontend to see the changes.")