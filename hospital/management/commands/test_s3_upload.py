# hospital/management/commands/test_s3_upload.py
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
import tempfile
import os

class Command(BaseCommand):
    help = 'Test S3 file upload with BlogPost model'
    
    def handle(self, *args, **options):
        print("📤 Testing S3 File Upload with BlogPost...")
        
        try:
            # Try to import models
            from hospital.models import BlogPost
            from users.models import User
            
            # Check if PIL is available
            try:
                from PIL import Image, ImageDraw
                pil_available = True
            except ImportError:
                pil_available = False
                print("⚠️  PIL/Pillow not installed, using text file instead")
            
            # Create a test file
            if pil_available:
                print("Creating test image...")
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                    # Create a simple image
                    img = Image.new('RGB', (100, 100), color='blue')  # Changed to blue
                    draw = ImageDraw.Draw(img)
                    draw.text((10, 40), "S3-TEST", fill='white')
                    img.save(tmp.name, format='JPEG')
                    file_to_upload = tmp.name
                    file_extension = '.jpg'
                    print(f"Created test image: {file_to_upload}")
            else:
                print("Creating test text file...")
                with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as tmp:
                    tmp.write("This is a test file for S3 upload")
                    file_to_upload = tmp.name
                    file_extension = '.txt'
                    print(f"Created test file: {file_to_upload}")
            
            # Get or create test user
            user, created = User.objects.get_or_create(
                username='test_s3_user',
                defaults={
                    'email': 'test_s3@example.com'
                }
            )
            
            # Try to get Profile model if it exists
            try:
                from users.models import Profile
                profile, profile_created = Profile.objects.get_or_create(
                    user=user,
                    defaults={
                        'fullname': 'S3 Test User', 
                        'role': 'ADMIN'
                    }
                )
                author = profile
            except:
                # If Profile model doesn't exist, use user as author
                print("⚠️  Profile model not found, using user as author")
                author = user
            
            # CHECK IF POST ALREADY EXISTS
            existing_post = BlogPost.objects.filter(title="Test S3 Upload").first()
            
            if existing_post:
                print(f"✅ Using existing blog post: {existing_post.title}")
                post = existing_post
            else:
                # Create NEW test blog post with unique slug
                import uuid
                unique_id = str(uuid.uuid4())[:8]
                
                post_data = {
                    'title': f"Test S3 Upload {unique_id}",
                    'description': "Testing S3 file upload functionality",
                    'content': "<h1>Test Content</h1><p>Testing S3 upload</p>",
                    'author': author,
                    'published': True
                }
                
                post = BlogPost.objects.create(**post_data)
                print(f"✅ Created new test blog post: {post.title}")
            
            # Check if featured_image field exists
            if hasattr(BlogPost, 'featured_image'):
                print(f"✅ BlogPost has featured_image field")
                
                # Upload the test file
                with open(file_to_upload, 'rb') as f:
                    filename = f'test_s3_upload_{os.path.basename(file_to_upload)}'
                    post.featured_image.save(filename, ContentFile(f.read()))
                
                print(f"✅ Uploaded file to S3")
                print(f"✅ File URL: {post.featured_image.url}")
                print(f"✅ File path: {post.featured_image.name}")
                
                # Verify the file exists in storage
                if post.featured_image.storage.exists(post.featured_image.name):
                    print(f"✅ File verified in S3 storage")
                else:
                    print(f"⚠️  File not found in S3 storage")
                    
                # Test that we can access it
                import requests
                try:
                    response = requests.head(post.featured_image.url, timeout=5)
                    print(f"✅ Image URL test: HTTP {response.status_code}")
                    
                    if response.status_code == 200:
                        print("🎉 SUCCESS! Image is publicly accessible via URL!")
                    else:
                        print(f"⚠️  URL returns {response.status_code}")
                        
                except Exception as e:
                    print(f"⚠️  Could not verify URL access: {e}")
            else:
                print("ℹ️  BlogPost model doesn't have featured_image field")
            
            # Clean up temporary file
            if os.path.exists(file_to_upload):
                os.unlink(file_to_upload)
                print(f"✅ Cleaned up temporary file")
            
            print("\n🎉 Test completed successfully!")
            
        except Exception as e:
            print(f"❌ Error during test: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Clean up on error
            if 'file_to_upload' in locals() and os.path.exists(file_to_upload):
                os.unlink(file_to_upload)

                