# users/pipeline.py
from .models import Profile
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)

def create_profile(backend, user, response, *args, **kwargs):
    """
    Pipeline to create or update user profile after social authentication
    """
    try:
        if backend.name == 'google':
            # Get or create profile
            profile, created = Profile.objects.get_or_create(user=user)
            
            # Update profile with Google data
            if response.get('name'):
                profile.fullname = response.get('name')
                
            # Get profile picture from Google
            if response.get('picture'):
                # You might want to download and save the picture
                # For now, we'll just log it
                logger.info(f"Google profile picture available: {response.get('picture')}")
            
            # Save profile
            profile.save()
            
            logger.info(f"Profile {'created' if created else 'updated'} for user {user.email}")
            
    except Exception as e:
        logger.error(f"Error creating profile for user {user.email}: {str(e)}")