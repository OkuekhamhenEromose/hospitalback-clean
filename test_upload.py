# test_upload.py
import os
import sys
import django
from pathlib import Path

# Setup Django environment
sys.path.append(str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

# Now import Django models
from hospital.models import BlogPost, upload_image_to_s3_simple
from django.core.files.uploadedfile import SimpleUploadedFile
from users.models import Profile
from django.contrib.auth.models import User
from PIL import Image
import io

def test_s3_upload():
    print("=" * 50)
    print("Starting S3 Upload Test")
    print("=" * 50)
    
    # Step 1: Check/Create author
    print("\n1. Checking for author...")
    author = Profile.objects.filter(role='ADMIN').first()
    
    if not author:
        print("   No admin found, creating test author...")
        user = User.objects.create_user(
            username='testadmin',
            password='testpass123',
            email='test@example.com'
        )
        author = Profile.objects.create(
            user=user,
            fullname='Test Admin',
            role='ADMIN'
        )
        print(f"   ✅ Created author with ID: {author.id}")
    else:
        print(f"   ✅ Found author: {author.fullname} (ID: {author.id})")
    
    # Step 2: Create blog post
    print("\n2. Creating test blog post...")
    post = BlogPost.objects.create(
        title="S3 Upload Test",
        description="Testing S3 image upload",
        content="<p>This is a test post for S3 upload</p>",
        author=author
    )
    print(f"   ✅ Blog post created with ID: {post.id}")
    
    # Step 3: Create test image
    print("\n3. Creating test image...")
    img = Image.new('RGB', (200, 200), color='blue')
    img_io = io.BytesIO()
    img.save(img_io, format='JPEG')
    img_io.seek(0)
    
    test_file = SimpleUploadedFile(
        "s3_test_image.jpg",
        img_io.read(),
        content_type="image/jpeg"
    )
    print(f"   ✅ Test image created: {test_file.size} bytes")
    
    # Step 4: Attach to post
    print("\n4. Attaching image to blog post...")
    post.featured_image = test_file
    post.save()
    print("   ✅ Image attached to post")
    
    # Step 5: Upload to S3
    print("\n5. Uploading to S3...")
    print("   (This may take a few seconds)")
    result = upload_image_to_s3_simple(post.featured_image, post, 'featured_image')
    
    if result:
        print("   ✅ Upload successful!")
        print(f"\n📸 Image URL: {post.featured_image.url}")
        print("\nTest the URL in your browser to verify it works!")
    else:
        print("   ❌ Upload failed")
    
    print("\n" + "=" * 50)
    print("Test Complete")
    print("=" * 50)
    
    return post

if __name__ == "__main__":
    test_s3_upload()