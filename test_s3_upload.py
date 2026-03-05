# test_s3_upload.py
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'api.settings')
django.setup()

from users.models import Profile
from django.core.files.uploadedfile import SimpleUploadedFile
from hospital.utils import upload_to_s3
from PIL import Image
import io
import boto3
from django.conf import settings

def test_upload():
    print("=" * 50)
    print("S3 Upload Test")
    print("=" * 50)
    
    # Create test image
    img = Image.new('RGB', (100, 100), color='blue')
    img_io = io.BytesIO()
    img.save(img_io, format='JPEG')
    img_io.seek(0)
    
    test_file = SimpleUploadedFile(
        "test_upload.jpg",
        img_io.read(),
        content_type="image/jpeg"
    )
    
    # Test direct S3 upload
    print("\n1. Testing direct S3 upload...")
    s3_key = "media/test/test_upload.jpg"
    success, url = upload_to_s3(test_file, s3_key, metadata={'test': 'true'})
    
    if success:
        print(f"✅ Upload successful!")
        print(f"   URL: {url}")
    else:
        print(f"❌ Upload failed: {url}")
        return
    
    # Verify in S3
    print("\n2. Verifying in S3...")
    s3 = boto3.client(
        's3',
        aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
        region_name=settings.AWS_S3_REGION_NAME
    )
    
    try:
        response = s3.head_object(Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=s3_key)
        print(f"✅ File exists in S3!")
        print(f"   Size: {response['ContentLength']} bytes")
        print(f"   Type: {response['ContentType']}")
        print(f"   ETag: {response['ETag']}")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
    
    # Test public access
    print("\n3. Testing public access...")
    import requests
    public_url = f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{s3_key}"
    response = requests.get(public_url)
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        print("✅ Publicly accessible!")
    else:
        print(f"❌ Not publicly accessible: {response.status_code}")

if __name__ == "__main__":
    test_upload()