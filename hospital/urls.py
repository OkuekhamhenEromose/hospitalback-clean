# hospital/urls.py - COMPLETE WORKING VERSION
from django.urls import path
from . import views

app_name = 'hospital'

urlpatterns = [
    # Appointment URLs
    path('appointments/', views.AppointmentListView.as_view(), name='appointment-list'),
    path('appointments/create/', views.AppointmentCreateView.as_view(), name='appointment-create'),
    path('appointments/<int:pk>/', views.AppointmentDetailView.as_view(), name='appointment-detail'),
    
    # Assignment URLs
    path('assignments/', views.AssignmentViewSet.as_view({'get': 'list', 'post': 'create'}), name='assignment-list'),
    path('assignments/<int:pk>/', views.AssignmentViewSet.as_view({'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'}), name='assignment-detail'),
    path('assignments/appointment/<int:appointment_id>/', views.AppointmentAssignmentsView.as_view(), name='appointment-assignments'),
    path('assignments/available-staff/', views.AvailableStaffView.as_view(), name='available-staff'),
    path('assignments/assign-staff/', views.AssignStaffView.as_view(), name='assign-staff'),
    
    # Patient URLs
    path('patients/', views.PatientListView.as_view(), name='patient-list'),
    
    # Vital Request URLs
    path('vital-requests/', views.VitalRequestListView.as_view(), name='vital-request-list'),
    path('vital-requests/create/', views.VitalRequestCreateView.as_view(), name='vital-request-create'),
    
    # Vitals URLs
    path('vitals/create/', views.VitalsCreateView.as_view(), name='vitals-create'),
    
    # Lab Result URLs
    path('lab-results/create/', views.LabResultCreateView.as_view(), name='lab-result-create'),
    
    # Medical Report URLs
    path('medical-reports/create/', views.MedicalReportCreateView.as_view(), name='medical-report-create'),
    
    # Staff URLs
    path('staff/', views.StaffListView.as_view(), name='staff-list'),
    
    # Blog URLs - UPDATED WITH CORRECT VIEW NAMES
    path('blog/', views.BlogPostListCreateView.as_view(), name='blog-list-create'),
    path('blog/<slug:slug>/', views.BlogPostRetrieveUpdateDestroyView.as_view(), name='blog-detail'),
    path('blog/search/', views.BlogPostSearchView.as_view(), name='blog-search'),
    path('blog/latest/', views.BlogPostLatestView.as_view(), name='blog-latest'),
    path('blog/author/<int:author_id>/', views.BlogPostByAuthorView.as_view(), name='blog-by-author'),
    
    # Admin blog endpoints
    path('blog/admin/all/', views.AdminBlogPostListView.as_view(), name='admin-blog-all'),
    path('blog/admin/stats/', views.BlogStatsView.as_view(), name='blog-stats'),
]