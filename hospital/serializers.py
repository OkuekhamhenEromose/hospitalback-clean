# hospital/serializers.py - COMPLETE UPDATED VERSION
from rest_framework import serializers
from .models import (
    Appointment, Vitals, LabResult, MedicalReport, BlogPost,
    TestRequest, VitalRequest, Assignment
)
from users.models import Profile
from users.serializers import ProfileSerializer
from django.conf import settings

class TestRequestSerializer(serializers.ModelSerializer):
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=Profile.objects.all(), required=False, allow_null=True
    )

    class Meta:
        model = TestRequest
        fields = '__all__'
        read_only_fields = ['requested_by', 'created_at', 'updated_at']

class VitalRequestSerializer(serializers.ModelSerializer):
    requested_by = ProfileSerializer(read_only=True)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=Profile.objects.all(), required=False, allow_null=True)

    class Meta:
        model = VitalRequest
        fields = ['id', 'appointment', 'requested_by', 'assigned_to', 'note', 'status', 'created_at', 'updated_at']
        read_only_fields = ['requested_by', 'created_at', 'updated_at']

class VitalsSerializer(serializers.ModelSerializer):
    nurse = ProfileSerializer(read_only=True)
    vital_request = serializers.PrimaryKeyRelatedField(queryset=VitalRequest.objects.all())

    class Meta:
        model = Vitals
        fields = ['id', 'vital_request', 'nurse', 'blood_pressure', 'respiration_rate', 'pulse_rate', 'body_temperature', 'height_cm', 'weight_kg', 'recorded_at']
        read_only_fields = ['nurse', 'recorded_at']

class LabResultSerializer(serializers.ModelSerializer):
    lab_scientist = ProfileSerializer(read_only=True)
    test_request = serializers.PrimaryKeyRelatedField(queryset=TestRequest.objects.all())

    class Meta:
        model = LabResult
        fields = ['id', 'test_request', 'lab_scientist', 'test_name', 'result', 'units', 'reference_range', 'recorded_at']
        read_only_fields = ['lab_scientist', 'recorded_at']

class MedicalReportSerializer(serializers.ModelSerializer):
    doctor = ProfileSerializer(read_only=True)

    class Meta:
        model = MedicalReport
        fields = ['id', 'appointment', 'doctor', 'medical_condition', 'drug_prescription', 'advice', 'next_appointment', 'created_at']
        read_only_fields = ['doctor', 'created_at']

class AssignmentSerializer(serializers.ModelSerializer):
    appointment = serializers.PrimaryKeyRelatedField(read_only=True)
    appointment_id = serializers.PrimaryKeyRelatedField(
        queryset=Appointment.objects.all(), write_only=True, source='appointment'
    )
    staff = ProfileSerializer(read_only=True)
    staff_id = serializers.PrimaryKeyRelatedField(
        queryset=Profile.objects.all(), write_only=True, source='staff'
    )
    assigned_by = ProfileSerializer(read_only=True)
    
    class Meta:
        model = Assignment
        fields = '__all__'
        read_only_fields = ['assigned_by', 'assigned_at']

class AppointmentSerializer(serializers.ModelSerializer):
    patient = ProfileSerializer(read_only=True)
    doctor = serializers.PrimaryKeyRelatedField(read_only=True)
    assignments = AssignmentSerializer(many=True, read_only=True)
    assigned_doctor = serializers.SerializerMethodField()
    assigned_nurse = serializers.SerializerMethodField()
    assigned_lab = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = ['id', 'patient', 'patient_id', 'name', 'age', 'sex', 'message', 'address', 
                 'booked_at', 'doctor', 'status', 'assignments', 'assigned_doctor', 
                 'assigned_nurse', 'assigned_lab']
        read_only_fields = ['booked_at', 'status', 'doctor']

    def get_assigned_doctor(self, obj):
        assignment = obj.assignments.filter(role='DOCTOR').first()
        return AssignmentSerializer(assignment).data if assignment else None
    
    def get_assigned_nurse(self, obj):
        assignment = obj.assignments.filter(role='NURSE').first()
        return AssignmentSerializer(assignment).data if assignment else None
    
    def get_assigned_lab(self, obj):
        assignment = obj.assignments.filter(role='LAB').first()
        return AssignmentSerializer(assignment).data if assignment else None

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        
        # Always include basic related data for better UX
        # Include test requests
        if instance.test_requests.exists():
            rep['test_requests'] = TestRequestSerializer(
                instance.test_requests.all(), 
                many=True
            ).data
        
        # Include vital requests
        if instance.vital_requests.exists():
            rep['vital_requests'] = VitalRequestSerializer(
                instance.vital_requests.all(), 
                many=True
            ).data
        
        # Include vitals if available
        vital_request = instance.vital_requests.last()
        if vital_request and vital_request.vitals_entries.exists():
            rep['vitals'] = VitalsSerializer(
                vital_request.vitals_entries.last()
            ).data
        
        # Include lab results if available
        lab_results_data = []
        for test_request in instance.test_requests.all():
            if test_request.lab_results.exists():
                lab_results_data.extend(
                    LabResultSerializer(
                        test_request.lab_results.all(), 
                        many=True
                    ).data
                )
        if lab_results_data:
            rep['lab_results'] = lab_results_data
        
        # Include medical report if available
        if hasattr(instance, 'medical_report'):
            rep['medical_report'] = MedicalReportSerializer(
                instance.medical_report
            ).data
        
        return rep

# Enhanced Appointment Serializer for detailed view
class AppointmentDetailSerializer(serializers.ModelSerializer):
    patient = ProfileSerializer(read_only=True)
    doctor = ProfileSerializer(read_only=True)
    assignments = AssignmentSerializer(many=True, read_only=True)
    test_requests = TestRequestSerializer(many=True, read_only=True)
    vital_requests = VitalRequestSerializer(many=True, read_only=True)
    
    class Meta:
        model = Appointment
        fields = '__all__'

# ---------------- Enhanced Blog Serializers ---------------- #

class SubheadingSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField()
    level = serializers.IntegerField()
    description = serializers.CharField()
    full_content = serializers.CharField()

class TOCSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    level = serializers.IntegerField()
    anchor = serializers.CharField()

# ==================== UPDATED BLOG SERIALIZERS WITH PROPER S3 URLS ====================

class BlogPostListSerializer(serializers.ModelSerializer):
    subheadings = serializers.SerializerMethodField()
    featured_image_url = serializers.SerializerMethodField()
    image_1_url = serializers.SerializerMethodField()
    image_2_url = serializers.SerializerMethodField()
    author_name = serializers.CharField(source='author.fullname', read_only=True)
    author_role = serializers.CharField(source='author.role', read_only=True)
    
    class Meta:
        model = BlogPost
        fields = [
            "id", "title", "slug", "description",
            "featured_image_url", "image_1_url", "image_2_url",
            "published", "created_at", "table_of_contents", 
            "subheadings", "author_name", "author_role"
        ]

    def get_subheadings(self, obj):
        return [
            {**s, "id": idx + 1} for idx, s in enumerate(obj.subheadings)
        ]
    
    def get_featured_image_url(self, obj):
        if obj.featured_image and obj.featured_image.name:
            # Return full S3 URL
            try:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.featured_image.name}"
            except:
                # Fallback if settings not available
                if hasattr(obj.featured_image, 'url'):
                    return obj.featured_image.url
                return None
        return None
    
    def get_image_1_url(self, obj):
        if obj.image_1 and obj.image_1.name:
            try:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.image_1.name}"
            except:
                if hasattr(obj.image_1, 'url'):
                    return obj.image_1.url
                return None
        return None
    
    def get_image_2_url(self, obj):
        if obj.image_2 and obj.image_2.name:
            try:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.image_2.name}"
            except:
                if hasattr(obj.image_2, 'url'):
                    return obj.image_2.url
                return None
        return None

class BlogPostSerializer(serializers.ModelSerializer):
    table_of_contents = TOCSerializer(many=True, read_only=True)
    subheadings = SubheadingSerializer(many=True, read_only=True)
    featured_image_url = serializers.SerializerMethodField()
    image_1_url = serializers.SerializerMethodField()
    image_2_url = serializers.SerializerMethodField()
    author_name = serializers.CharField(source='author.fullname', read_only=True)
    author_role = serializers.CharField(source='author.role', read_only=True)
    
    class Meta:
        model = BlogPost
        fields = [
            "id", "title", "description", "content", 
            "author", "author_name", "author_role",
            "featured_image_url", "image_1_url", "image_2_url",
            "published", "published_date", "created_at", "updated_at", 
            "slug", "table_of_contents", "enable_toc", "subheadings"
        ]
        read_only_fields = ['slug', 'table_of_contents', 'subheadings', 'author']

    def get_featured_image_url(self, obj):
        if obj.featured_image:
            try:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.featured_image.name}"
            except:
                return None
        return None
    
    def get_image_1_url(self, obj):
        if obj.image_1:
            try:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.image_1.name}"
            except:
                return None
        return None
    
    def get_image_2_url(self, obj):
        if obj.image_2:
            try:
                return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.image_2.name}"
            except:
                return None
        return None
    
    
    def create(self, validated_data):
        # Set the author to the current user
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            profile = request.user.profile
            validated_data['author'] = profile
        return super().create(validated_data)

class BlogPostCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = "__all__"
        read_only_fields = ['author']

# Profile Serializer for staff listings
class StaffProfileSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)
    profile_pix = serializers.SerializerMethodField()
    
    class Meta:
        model = Profile
        fields = ['id', 'user', 'fullname', 'phone', 'gender', 'profile_pix', 'role']
    
    def get_profile_pix(self, obj):
        if obj.profile_pix:
            return f"https://{settings.AWS_STORAGE_BUCKET_NAME}.s3.{settings.AWS_S3_REGION_NAME}.amazonaws.com/media/{obj.profile_pix.name}"
        return None

# Appointment assignment serializer
class AppointmentAssignmentSerializer(serializers.Serializer):
    appointment_id = serializers.IntegerField(required=True)
    staff_id = serializers.IntegerField(required=True)
    role = serializers.ChoiceField(choices=['DOCTOR', 'NURSE', 'LAB'], required=True)
    notes = serializers.CharField(required=False, allow_blank=True)