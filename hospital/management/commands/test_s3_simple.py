from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

class Command(BaseCommand):
    help = 'Simple S3 upload test'
    
    def handle(self, *args, **options):
        print("📤 Testing S3 Upload with default_storage...")
        
        # Create a test file
        test_content = b"This is a test file for S3 upload"
        
        # Upload directly using default storage
        file_name = "test_uploads/simple_test.txt"
        
        try:
            # Save file to S3
            saved_name = default_storage.save(file_name, ContentFile(test_content))
            print(f"✅ File saved to: {saved_name}")
            
            # Get URL
            file_url = default_storage.url(saved_name)
            print(f"✅ File URL: {file_url}")
            
            # Check if file exists
            if default_storage.exists(saved_name):
                print(f"✅ File exists in S3")
            else:
                print(f"❌ File not found in S3")
                
            # Read back the file
            if default_storage.exists(saved_name):
                file_content = default_storage.open(saved_name).read()
                print(f"✅ File content verified: {file_content.decode()}")
            
        except Exception as e:
            print(f"❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()