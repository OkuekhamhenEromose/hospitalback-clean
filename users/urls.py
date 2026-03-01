# users/urls.py - SIMPLIFIED
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenRefreshView,
    TokenVerifyView,
)
from . import views

urlpatterns = [
    # JWT Authentication
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    
    # Unified endpoints
    path('register/', views.RegistrationView.as_view(), name='register'),
    path('login/', views.UnifiedLoginView.as_view(), name='login'),

    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('update-profile/', views.UpdateProfileView.as_view(), name='update-profile'),
    
    # Keep social auth URLs for compatibility
    path('', include('social_django.urls', namespace='social')),
    
    # Compatibility URLs (can be removed later)
    path('social-auth-success/', views.SocialAuthSuccessView.as_view(), name='social-auth-success'),
    path('social-auth-error/', views.SocialAuthErrorView.as_view(), name='social-auth-error'),
]