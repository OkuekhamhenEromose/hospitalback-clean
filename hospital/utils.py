# hospital/utils.py
import boto3
from django.conf import settings
import logging
from datetime import datetime
import mimetypes

logger = logging.getLogger(__name__)

def upload_to_s3(file_field, destination_key, metadata=None, acl='public-read'):
    """
    Upload a file to S3 with verification
    
    Args:
        file_field: Django file field (with .file attribute)
        destination_key: S3 key (path)
        metadata: dict of metadata to attach
        acl: ACL policy
    
    Returns:
        tuple: (success, url or error)
    """
    if not settings.AWS_CREDENTIALS_PROVIDED:
        logger.warning("AWS credentials not provided, skipping S3 upload")
        return False, None
    
    try:
        # Initialize S3 client
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        # Reset file pointer and read content
        file_field.file.seek(0)
        file_content = file_field.file.read()
        
        # Determine content type
        content_type = getattr(file_field.file, 'content_type', None)
        if not content_type:
            content_type = mimetypes.guess_type(destination_key)[0] or 'application/octet-stream'
        
        # Prepare metadata
        if metadata is None:
            metadata = {}
        metadata['uploaded_at'] = datetime.now().isoformat()
        
        # Upload to S3
        logger.info(f"📤 Uploading to S3: {destination_key} ({len(file_content)} bytes)")
        
        s3.put_object(
            Bucket=bucket_name,
            Key=destination_key,
            Body=file_content,
            ContentType=content_type,
            ACL=acl,
            Metadata=metadata
        )
        
        # Verify upload
        s3.head_object(Bucket=bucket_name, Key=destination_key)
        logger.info(f"✅ Verified file in S3: {destination_key}")
        
        # Generate URL
        url = f"https://{bucket_name}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/{destination_key}"
        
        return True, url
        
    except Exception as e:
        logger.error(f"❌ S3 upload failed for {destination_key}: {e}")
        return False, str(e)