# hospital/tasks.py
from celery import shared_task
from django.core.cache import cache
import logging
from .models import BlogPost, upload_image_to_s3_simple  # Add this import
from .serializers import BlogPostListSerializer  # Add this for warm_cache

logger = logging.getLogger(__name__)

@shared_task
def process_blog_images(blog_post_id):
    """Async task to process and upload blog images to S3"""
    try:
        blog_post = BlogPost.objects.get(id=blog_post_id)
        logger.info(f"📸 Processing images for blog post {blog_post_id}")
        
        # Process each image field
        image_fields = [
            ('featured_image', blog_post.featured_image),
            ('image_1', blog_post.image_1),
            ('image_2', blog_post.image_2),
        ]
        
        for field_name, image_field in image_fields:
            if image_field and image_field.name:
                logger.info(f"  Uploading {field_name}: {image_field.name}")
                upload_image_to_s3_simple(image_field, blog_post, field_name)
        
        # Clear cache after processing
        cache.delete_pattern('blog_*')
        logger.info(f"✅ Images processed for blog post {blog_post_id}")
        
    except BlogPost.DoesNotExist:
        logger.error(f"Blog post {blog_post_id} not found")
    except Exception as e:
        logger.error(f"Error processing images: {str(e)}")