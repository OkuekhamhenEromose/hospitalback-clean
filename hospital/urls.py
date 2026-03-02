# hospital/urls.py
#
# ══════════════════════════════════════════════════════════════════════════════
# FIX: /api/hospital/blog/latest/ was returning 404
# ══════════════════════════════════════════════════════════════════════════════
#
# Django's WARNING log at 07:26:15 showed:
#   "Not Found: /api/hospital/blog/latest/"
#
# That is a URL-resolver 404 (Django never matched the path to a view), not
# a model-lookup 404.  The view BlogPostLatestView existed in views.py; it just
# was never wired up in this URL conf.
#
# CRITICAL ORDER NOTE
# ────────────────────
# path('blog/latest/', ...) and path('blog/search/', ...) MUST appear BEFORE
# path('blog/<slug:slug>/', ...). Django tests patterns top-to-bottom; if the
# slug pattern comes first, the literal strings "latest" and "search" match
# the <slug> converter and get dispatched to the detail view, which then
# returns 404 because no post has that slug.
# ══════════════════════════════════════════════════════════════════════════════

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    # Appointments
    AppointmentCreateView,
    AppointmentListView,
    AppointmentDetailView,

    # Assignments
    AssignmentViewSet,
    AssignStaffView,
    AvailableStaffView,
    AppointmentAssignmentsView,
    PatientListView,

    # Vitals
    VitalRequestCreateView,
    VitalRequestListView,
    VitalsCreateView,

    # Lab
    LabResultCreateView,

    # Medical
    MedicalReportCreateView,

    # Staff
    StaffListView,

    # Blog  ← ORDER MATTERS: specific before parameterised
    BlogPostLatestView,          # /blog/latest/
    BlogPostSearchView,          # /blog/search/
    BlogStatsView,               # /blog/admin/stats/
    AdminBlogPostListView,       # /blog/admin/all/
    BlogPostListCreateView,      # /blog/
    BlogPostRetrieveUpdateDestroyView,  # /blog/<slug>/
    BlogPostByAuthorView,        # /blog/author/<author_id>/
)

router = DefaultRouter()
router.register(r'assignments', AssignmentViewSet, basename='assignment')

urlpatterns = [
    # ── Assignments router ─────────────────────────────────────────────────
    path('', include(router.urls)),

    # ── Appointments ───────────────────────────────────────────────────────
    path('appointments/create/',AppointmentCreateView.as_view(),  name='appointment-create'),
    path('appointments/',AppointmentListView.as_view(),    name='appointment-list'),
    path('appointments/<int:pk>/', AppointmentDetailView.as_view(), name='appointment-detail'),

    # ── Staff assignment helpers ────────────────────────────────────────────
    path('assignments/assign-staff/',AssignStaffView.as_view(),name='assign-staff'),
    path('assignments/available-staff/',            AvailableStaffView.as_view(),name='available-staff'),
    path('assignments/appointment/<int:appointment_id>/', AppointmentAssignmentsView.as_view(), name='appointment-assignments'),

    # ── Vital requests ──────────────────────────────────────────────────────
    path('vital-requests/create/', VitalRequestCreateView.as_view(), name='vital-request-create'),
    path('vital-requests/',        VitalRequestListView.as_view(),   name='vital-request-list'),

    # ── Vitals ──────────────────────────────────────────────────────────────
    path('vitals/create/', VitalsCreateView.as_view(), name='vitals-create'),

    # ── Lab results ─────────────────────────────────────────────────────────
    path('lab-results/create/', LabResultCreateView.as_view(), name='lab-result-create'),

    # ── Medical reports ─────────────────────────────────────────────────────
    path('medical-reports/create/', MedicalReportCreateView.as_view(), name='medical-report-create'),

    # ── Patients / staff ────────────────────────────────────────────────────
    path('patients/', PatientListView.as_view(), name='patient-list'),
    path('staff/',    StaffListView.as_view(),   name='staff-list'),
    #
    path('blog/latest/',        BlogPostLatestView.as_view(),       name='blog-latest'),
    path('blog/search/',        BlogPostSearchView.as_view(),        name='blog-search'),
    path('blog/admin/stats/',   BlogStatsView.as_view(),            name='blog-stats'),
    path('blog/admin/all/',     AdminBlogPostListView.as_view(),    name='blog-admin-all'),
    path('blog/author/<int:author_id>/', BlogPostByAuthorView.as_view(), name='blog-by-author'),

    # ── Blog list + create (must come after fixed paths) ───────────────────
    path('blog/',               BlogPostListCreateView.as_view(),           name='blog-list-create'),

    # ── Blog detail / update / delete — parameterised LAST ─────────────────
    path('blog/<slug:slug>/',   BlogPostRetrieveUpdateDestroyView.as_view(), name='blog-detail'),
]