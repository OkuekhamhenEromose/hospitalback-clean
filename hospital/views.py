# hospital/views.py
from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from .models import (
    Appointment, TestRequest, VitalRequest, Vitals, LabResult, MedicalReport, BlogPost
)
from users.models import Profile
from django.db import models, transaction
from .serializers import (
    AppointmentSerializer, TestRequestSerializer, VitalRequestSerializer,
    VitalsSerializer, LabResultSerializer, MedicalReportSerializer,
    AssignmentSerializer, AppointmentAssignmentSerializer,
    StaffProfileSerializer, AppointmentDetailSerializer,
    BlogPostSerializer, BlogPostCreateSerializer, BlogPostListSerializer,
)
from rest_framework.exceptions import PermissionDenied
from .permissions import IsRole
from django.shortcuts import get_object_or_404
from django.db.models import Q, Prefetch
from users.serializers import ProfileSerializer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Assignment

from django.core.cache import cache
from .base_views import OptimizedAPIView, CacheMixin
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers

# FIX: Import the safe helper instead of calling cache.delete_pattern() directly.
# cache.delete_pattern() only exists on django-redis. On LocMemCache (local dev
# or when Redis is unavailable) it raises AttributeError and crashes the request.
from api.settings import safe_cache_delete_pattern

import logging
logger = logging.getLogger(__name__)


# --------------- Appointment ---------------

class AppointmentCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['PATIENT']
    serializer_class = AppointmentSerializer

    def perform_create(self, serializer):
        profile = self.request.user.profile

        # FIX: Doctor auto-assignment has been moved into Appointment.save()
        # using select_for_update(skip_locked=True) inside an atomic block so
        # two simultaneous bookings can never be assigned to the same doctor.
        # The previous random.choice(list(available_doctors)) here:
        #   1. Loaded every doctor into memory.
        #   2. Had no locking — two concurrent requests could pick the same doctor.
        # Appointment.save() handles assignment safely; just save the patient here.
        appointment = serializer.save(patient=profile)
        logger.info('Appointment %d created for patient: %s', appointment.pk, profile.user.username)

# Remove these decorators:
# @method_decorator(cache_page(60))
# @method_decorator(vary_on_headers('Authorization'))

# Replace with manual caching in the get method:

class AppointmentListView(generics.ListAPIView, CacheMixin):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AppointmentSerializer
    cache_timeout = 60
    cache_key_prefix = 'appointments'

    def get_queryset(self):
        profile = self.request.user.profile
        base_queryset = Appointment.objects.select_related(
            'patient', 'patient__user',
            'doctor',  'doctor__user',
        ).prefetch_related(
            Prefetch(
                'test_requests',
                queryset=TestRequest.objects.select_related('assigned_to')
                                            .prefetch_related('lab_results'),
            ),
            Prefetch(
                'vital_requests',
                queryset=VitalRequest.objects.select_related('assigned_to')
                                             .prefetch_related('vitals_entries'),
            ),
            Prefetch(
                'assignments',
                queryset=Assignment.objects.select_related('staff', 'assigned_by'),
            ),
            'medical_report',
        )

        if profile.role == 'PATIENT':
            return base_queryset.filter(patient=profile).order_by('-booked_at')
        elif profile.role == 'DOCTOR':
            return base_queryset.filter(doctor=profile).order_by('-booked_at')
        else:
            return base_queryset.all().order_by('-booked_at')

    def get(self, request, *args, **kwargs):
        # Manual caching - cache the serialized data, not the Response object
        cache_key = f"{self.cache_key_prefix}:{request.user.id}:{request.GET.urlencode()}"
        cached_data = cache.get(cache_key)
        
        if cached_data:
            return Response(cached_data)
        
        response = super().get(request, *args, **kwargs)
        cache.set(cache_key, response.data, self.cache_timeout)
        return response


class AppointmentDetailView(generics.RetrieveAPIView, CacheMixin):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AppointmentDetailSerializer
    cache_timeout = 30
    cache_key_prefix = 'appointment_detail'

    def get_queryset(self):
        return Appointment.objects.select_related(
            'patient', 'patient__user',
            'doctor',  'doctor__user',
        ).prefetch_related(
            Prefetch(
                'test_requests',
                queryset=TestRequest.objects.select_related('assigned_to')
                                            .prefetch_related('lab_results'),
            ),
            Prefetch(
                'vital_requests',
                queryset=VitalRequest.objects.select_related('assigned_to')
                                             .prefetch_related('vitals_entries'),
            ),
            Prefetch(
                'assignments',
                queryset=Assignment.objects.select_related('staff', 'assigned_by'),
            ),
            'medical_report',
        )

    @method_decorator(cache_page(30))
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


# --------------- Assignment ---------------

class AssignmentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer
    queryset = Assignment.objects.all()

    def get_queryset(self):
        profile = self.request.user.profile
        if profile.role == 'ADMIN':
            return Assignment.objects.all()
        elif profile.role == 'DOCTOR':
            return Assignment.objects.filter(appointment__doctor=profile)
        elif profile.role == 'NURSE':
            return Assignment.objects.filter(staff=profile, role='NURSE')
        elif profile.role == 'LAB':
            return Assignment.objects.filter(staff=profile, role='LAB')
        return Assignment.objects.none()


class AppointmentAssignmentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        appointment_id = self.kwargs['appointment_id']
        return Assignment.objects.filter(appointment_id=appointment_id)


class AvailableStaffView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StaffProfileSerializer

    def get_queryset(self):
        role = self.request.query_params.get('role', '').upper()
        valid_roles = {'DOCTOR', 'NURSE', 'LAB'}
        if role and role in valid_roles:
            return Profile.objects.filter(role=role, user__is_active=True)
        return Profile.objects.filter(role__in=valid_roles, user__is_active=True)


class AssignStaffView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['ADMIN', 'DOCTOR']

    def post(self, request):
        serializer = AppointmentAssignmentSerializer(data=request.data)
        if serializer.is_valid():
            appointment_id = serializer.validated_data['appointment_id']
            staff_id       = serializer.validated_data['staff_id']
            role           = serializer.validated_data['role']
            notes          = serializer.validated_data.get('notes', '')

            try:
                appointment = Appointment.objects.get(id=appointment_id)
                staff       = Profile.objects.get(id=staff_id)

                if staff.role != role:
                    return Response(
                        {'error': f'Staff member is not a {role}'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                assignment, created = Assignment.objects.update_or_create(
                    appointment=appointment,
                    role=role,
                    defaults={
                        'staff':       staff,
                        'assigned_by': request.user.profile,
                        'notes':       notes,
                    },
                )

                if role == 'DOCTOR':
                    # FIX: Use queryset .update() instead of appointment.save() to
                    # avoid triggering Appointment.save() → _assign_doctor() recursion.
                    Appointment.objects.filter(pk=appointment.pk).update(doctor=staff)
                elif role == 'NURSE':
                    VitalRequest.objects.get_or_create(
                        appointment=appointment,
                        defaults={
                            'assigned_to':  staff,
                            'requested_by': request.user.profile,
                        },
                    )
                elif role == 'LAB':
                    TestRequest.objects.get_or_create(
                        appointment=appointment,
                        defaults={
                            'assigned_to':  staff,
                            'requested_by': request.user.profile,
                            'tests':        'General tests',
                        },
                    )

                logger.info(
                    'Assigned %s (%s) to appointment %d by %s',
                    staff.fullname, role, appointment.pk,
                    request.user.profile.fullname,
                )
                return Response({
                    'message':    f'Successfully assigned {staff.fullname} as {role}',
                    'assignment': AssignmentSerializer(assignment).data,
                })

            except Appointment.DoesNotExist:
                return Response({'error': 'Appointment not found'}, status=status.HTTP_404_NOT_FOUND)
            except Profile.DoesNotExist:
                return Response({'error': 'Staff member not found'}, status=status.HTTP_404_NOT_FOUND)
            except Exception as e:
                logger.error('AssignStaffView error: %s', e)
                return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PatientListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['ADMIN', 'DOCTOR']
    serializer_class = StaffProfileSerializer

    def get_queryset(self):
        patient_ids = Appointment.objects.values_list('patient_id', flat=True).distinct()
        return Profile.objects.filter(
            id__in=patient_ids, role='PATIENT',
        ).order_by('-user__date_joined')


# --------------- VitalRequest (doctor → nurse) ---------------

class VitalRequestCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['DOCTOR']
    serializer_class = VitalRequestSerializer

    def perform_create(self, serializer):
        vital_request = serializer.save(requested_by=self.request.user.profile)

        # FIX: Use queryset .update() to avoid triggering Appointment.save()
        # which would re-run _assign_doctor() and create recursive save risk.
        Appointment.objects.filter(pk=vital_request.appointment_id).update(status='IN_REVIEW')

        logger.info(
            'Vital request created by doctor %s — assigned to: %s',
            self.request.user.profile.fullname,
            vital_request.assigned_to,
        )


class VitalRequestListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = VitalRequestSerializer

    def get_queryset(self):
        profile = self.request.user.profile
        if profile.role == 'NURSE':
            return VitalRequest.objects.filter(
                models.Q(assigned_to=profile) | models.Q(status='PENDING')
            ).order_by('-created_at')
        if profile.role == 'DOCTOR':
            return VitalRequest.objects.filter(requested_by=profile).order_by('-created_at')
        return VitalRequest.objects.all().order_by('-created_at')


# --------------- Nurse fills Vitals ---------------

class VitalsCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['NURSE']
    serializer_class = VitalsSerializer

    def perform_create(self, serializer):
        vitals = serializer.save(nurse=self.request.user.profile)
        vital_request = vitals.vital_request

        # FIX: .update() avoids triggering VitalRequest.save() side-effects.
        VitalRequest.objects.filter(pk=vital_request.pk).update(status='DONE')

        logger.info(
            'Vitals recorded for %s — BP: %s, Pulse: %s',
            vital_request.appointment.name,
            vitals.blood_pressure,
            vitals.pulse_rate,
        )


# --------------- Lab scientist fills LabResult ---------------

class LabResultCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['LAB']
    serializer_class = LabResultSerializer

    def perform_create(self, serializer):
        lab_result   = serializer.save(lab_scientist=self.request.user.profile)
        test_request = lab_result.test_request

        logger.info(
            'Lab result submitted for %s — Test: %s, Result: %s',
            test_request.appointment.name,
            lab_result.test_name,
            lab_result.result,
        )

        requested_tests = {t.strip() for t in test_request.tests.split(',')}
        completed_tests = set(test_request.lab_results.values_list('test_name', flat=True))

        if requested_tests.issubset(completed_tests):
            # FIX: .update() instead of test_request.save() to avoid side-effects.
            TestRequest.objects.filter(pk=test_request.pk).update(status='DONE')
            logger.info('All tests completed for %s', test_request.appointment.name)


# --------------- Doctor creates Medical Report ---------------

class MedicalReportCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['DOCTOR']
    serializer_class = MedicalReportSerializer

    def perform_create(self, serializer):
        serializer.save(doctor=self.request.user.profile)
        # Appointment status → COMPLETED is handled inside MedicalReport.save()


class StaffListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_queryset(self):
        return Profile.objects.filter(
            Q(role='DOCTOR') | Q(role='NURSE') | Q(role='LAB'),
            user__is_active=True,
        )


# ==================== BLOG VIEWS ====================
class BlogPostLatestView(generics.ListAPIView, CacheMixin):
    serializer_class = BlogPostListSerializer
    permission_classes = [permissions.AllowAny]
    cache_timeout = 300
    cache_key_prefix = 'blog_latest'

    def get_queryset(self):
        limit = self.request.query_params.get('limit', 6)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 6

        return BlogPost.objects.filter(published=True).select_related(
            'author'
        ).only(
            'id', 'title', 'slug', 'description', 'featured_image',
            'image_1', 'image_2', 'published_date', 'created_at',
            'author__fullname', 'author__role',
        ).order_by('-published_date', '-created_at')[:limit]

    @method_decorator(cache_page(300))
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BlogPostListCreateView(generics.ListCreateAPIView, CacheMixin):
    parser_classes   = [MultiPartParser, FormParser, JSONParser]
    cache_timeout    = 300
    cache_key_prefix = 'blog_list'

    def get_queryset(self):
        if self.request.method == 'GET':
            return BlogPost.objects.filter(published=True).select_related(
                'author'
            ).only(
                'id', 'title', 'slug', 'description', 'featured_image',
                'image_1', 'image_2', 'published', 'published_date',
                'created_at', 'author__fullname', 'author__role',
            ).order_by('-published_date', '-created_at')
        return BlogPost.objects.all()

    def get_serializer_class(self):
        return BlogPostCreateSerializer if self.request.method == 'POST' else BlogPostListSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsRole()]
        return [permissions.AllowAny()]
    @method_decorator(cache_page(300))
    @method_decorator(vary_on_headers('Authorization'))
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def perform_create(self, serializer):
        profile = self.request.user.profile
        if profile.role != 'ADMIN':
            raise PermissionDenied('Only admins can create blog posts.')

        blog_post = serializer.save(author=profile)

        # FIX: safe_cache_delete_pattern — won't crash on LocMemCache.
        safe_cache_delete_pattern('blog_list:*')

        from .tasks import process_blog_images
        transaction.on_commit(lambda: process_blog_images.delay(blog_post.id))
        logger.info('Blog post %d created by %s', blog_post.pk, profile.fullname)


class BlogPostRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView, CacheMixin):
    queryset         = BlogPost.objects.all().select_related('author')
    parser_classes   = [MultiPartParser, FormParser, JSONParser]
    lookup_field     = 'slug'
    cache_timeout    = 600
    cache_key_prefix = 'blog_detail'

    def get_serializer_class(self):
        return BlogPostCreateSerializer if self.request.method != 'GET' else BlogPostSerializer

    # FIX: Double-caching removed — same rationale as BlogPostListCreateView.
    @method_decorator(cache_page(600))
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def perform_update(self, serializer):
        profile = self.request.user.profile
        if profile.role != 'ADMIN':
            raise PermissionDenied('Only admins can update blog posts.')

        instance = serializer.save()

        safe_cache_delete_pattern('blog_detail:*')
        safe_cache_delete_pattern('blog_list:*')

        from .tasks import process_blog_images
        transaction.on_commit(lambda: process_blog_images.delay(instance.id))
        logger.info('Blog post %d updated by %s', instance.pk, profile.fullname)

    def perform_destroy(self, instance):
        profile = self.request.user.profile
        if profile.role != 'ADMIN':
            raise PermissionDenied('Only admins can delete blog posts.')

        safe_cache_delete_pattern('blog_detail:*')
        safe_cache_delete_pattern('blog_list:*')
        safe_cache_delete_pattern('blog_latest:*')
        logger.info('Blog post %d deleted by %s', instance.pk, profile.fullname)
        instance.delete()


class BlogPostLatestView(generics.ListAPIView, CacheMixin):
    serializer_class   = BlogPostListSerializer
    permission_classes = [permissions.AllowAny]
    cache_timeout      = 300
    cache_key_prefix   = 'blog_latest'

    def get_queryset(self):
        limit = self.request.query_params.get('limit', 6)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 6

        return BlogPost.objects.filter(published=True).select_related(
            'author'
        ).only(
            'id', 'title', 'slug', 'description', 'featured_image',
            'image_1', 'image_2', 'published_date', 'created_at',
            'author__fullname', 'author__role',
        ).order_by('-published_date', '-created_at')[:limit]

    # FIX: Double-caching removed — same rationale as BlogPostListCreateView.
    @method_decorator(cache_page(300))
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BlogPostSearchView(generics.ListAPIView):
    serializer_class   = BlogPostListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        queryset     = BlogPost.objects.filter(published=True)
        search_query = self.request.query_params.get('q', None)
        if search_query:
            queryset = queryset.filter(
                Q(title__icontains=search_query) |
                Q(description__icontains=search_query) |
                Q(content__icontains=search_query)
            )
        return queryset.order_by('-created_at')


class AdminBlogPostListView(generics.ListAPIView):
    serializer_class   = BlogPostListSerializer
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles      = ['ADMIN']

    def get_queryset(self):
        return BlogPost.objects.all().order_by('-created_at')


class BlogPostByAuthorView(generics.ListAPIView):
    serializer_class   = BlogPostListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return BlogPost.objects.filter(
            author_id=self.kwargs['author_id'],
            published=True,
        ).order_by('-published_date', '-created_at')


class BlogStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles      = ['ADMIN']

    def get(self, request):
        total_posts     = BlogPost.objects.count()
        published_posts = BlogPost.objects.filter(published=True).count()
        draft_posts     = total_posts - published_posts
        posts_with_toc  = BlogPost.objects.filter(enable_toc=True).count()

        return Response({
            'total_posts':     total_posts,
            'published_posts': published_posts,
            'draft_posts':     draft_posts,
            'posts_with_toc':  posts_with_toc,
            'toc_usage_rate':  (posts_with_toc / total_posts * 100) if total_posts > 0 else 0,
        })