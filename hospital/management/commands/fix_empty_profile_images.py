# users/management/commands/fix_empty_profile_images.py
from django.core.management.base import BaseCommand
from users.models import Profile
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Fix profiles with empty image fields'

    def handle(self, *args, **options):
        self.stdout.write("🔧 Fixing profiles with empty image fields...")
        
        # Find profiles with empty or null profile_pix
        profiles = Profile.objects.filter(profile_pix__isnull=True) | \
                   Profile.objects.filter(profile_pix__exact='')
        
        count = 0
        for profile in profiles:
            try:
                # Check if profile_pix is actually empty
                if not profile.profile_pix or str(profile.profile_pix) == '':
                    # Set to None to clear the field
                    profile.profile_pix = None
                    profile.save()
                    self.stdout.write(f"✅ Fixed {profile.user.username}: Cleared empty image field")
                    count += 1
            except Exception as e:
                self.stdout.write(f"❌ Error fixing {profile.user.username}: {e}")
        
        self.stdout.write(f"🎉 Fixed {count} profiles with empty image fields")