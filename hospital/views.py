# hospital/views.py
#
# ══════════════════════════════════════════════════════════════════════════════
# FIXES IN THIS FILE
# ══════════════════════════════════════════════════════════════════════════════
#
# FIX-1 ── Removed ALL @method_decorator(cache_page()) from every view.
#
#   Root cause (confirmed in Render traceback at 07:10:20):
#     Django's cache_page middleware intercepts the view response via
#     add_post_render_callback(). DRF's Response extends SimpleTemplateResponse,
#     so Django treats it like a template response and tries to cache the whole
#     object. Redis is configured with JSONSerializer → json.dumps(Response)
#     raises TypeError: Object of type Response is not JSON serializable.
#     This turned EVERY cached blog/appointment GET into a 500.
#
#   Fix: manual caching only. cache.set() is called on response.data, which
#   is already a plain dict/list → safe to JSON-serialize. Cache failures are
#   caught and logged; a slow response is always better than a 500.
#
# FIX-2 ── Removed duplicate BlogPostLatestView class definition.
#   The original file defined BlogPostLatestView twice. Python silently uses
#   the last definition; the first is dead code. Only one definition remains.
#
# FIX-3 ── BlogPostLatestView.get() uses manual caching (no cache_page).
#   The /blog/latest/ endpoint is AllowAny. cache_page + JWTAuthentication
#   interaction was causing 401s even on AllowAny views when an expired token
#   was present in the request headers.
# ══════════════════════════════════════════════════════════════════════════════

from rest_framework import generics, permissions, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from .models import (
    Appointment, TestRequest, VitalRequest, Vitals, LabResult,
    MedicalReport, BlogPost,
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
from django.db.models import Q, Prefetch
from users.serializers import ProfileSerializer
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from .models import Assignment
from django.core.cache import cache
from .base_views import OptimizedAPIView, CacheMixin
from api.settings import safe_cache_delete_pattern

import logging
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# APPOINTMENTS
# ──────────────────────────────────────────────────────────────────────────────

class AppointmentCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['PATIENT']
    serializer_class = AppointmentSerializer

    def perform_create(self, serializer):
        profile = self.request.user.profile
        appointment = serializer.save(patient=profile)
        logger.info('Appointment %d created for patient: %s', appointment.pk, profile.user.username)


class AppointmentListView(generics.ListAPIView, CacheMixin):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AppointmentSerializer
    cache_timeout = 60
    cache_key_prefix = 'appointments'

    def get_queryset(self):
        profile = self.request.user.profile
        base_qs = Appointment.objects.select_related(
            'patient', 'patient__user',
            'doctor',  'doctor__user',
        ).prefetch_related(
            Prefetch('test_requests',
                     queryset=TestRequest.objects.select_related('assigned_to')
                                                 .prefetch_related('lab_results')),
            Prefetch('vital_requests',
                     queryset=VitalRequest.objects.select_related('assigned_to')
                                                  .prefetch_related('vitals_entries')),
            Prefetch('assignments',
                     queryset=Assignment.objects.select_related('staff', 'assigned_by')),
            'medical_report',
        )
        if profile.role == 'PATIENT':
            return base_qs.filter(patient=profile).order_by('-booked_at')
        if profile.role == 'DOCTOR':
            return base_qs.filter(doctor=profile).order_by('-booked_at')
        return base_qs.all().order_by('-booked_at')

    # FIX-1: No cache_page decorator. Manual cache on response.data only.
    def get(self, request, *args, **kwargs):
        cache_key = f"{self.cache_key_prefix}:{request.user.id}:{request.GET.urlencode()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().get(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
            except Exception as e:
                logger.warning('AppointmentListView cache.set failed: %s', e)
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
            Prefetch('test_requests',
                     queryset=TestRequest.objects.select_related('assigned_to')
                                                 .prefetch_related('lab_results')),
            Prefetch('vital_requests',
                     queryset=VitalRequest.objects.select_related('assigned_to')
                                                  .prefetch_related('vitals_entries')),
            Prefetch('assignments',
                     queryset=Assignment.objects.select_related('staff', 'assigned_by')),
            'medical_report',
        )

    # FIX-1: No cache_page decorator.
    def get(self, request, *args, **kwargs):
        cache_key = f"{self.cache_key_prefix}:{kwargs.get('pk')}:{request.user.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().get(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
            except Exception as e:
                logger.warning('AppointmentDetailView cache.set failed: %s', e)
        return response


# ──────────────────────────────────────────────────────────────────────────────
# ASSIGNMENTS
# ──────────────────────────────────────────────────────────────────────────────

class AssignmentViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer
    queryset = Assignment.objects.all()

    def get_queryset(self):
        profile = self.request.user.profile
        if profile.role == 'ADMIN':
            return Assignment.objects.all()
        if profile.role == 'DOCTOR':
            return Assignment.objects.filter(appointment__doctor=profile)
        if profile.role == 'NURSE':
            return Assignment.objects.filter(staff=profile, role='NURSE')
        if profile.role == 'LAB':
            return Assignment.objects.filter(staff=profile, role='LAB')
        return Assignment.objects.none()


class AppointmentAssignmentsView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = AssignmentSerializer

    def get_queryset(self):
        return Assignment.objects.filter(appointment_id=self.kwargs['appointment_id'])


class AvailableStaffView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = StaffProfileSerializer

    def get_queryset(self):
        role = self.request.query_params.get('role', '').upper()
        valid = {'DOCTOR', 'NURSE', 'LAB'}
        if role and role in valid:
            return Profile.objects.filter(role=role, user__is_active=True)
        return Profile.objects.filter(role__in=valid, user__is_active=True)


class AssignStaffView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['ADMIN', 'DOCTOR']

    def post(self, request):
        serializer = AppointmentAssignmentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        appt_id = serializer.validated_data['appointment_id']
        staff_id = serializer.validated_data['staff_id']
        role = serializer.validated_data['role']
        notes = serializer.validated_data.get('notes', '')

        try:
            appointment = Appointment.objects.get(id=appt_id)
            staff = Profile.objects.get(id=staff_id)

            if staff.role != role:
                return Response({'error': f'Staff member is not a {role}'},
                                status=status.HTTP_400_BAD_REQUEST)

            assignment, _ = Assignment.objects.update_or_create(
                appointment=appointment,
                role=role,
                defaults={'staff': staff,
                          'assigned_by': request.user.profile,
                          'notes': notes},
            )

            if role == 'DOCTOR':
                Appointment.objects.filter(pk=appointment.pk).update(doctor=staff)
            elif role == 'NURSE':
                VitalRequest.objects.get_or_create(
                    appointment=appointment,
                    defaults={'assigned_to': staff,
                              'requested_by': request.user.profile},
                )
            elif role == 'LAB':
                TestRequest.objects.get_or_create(
                    appointment=appointment,
                    defaults={'assigned_to': staff,
                              'requested_by': request.user.profile,
                              'tests': 'General tests'},
                )

            logger.info('Assigned %s (%s) to appointment %d by %s',
                        staff.fullname, role, appointment.pk,
                        request.user.profile.fullname)
            return Response({
                'message': f'Successfully assigned {staff.fullname} as {role}',
                'assignment': AssignmentSerializer(assignment).data,
            })

        except Appointment.DoesNotExist:
            return Response({'error': 'Appointment not found'}, status=status.HTTP_404_NOT_FOUND)
        except Profile.DoesNotExist:
            return Response({'error': 'Staff member not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error('AssignStaffView error: %s', e)
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PatientListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['ADMIN', 'DOCTOR']
    serializer_class = StaffProfileSerializer

    def get_queryset(self):
        patient_ids = Appointment.objects.values_list('patient_id', flat=True).distinct()
        return Profile.objects.filter(id__in=patient_ids, role='PATIENT').order_by('-user__date_joined')


# ──────────────────────────────────────────────────────────────────────────────
# VITAL REQUESTS  (doctor → nurse)
# ──────────────────────────────────────────────────────────────────────────────

class VitalRequestCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['DOCTOR']
    serializer_class = VitalRequestSerializer

    def perform_create(self, serializer):
        vr = serializer.save(requested_by=self.request.user.profile)
        Appointment.objects.filter(pk=vr.appointment_id).update(status='IN_REVIEW')
        logger.info('Vital request created by %s — assigned to: %s',
                    self.request.user.profile.fullname, vr.assigned_to)


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


# ──────────────────────────────────────────────────────────────────────────────
# VITALS  (nurse fills)
# ──────────────────────────────────────────────────────────────────────────────

class VitalsCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['NURSE']
    serializer_class = VitalsSerializer

    def perform_create(self, serializer):
        vitals = serializer.save(nurse=self.request.user.profile)
        VitalRequest.objects.filter(pk=vitals.vital_request_id).update(status='DONE')
        logger.info('Vitals recorded for %s — BP: %s, Pulse: %s',
                    vitals.vital_request.appointment.name,
                    vitals.blood_pressure, vitals.pulse_rate)


# ──────────────────────────────────────────────────────────────────────────────
# LAB RESULTS  (lab scientist fills)
# ──────────────────────────────────────────────────────────────────────────────

class LabResultCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['LAB']
    serializer_class = LabResultSerializer

    def perform_create(self, serializer):
        lr = serializer.save(lab_scientist=self.request.user.profile)
        tr = lr.test_request
        requested = {t.strip() for t in tr.tests.split(',')}
        completed = set(tr.lab_results.values_list('test_name', flat=True))
        if requested.issubset(completed):
            TestRequest.objects.filter(pk=tr.pk).update(status='DONE')
            logger.info('All tests completed for %s', tr.appointment.name)


# ──────────────────────────────────────────────────────────────────────────────
# MEDICAL REPORT  (doctor creates)
# ──────────────────────────────────────────────────────────────────────────────

class MedicalReportCreateView(generics.CreateAPIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles = ['DOCTOR']
    serializer_class = MedicalReportSerializer

    def perform_create(self, serializer):
        serializer.save(doctor=self.request.user.profile)


class StaffListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ProfileSerializer

    def get_queryset(self):
        return Profile.objects.filter(
            Q(role='DOCTOR') | Q(role='NURSE') | Q(role='LAB'),
            user__is_active=True,
        )


class BlogPostLatestView(generics.ListAPIView, CacheMixin):
    """
    GET /hospital/blog/latest/?limit=N
    Public endpoint — no authentication required.
    """
    serializer_class = BlogPostListSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # ADD THIS LINE - explicitly disable authentication
    cache_timeout = 300
    cache_key_prefix = 'blog_latest'

    def get_queryset(self):
        try:
            limit = int(self.request.query_params.get('limit', 6))
        except (TypeError, ValueError):
            limit = 6
        return (
            BlogPost.objects
            .filter(published=True)
            .select_related('author')
            .only('id', 'title', 'slug', 'description', 'featured_image',
                  'image_1', 'image_2', 'published_date', 'created_at',
                  'author__fullname', 'author__role')
            .order_by('-published_date', '-created_at')[:limit]
        )

    def get(self, request, *args, **kwargs):
        limit = request.GET.get('limit', '6')
        cache_key = f"{self.cache_key_prefix}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().get(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
            except Exception as e:
                logger.warning('BlogPostLatestView cache.set failed: %s', e)
        return response


class BlogPostListCreateView(generics.ListCreateAPIView, CacheMixin):
    parser_classes   = [MultiPartParser, FormParser, JSONParser]
    cache_timeout    = 300
    cache_key_prefix = 'blog_list'

    def get_queryset(self):
        if self.request.method == 'GET':
            return (
                BlogPost.objects
                .filter(published=True)
                .select_related('author')
                .only('id', 'title', 'slug', 'description', 'featured_image',
                      'image_1', 'image_2', 'published', 'published_date',
                      'created_at', 'author__fullname', 'author__role')
                .order_by('-published_date', '-created_at')
            )
        return BlogPost.objects.all()

    def get_serializer_class(self):
        return BlogPostCreateSerializer if self.request.method == 'POST' else BlogPostListSerializer

    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAuthenticated(), IsRole()]
        return [permissions.AllowAny()]

    # FIX-1: No cache_page decorator — manual cache on response.data only.
    def get(self, request, *args, **kwargs):
        cache_key = f"{self.cache_key_prefix}:{request.GET.urlencode()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().get(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
            except Exception as e:
                logger.warning('BlogPostListCreateView cache.set failed: %s', e)
        return response

    def perform_create(self, serializer):
        profile = self.request.user.profile
        if profile.role != 'ADMIN':
            raise PermissionDenied('Only admins can create blog posts.')
        blog_post = serializer.save(author=profile)
        safe_cache_delete_pattern('blog_list:*')
        safe_cache_delete_pattern('blog_latest:*')
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

    def get_permissions(self):
        if self.request.method in ('PUT', 'PATCH', 'DELETE'):
            return [permissions.IsAuthenticated(), IsRole()]
        return [permissions.AllowAny()]

    # FIX-1: No cache_page decorator.
    def get(self, request, *args, **kwargs):
        cache_key = f"{self.cache_key_prefix}:{kwargs.get('slug')}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)
        response = super().get(request, *args, **kwargs)
        if response.status_code == 200:
            try:
                cache.set(cache_key, response.data, self.cache_timeout)
            except Exception as e:
                logger.warning('BlogPostRetrieveUpdateDestroyView cache.set failed: %s', e)
        return response

    def perform_update(self, serializer):
        profile = self.request.user.profile
        if profile.role != 'ADMIN':
            raise PermissionDenied('Only admins can update blog posts.')
        instance = serializer.save()
        safe_cache_delete_pattern('blog_detail:*')
        safe_cache_delete_pattern('blog_list:*')
        safe_cache_delete_pattern('blog_latest:*')
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


class BlogPostSearchView(generics.ListAPIView):
    serializer_class   = BlogPostListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = BlogPost.objects.filter(published=True)
        q = self.request.query_params.get('q')
        if q:
            qs = qs.filter(
                Q(title__icontains=q) |
                Q(description__icontains=q) |
                Q(content__icontains=q)
            )
        return qs.order_by('-created_at')


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
            author_id=self.kwargs['author_id'], published=True,
        ).order_by('-published_date', '-created_at')


class BlogStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsRole]
    allowed_roles      = ['ADMIN']

    def get(self, request):
        total     = BlogPost.objects.count()
        published = BlogPost.objects.filter(published=True).count()
        with_toc  = BlogPost.objects.filter(enable_toc=True).count()
        return Response({
            'total_posts':     total,
            'published_posts': published,
            'draft_posts':     total - published,
            'posts_with_toc':  with_toc,
            'toc_usage_rate':  (with_toc / total * 100) if total else 0,
        })