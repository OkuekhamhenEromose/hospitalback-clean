# users/serializers.py
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Profile, GENDER_CHOICES, ROLE_CHOICES
from django.contrib.auth.password_validation import validate_password
from .utils import SendMail
import logging
from hospital.utils import upload_to_s3

logger = logging.getLogger(__name__)


# ============================================================
# UTILITY — IMAGE URL
# ============================================================

def get_absolute_profile_image_url(profile_pix):
    """
    Return the public URL for a profile ImageField.

    FIX: The original had two fallback branches that constructed URLs by
    concatenating AWS_S3_CUSTOM_DOMAIN or BASE_URL with the field name as an
    f-string. Those paths:
      1. Bypassed the storage backend entirely.
      2. Produced broken URLs in local dev (no S3 bucket configured).
      3. Would stop working if the bucket or region ever changed.

    The storage backend's .url property handles all of this correctly for both
    S3 and local FileSystemStorage. Use it exclusively.
    """
    if not profile_pix:
        return None
    try:
        if not getattr(profile_pix, 'name', None) or str(profile_pix.name).strip() == '':
            return None
        url = profile_pix.url
        # Normalise http → https for S3 (boto3 can return http in some configs)
        if url and 's3.amazonaws.com' in url and url.startswith('http://'):
            url = url.replace('http://', 'https://')
        return url
    except ValueError:
        # "has no file associated with it" — field row exists but file was deleted
        return None
    except Exception as e:
        logger.error('Error getting URL for profile image: %s', e)
        return None


# ============================================================
# USER SERIALIZER
# ============================================================

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = ['id', 'username', 'email']


# ============================================================
# PROFILE SERIALIZER
# ============================================================

class ProfileSerializer(serializers.ModelSerializer):
    user        = UserSerializer(read_only=True)
    profile_pix = serializers.SerializerMethodField()

    class Meta:
        model  = Profile
        fields = ['user', 'fullname', 'phone', 'gender', 'profile_pix', 'role']

    def get_profile_pix(self, obj):
        """
        Return the absolute URL for the profile image via the storage backend.

        FIX: The original had a second fallback path that constructed S3 URLs
        manually as an f-string using AWS_S3_CUSTOM_DOMAIN. That path bypassed
        the storage backend and is now removed. get_absolute_profile_image_url()
        delegates to .url which works for both S3 and local filesystem.
        """
        try:
            if not obj.profile_pix or str(obj.profile_pix) == '':
                logger.debug('%s: no profile image', obj.user.username)
                return None

            url = get_absolute_profile_image_url(obj.profile_pix)
            logger.debug('%s: profile_pix URL → %s', obj.user.username, url)
            return url

        except Exception as e:
            logger.error('Error getting profile_pix for %s: %s', obj.user.username, e)
            return None


# ============================================================
# REGISTRATION SERIALIZER
# ============================================================

class RegistrationSerializer(serializers.Serializer):
    username    = serializers.CharField()
    email       = serializers.EmailField()
    password1   = serializers.CharField(write_only=True)
    password2   = serializers.CharField(write_only=True)
    fullname    = serializers.CharField()
    phone       = serializers.CharField(required=False, allow_blank=True)
    gender      = serializers.ChoiceField(choices=GENDER_CHOICES, required=False)
    role        = serializers.ChoiceField(choices=ROLE_CHOICES, default='PATIENT')
    profile_pix = serializers.ImageField(required=False, allow_null=True)

    def validate(self, data):
        if data['password1'] != data['password2']:
            raise serializers.ValidationError('Passwords do not match.')
        validate_password(data['password1'])
        if User.objects.filter(username=data['username']).exists():
            raise serializers.ValidationError('Username already taken.')
        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError('Email already registered.')
        return data

    def create(self, validated_data):
        username    = validated_data.pop('username')
        email       = validated_data.pop('email')
        password    = validated_data.pop('password1')
        validated_data.pop('password2', None)
        profile_pix = validated_data.pop('profile_pix', None)

        user = User.objects.create_user(username=username, email=email, password=password)

        profile, _ = Profile.objects.get_or_create(user=user)
        profile.fullname = validated_data.get('fullname', '')
        profile.phone    = validated_data.get('phone', '')
        profile.gender   = validated_data.get('gender', None)
        profile.role     = validated_data.get('role', 'PATIENT')

        # In RegistrationSerializer.create method, find the profile_pix section and replace with:

        if profile_pix:
            import os
            from django.utils.text import slugify
            from datetime import datetime
            from django.core.files.storage import default_storage
            from django.core.files import File
            
            ext = os.path.splitext(profile_pix.name)[1]
            clean_username = slugify(username)
            filename = f'{clean_username}_profile{ext}'
            s3_key = f"media/profile/{filename}"
            
            logger.info(
                'Processing profile image for %s — %s (%d bytes)',
                username, filename, profile_pix.size,
            )

                # Save to Django's default storage (local)
            saved_path = default_storage.save(f"profile/{filename}", profile_pix)
            logger.info(f'✅ Local save complete: {saved_path}')
            
            with default_storage.open(saved_path, 'rb') as f:
                django_file = File(f)
                
                # Upload to S3
                success, result = upload_to_s3(
                    django_file,
                    s3_key,
                    metadata={
                        'username': username, 
                        'original_name': profile_pix.name,
                        'uploaded_at': datetime.now().isoformat()
                    }
                )
        
                if success:
                    logger.info(f'✅ S3 upload successful: {result}')
                    # Update the profile with the file reference
                    profile.profile_pix.name = saved_path
                else:
                    logger.error(f'❌ S3 upload failed: {result}')
            
            profile.save()


        else:
            profile.save()
            logger.info('Profile created without image for %s', username)
            
        try:
            import threading

            def send_email_async():
                try:
                    SendMail(email)
                except Exception as e:
                    logger.warning('Failed to send welcome email to %s: %s', email, e)

            email_thread        = threading.Thread(target=send_email_async)
            email_thread.daemon = True
            email_thread.start()

        except Exception as e:
            logger.warning('Failed to schedule welcome email for %s: %s', email, e)

        return profile


# ============================================================
# UPDATE PROFILE SERIALIZER
# ============================================================

class UpdateProfileSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', required=False)
    email    = serializers.EmailField(source='user.email',   required=False)

    class Meta:
        model  = Profile
        fields = ['username', 'email', 'fullname', 'phone', 'gender', 'profile_pix', 'role']

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        user      = instance.user

        if 'username' in user_data:
            user.username = user_data['username']
        if 'email' in user_data:
            user.email = user_data['email']
        user.save()

        for attr in ('fullname', 'phone', 'gender', 'profile_pix', 'role'):
            if attr in validated_data:
                setattr(instance, attr, validated_data[attr])

        instance.save()
        return instance