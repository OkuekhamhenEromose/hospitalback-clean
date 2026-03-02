# hospital/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AppointmentCreateView, AppointmentListView, AppointmentDetailView,
    AssignmentViewSet, AppointmentAssignmentsView,
    AvailableStaffView,   # ← was never registered — causes the 404 in logs
    AssignStaffView, PatientListView,
    VitalRequestCreateView, VitalRequestListView,
    VitalsCreateView, LabResultCreateView, MedicalReportCreateView,
    StaffListView,
    BlogPostLatestView, BlogPostListCreateView,
    BlogPostRetrieveUpdateDestroyView, BlogPostSearchView,
    AdminBlogPostListView, BlogPostByAuthorView, BlogStatsView,
)

router = DefaultRouter()
router.register(r'assignments', AssignmentViewSet, basename='assignment')

urlpatterns = [
    # ── Appointments ──────────────────────────────────────────────────────────
    path('appointments/',          AppointmentListView.as_view(),   name='appointment-list'),
    path('appointments/create/',   AppointmentCreateView.as_view(), name='appointment-create'),
    path('appointments/<int:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),

    # ── Assignments ───────────────────────────────────────────────────────────
    # FIX: These named paths MUST come before include(router.urls).
    # The router registers /assignments/{pk}/ which would shadow these if it
    # came first — Django matches patterns in order.
    path('assignments/available-staff/',
         AvailableStaffView.as_view(), name='available-staff'),
    path('assignments/assign-staff/',
         AssignStaffView.as_view(), name='assign-staff'),
    path('assignments/appointment/<int:appointment_id>/',
         AppointmentAssignmentsView.as_view(), name='appointment-assignments'),
    path('', include(router.urls)),   # ViewSet: GET/POST /assignments/, GET/PUT/DELETE /assignments/{id}/

    # ── Staff / Patients ──────────────────────────────────────────────────────
    path('staff/',    StaffListView.as_view(),   name='staff-list'),
    path('patients/', PatientListView.as_view(), name='patient-list'),

    # ── Clinical ──────────────────────────────────────────────────────────────
    path('vital-requests/',        VitalRequestListView.as_view(),   name='vital-request-list'),
    path('vital-requests/create/', VitalRequestCreateView.as_view(), name='vital-request-create'),
    path('vitals/create/',         VitalsCreateView.as_view(),       name='vitals-create'),
    path('lab-results/create/',    LabResultCreateView.as_view(),    name='lab-result-create'),
    path('medical-reports/create/', MedicalReportCreateView.as_view(), name='medical-report-create'),

    # ── Blog ──────────────────────────────────────────────────────────────────
    # Exact paths MUST come before the slug catch-all or 'latest'/'search'/
    # 'admin/...' would be treated as slug values and return 404.
    path('blog/latest/',                    BlogPostLatestView.as_view(),              name='blog-latest'),
    path('blog/search/',                    BlogPostSearchView.as_view(),              name='blog-search'),
    path('blog/admin/stats/',               BlogStatsView.as_view(),                   name='blog-stats'),
    path('blog/admin/all/',                 AdminBlogPostListView.as_view(),           name='blog-admin-all'),
    path('blog/author/<int:author_id>/',    BlogPostByAuthorView.as_view(),            name='blog-by-author'),
    path('blog/',                           BlogPostListCreateView.as_view(),          name='blog-list-create'),
    path('blog/<slug:slug>/',               BlogPostRetrieveUpdateDestroyView.as_view(), name='blog-detail'),
]