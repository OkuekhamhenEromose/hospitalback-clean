# test_fix.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from users.models import Profile
from hospital.utils import upload_to_s3
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
import io
import boto3
from django.conf import settings

def test_complete_cycle():
    print("=" * 60)
    print("Testing Complete Upload Cycle")
    print("=" * 60)
    
    # Create test image
    img = Image.new('RGB', (100, 100), color='purple')
    img_io = io.BytesIO()
    img.save(img_io, format='JPEG')
    img_io.seek(0)
    
    test_file = SimpleUploadedFile(
        "test_cycle.jpg",
        img_io.read(),
        content_type="image/jpeg"
    )
    
    # Get a profile
    profile = Profile.objects.first()
    if not profile:
        from django.contrib.auth.models import User
        user = User.objects.create_user(username='testuser', password='testpass123')
        profile = Profile.objects.create(user=user, fullname='Test User', role='PATIENT')
    
    print(f"\n1. Testing with profile ID: {profile.id}")
    
    # Save locally
    filename = "test_cycle_profile.jpg"
    profile.profile_pix.save(filename, test_file, save=True)
    print(f"✅ Local save complete: {filename}")
    
    # Upload to S3
    s3_key = f"media/profile/{filename}"
    success, url = upload_to_s3(profile.profile_pix, s3_key, metadata={'test': 'true'})
    
    if success:
        print(f"✅ S3 upload successful")
        print(f"   URL: {url}")
    else:
        print(f"❌ S3 upload failed: {url}")
        return
    
    # Verify in S3
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )
    
    try:
        response = s3.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=s3_key)
        print(f"✅ Verified in S3: {s3_key}")
        print(f"   Size: {response['ContentLength']} bytes")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        return
    
    # Test public access
    import requests
    response = requests.get(url)
    print(f"   Public access: {response.status_code}")
    if response.status_code == 200:
        print("✅ Image is publicly accessible!")
    else:
        print(f"❌ Public access failed: {response.status_code}")
    
    return url

if __name__ == "__main__":
    test_complete_cycle()