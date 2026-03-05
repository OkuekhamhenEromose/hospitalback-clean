import os
from django.db import models
from django.utils import timezone
from users.models import Profile
import random
import json
from django.utils.text import slugify
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import boto3
from PIL import Image
import io
import hashlib
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SEX_CHOICES = (('M', 'Male'), ('F', 'Female'), ('O', 'Other'))

APPOINTMENT_STATUS = (
    ('PENDING', 'Pending'),
    ('IN_REVIEW', 'In Review'),
    ('AWAITING_RESULTS', 'Awaiting Results'),
    ('COMPLETED', 'Completed'),
    ('CANCELLED', 'Cancelled'),
)

REQUEST_STATUS = (
    ('PENDING', 'Pending'),
    ('IN_PROGRESS', 'In Progress'),
    ('DONE', 'Done'),
    ('CANCELLED', 'Cancelled'),
)

# ==================== HELPER FUNCTIONS ====================

def create_s3_placeholder_image(text, width=800, height=400, img_format='JPEG'):
    """
    Create a colored placeholder image for S3
    """
    color_hash = hashlib.md5(text.encode()).hexdigest()[:6]
    img = Image.new('RGB', (width, height), color=f'#{color_hash}')
    
    buffer = io.BytesIO()
    
    if img_format.upper() == 'WEBP':
        img.save(buffer, format='WEBP', quality=85)
        content_type = 'image/webp'
    elif img_format.upper() == 'PNG':
        img.save(buffer, format='PNG')
        content_type = 'image/png'
    else:
        img.save(buffer, format='JPEG', quality=85)
        content_type = 'image/jpeg'
    
    buffer.seek(0)
    return buffer.getvalue(), content_type

# ==================== MAIN MODELS ====================

class Appointment(models.Model):
    patient = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='appointments')
    name = models.CharField(max_length=255)
    age = models.PositiveSmallIntegerField()
    sex = models.CharField(max_length=2, choices=SEX_CHOICES)
    address = models.TextField()
    booked_at = models.DateTimeField(auto_now_add=True)
    doctor = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_appointments')
    message = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=APPOINTMENT_STATUS, default='PENDING')

    class Meta:
        indexes = [
            models.Index(fields=['status', 'booked_at']),
            models.Index(fields=['patient', 'status']),
            models.Index(fields=['doctor', 'status']),
            models.Index(fields=['booked_at']),  # For date range queries
            models.Index(fields=['patient', '-booked_at']),
            models.Index(fields=['doctor', '-booked_at']),
        ]

    def __str__(self):
        return f"Appointment {self.id} - {self.name}"

    def assign_doctor(self):
        if self.doctor:
            return
            
        available_doctors = Profile.objects.filter(role='DOCTOR', user__is_active=True)
        
        if available_doctors.exists():
            assigned_doctor = random.choice(list(available_doctors))
            self.doctor = assigned_doctor
            self.save()
            print(f"Assigned doctor {assigned_doctor.fullname} to appointment {self.id}")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and not self.doctor:
            self.assign_doctor()

class Assignment(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='assignments')
    staff = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='assignments')
    role = models.CharField(max_length=20, choices=[('DOCTOR', 'Doctor'), ('NURSE', 'Nurse'), ('LAB', 'Lab Scientist')])
    assigned_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_staff')
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True, null=True)
    
    class Meta:
        unique_together = ['appointment', 'staff', 'role']
          
class TestRequest(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='test_requests')
    requested_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='test_requests_made')
    assigned_to = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='test_requests_assigned')
    tests = models.TextField(help_text="Comma-separated test list or JSON")
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['appointment', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['appointment', '-created_at']),
        ]

    def assign_lab_scientist(self):
        if self.assigned_to:
            return
            
        available_lab_scientists = Profile.objects.filter(role='LAB', user__is_active=True)
        
        if available_lab_scientists.exists():
            assigned_scientist = random.choice(list(available_lab_scientists))
            self.assigned_to = assigned_scientist
            self.save()
            print(f"Assigned lab scientist {assigned_scientist.fullname} to test request {self.id}")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and not self.assigned_to:
            self.assign_lab_scientist()
            
        if not is_new and self.status == 'DONE':
            appointment = self.appointment
            has_vitals = appointment.vital_requests.filter(status='DONE').exists()
            has_all_tests = appointment.test_requests.filter(status='PENDING').exists()
            
            if has_vitals and not has_all_tests:
                appointment.status = 'IN_REVIEW'
                appointment.save()

class VitalRequest(models.Model):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='vital_requests')
    requested_by = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='vital_requests_made')
    assigned_to = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='vital_requests_assigned')
    note = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=REQUEST_STATUS, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['appointment', 'status']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['appointment', '-created_at']),
        ]

    def assign_nurse(self):
        if self.assigned_to:
            return
            
        available_nurses = Profile.objects.filter(role='NURSE', user__is_active=True)
        
        if available_nurses.exists():
            assigned_nurse = random.choice(list(available_nurses))
            self.assigned_to = assigned_nurse
            self.save()
            print(f"Assigned nurse {assigned_nurse.fullname} to vital request {self.id}")

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        
        if is_new and not self.assigned_to:
            self.assign_nurse()
            
        if not is_new and self.status == 'DONE':
            appointment = self.appointment
            pending_tests = appointment.test_requests.filter(status='PENDING').exists()
            if not pending_tests:
                appointment.status = 'IN_REVIEW'
                appointment.save()

class Vitals(models.Model):
    vital_request = models.ForeignKey(
        VitalRequest,
        on_delete=models.CASCADE,
        related_name='vitals_entries',
        null=True,
        blank=True
    )
    nurse = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='vitals_recorded')
    blood_pressure = models.CharField(max_length=50, blank=True, null=True)
    respiration_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    pulse_rate = models.PositiveSmallIntegerField(null=True, blank=True)
    body_temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    height_cm = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    weight_kg = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

class LabResult(models.Model):
    test_request = models.ForeignKey(TestRequest, on_delete=models.CASCADE, related_name='lab_results', null=True, blank=True)
    lab_scientist = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='lab_results_posted')
    test_name = models.CharField(max_length=255)
    result = models.TextField(blank=True, null=True)
    units = models.CharField(max_length=50, blank=True, null=True)
    reference_range = models.CharField(max_length=100, blank=True, null=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

class MedicalReport(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE, related_name='medical_report')
    doctor = models.ForeignKey(Profile, on_delete=models.SET_NULL, null=True, blank=True, related_name='reports')
    medical_condition = models.TextField()
    drug_prescription = models.TextField(blank=True, null=True)
    advice = models.TextField(blank=True, null=True)
    next_appointment = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        appt = self.appointment
        appt.status = 'COMPLETED'
        appt.save()

# ==================== BLOG POST MODEL ====================

class BlogPost(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    content = models.TextField()
    author = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='blog_posts')

    featured_image = models.ImageField(upload_to='blog_images/', null=True, blank=True)
    image_1 = models.ImageField(upload_to='blog_images/', null=True, blank=True)
    image_2 = models.ImageField(upload_to='blog_images/', null=True, blank=True)

    published = models.BooleanField(default=False)
    published_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    slug = models.SlugField(max_length=200, unique=True, blank=True)

    table_of_contents = models.JSONField(default=list, blank=True)
    enable_toc = models.BooleanField(default=True)
    subheadings = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-published_date', '-created_at']
        indexes = [
            models.Index(fields=['published', '-published_date']),
            models.Index(fields=['slug']),
            models.Index(fields=['author', 'published']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.published and not self.published_date:
            self.published_date = timezone.now()

        if not self.slug:
            base_slug = slugify(self.title)
            slug = base_slug
            counter = 1
            # Check for existing slugs and append number if needed
            while BlogPost.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug

        if self.content:
            if self.enable_toc:
                self.generate_table_of_contents()
            self.extract_subheadings()

        super().save(*args, **kwargs)
        

    def generate_table_of_contents(self):
        import re

        pattern = r'<h([1-6])[^>]*>(.*?)</h\1>'
        headings = re.findall(pattern, self.content)

        toc_items = []
        for level, html_title in headings:
            clean_title = re.sub(r'<[^>]+>', '', html_title).strip()
            anchor = slugify(clean_title)
            toc_items.append({
                "id": len(toc_items) + 1,
                "title": clean_title,
                "anchor": anchor,
                "level": int(level)
            })

        self.table_of_contents = toc_items

    def extract_subheadings(self):
        import re

        pattern = r'<h([1-6])[^>]*>(.*?)</h\1>(.*?)(?=<h[1-6]|$)'
        matches = re.findall(pattern, self.content or "", re.DOTALL)

        structured = []

        if matches:
            for level, html_title, section_body in matches:
                clean_title = re.sub(r'<[^>]+>', '', html_title).strip()
                clean_desc = re.sub(r'<[^>]+>', '', section_body).strip()

                structured.append({
                    "title": clean_title,
                    "level": int(level),
                    "description": clean_desc[:200] + ("..." if len(clean_desc) > 200 else ""),
                    "full_content": section_body.strip()
                })
        else:
            if self.description:
                lines = self.description.split(". ")[:2]
                for i, line in enumerate(lines):
                    structured.append({
                        "title": f"Section {i+1}",
                        "level": 2,
                        "description": line[:200] + ("..." if len(line) > 200 else ""),
                        "full_content": line
                    })

        self.subheadings = structured[:6]

    # ==================== SIMPLE IMAGE UPLOAD FUNCTION ====================

def upload_image_to_s3_simple(image_field, blog_post, field_name):
    """Simple, reliable image upload to S3 - FIXED VERSION"""
    import boto3
    from django.conf import settings
    import logging
    import os
    
    logger = logging.getLogger(__name__)
    
    if not image_field or not hasattr(image_field, 'name') or not image_field.name:
        logger.warning(f"[SKIP] No image field for {field_name}")
        return False
    
    try:
        # Setup S3 client
        s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME
        
        # IMPORTANT: Get the actual file path from Django storage
        # For default_storage, get the file path relative to media root
        from django.core.files.storage import default_storage
        
        # Extract the path relative to media/ directory
        if image_field.name.startswith('blog_images/'):
            s3_key = f"media/{image_field.name}"
        else:
            s3_key = f"media/blog_images/{os.path.basename(image_field.name)}"
        
        logger.info(f"[UPLOAD] Processing {field_name}: {image_field.name} -> S3 Key: {s3_key}")
        
        # Check if already exists in S3 (skip if it's an actual image)
        try:
            existing = s3.head_object(Bucket=bucket_name, Key=s3_key)
            metadata = existing.get('Metadata', {})
            if metadata.get('actual_image') == 'true':
                logger.info(f"[SKIP] Already exists in S3 with actual_image=true: {s3_key}")
                return True
        except:
            pass  # File doesn't exist, continue upload
        
        # Get the actual file from Django storage
        if default_storage.exists(image_field.name):
            logger.info(f"[FOUND] File exists in default storage: {image_field.name}")
            
            # Open file from Django storage
            with default_storage.open(image_field.name, 'rb') as f:
                file_content = f.read()
                file_size = len(file_content)
                
                # Determine content type from filename
                filename = image_field.name.lower()
                if filename.endswith('.png'):
                    content_type = 'image/png'
                elif filename.endswith('.webp'):
                    content_type = 'image/webp'
                elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
                    content_type = 'image/jpeg'
                else:
                    content_type = 'application/octet-stream'
                
                # Upload to S3
                logger.info(f"[UPLOADING] {s3_key} ({file_size} bytes)...")
                
                s3.put_object(
                    Bucket=bucket_name,
                    Key=s3_key,
                    Body=file_content,
                    ContentType=content_type,
                    ACL='public-read',
                    Metadata={
                        'blog_id': str(blog_post.id),
                        'blog_title': blog_post.title[:100],
                        'field': field_name,
                        'actual_image': 'true',
                        'uploaded_at': datetime.now().isoformat(),
                        'upload_method': 'django_signal'
                    }
                )
                
                logger.info(f"[SUCCESS] Uploaded to S3: {s3_key}")
                return True
        else:
            logger.warning(f"[MISSING] File not in default storage: {image_field.name}")
            
            # Try to get file from the ImageField directly
            try:
                logger.info(f"[ATTEMPT] Trying to read from ImageField directly...")
                
                # Reset file pointer to beginning
                if hasattr(image_field, 'file') and image_field.file:
                    image_field.file.seek(0)
                    file_content = image_field.file.read()
                    
                    # Determine content type
                    filename = image_field.name.lower()
                    if filename.endswith('.png'):
                        content_type = 'image/png'
                    elif filename.endswith('.webp'):
                        content_type = 'image/webp'
                    elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
                        content_type = 'image/jpeg'
                    else:
                        content_type = 'application/octet-stream'
                    
                    # Upload to S3
                    logger.info(f"[UPLOADING-DIRECT] {s3_key} ({len(file_content)} bytes)...")
                    
                    s3.put_object(
                        Bucket=bucket_name,
                        Key=s3_key,
                        Body=file_content,
                        ContentType=content_type,
                        ACL='public-read',
                        Metadata={
                            'blog_id': str(blog_post.id),
                            'blog_title': blog_post.title[:100],
                            'field': field_name,
                            'actual_image': 'true',
                            'uploaded_at': datetime.now().isoformat(),
                            'upload_method': 'direct_imagefield'
                        }
                    )
                    
                    logger.info(f"[SUCCESS] Uploaded from ImageField: {s3_key}")
                    return True
                    
            except Exception as e:
                logger.error(f"[ERROR] Cannot read from ImageField: {str(e)}")
                return False
                
    except Exception as e:
        logger.error(f"[ERROR] Failed to upload {image_field.name if image_field else 'unknown'}: {str(e)}")
        import traceback
        logger.error(f"[TRACEBACK] {traceback.format_exc()}")
        return False

# ==================== SINGLE SIGNAL HANDLER ====================

@receiver(post_save, sender=BlogPost)
def handle_blog_post_save(sender, instance, created, **kwargs):
    """SINGLE signal handler for uploading images to S3 - FIXED VERSION"""
    import logging
    logger = logging.getLogger(__name__)
    from hospital.utils import upload_to_s3
    
    if kwargs.get('raw', False) or kwargs.get('update_fields'):
        return
    
    logger.info(f"📝 Processing images for blog post: {instance.id} - {instance.title}")
    
    # List of image fields to process
    image_fields = [
        ('featured_image', instance.featured_image),
        ('image_1', instance.image_1),
        ('image_2', instance.image_2),
    ]
    
    # Process each image
    for field_name, image_field in image_fields:
        if image_field and image_field.name:
            logger.info(f"  ⬆️ Uploading {field_name}: {image_field.name}")
            
            # Get filename and create S3 key
            filename = os.path.basename(image_field.name)
            s3_key = f"media/blog_images/{filename}"
            
            # Upload to S3 (file already saved locally by Django)
            success, result = upload_to_s3(
                image_field,
                s3_key,
                metadata={
                    'blog_id': str(instance.id),
                    'blog_title': instance.title[:100],
                    'field': field_name
                }
            )
            
            if success:
                logger.info(f"  ✅ Uploaded to S3: {result}")
            else:
                logger.error(f"  ❌ Failed to upload: {result}")

                