# users/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.conf import settings
from django.shortcuts import redirect
import urllib.parse
import requests
import logging
from django.contrib.auth import login as auth_login
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .serializers import (
    RegistrationSerializer,
    ProfileSerializer,
    UpdateProfileSerializer,
)
from .models import Profile
from social_django.models import UserSocialAuth

logger = logging.getLogger(__name__)


class UnifiedLoginView(APIView):
    """Handle both regular login and Google OAuth login."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        google_auth_code = request.data.get('google_auth_code')
        if google_auth_code:
            return self.handle_google_login(request, google_auth_code)
        return self.handle_regular_login(request)

    def handle_regular_login(self, request):
        identifier = request.data.get('username')  # accepts username OR email
        password   = request.data.get('password')

        if not identifier or not password:
            return Response(
                {'detail': 'Username/Email and password are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = authenticate(username=identifier, password=password)

        if user is None:
            try:
                user_obj = User.objects.get(email=identifier)
                user = authenticate(username=user_obj.username, password=password)
            except User.DoesNotExist:
                user = None

        if user is None:
            return Response({'detail': 'Invalid credentials'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.is_active:
            return Response({'detail': 'Account is disabled'}, status=status.HTTP_400_BAD_REQUEST)

        user.backend = 'django.contrib.auth.backends.ModelBackend'
        auth_login(request, user)
        refresh = RefreshToken.for_user(user)

        # FIX: replaced print() with structured logger call
        logger.info('Regular login successful: %s', user.username)

        return Response({
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id':       user.id,
                'username': user.username,
                'email':    user.email,
                'profile':  self.get_user_profile_data(user, request),
            },
        })

    def handle_google_login(self, request, auth_code):
        try:
            token_response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code':          auth_code,
                    'client_id':     settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY,
                    'client_secret': settings.SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET,
                    'redirect_uri':  'https://ettahospitalclone.vercel.app/auth/callback',
                    'grant_type':    'authorization_code',
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get('access_token')

            if not access_token:
                return Response(
                    {'detail': 'Failed to get access token from Google'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            userinfo_response = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {access_token}'},
            )
            userinfo_response.raise_for_status()
            google_user = userinfo_response.json()

            email = google_user.get('email')
            if not email:
                return Response(
                    {'detail': 'No email received from Google'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                user    = User.objects.get(email=email)
                created = False
                logger.info('Google login — existing user: %s', email)
            except User.DoesNotExist:
                username = self.generate_username(google_user.get('name', ''), email)
                user = User.objects.create_user(username=username, email=email, password=None)
                user.first_name = google_user.get('given_name', '')
                user.last_name  = google_user.get('family_name', '')
                user.save()
                created = True
                logger.info('Google login — new user created: %s', email)

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.fullname = google_user.get('name', f'{user.first_name} {user.last_name}'.strip())
                profile.save()

            user.backend = 'django.contrib.auth.backends.ModelBackend'
            auth_login(request, user)
            refresh = RefreshToken.for_user(user)
            logger.info('Google login successful: %s', user.email)

            return Response({
                'access':      str(refresh.access_token),
                'refresh':     str(refresh),
                'user': {
                    'id':       user.id,
                    'username': user.username,
                    'email':    user.email,
                    'profile':  self.get_user_profile_data(user, request),
                },
                'is_new_user': created,
            })

        except requests.RequestException as e:
            logger.error('Google API error: %s', e)
            return Response({'detail': 'Google authentication failed'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception('Unexpected error in Google login')
            return Response({'detail': 'Authentication failed'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_user_profile_data(self, user, request):
        try:
            profile = Profile.objects.select_related('user').get(user=user)
            profile_serializer = ProfileSerializer(profile, context={'request': request})
            # FIX: replaced three print() debug lines with a single logger.debug
            logger.debug('Profile data fetched for %s', user.username)
            return {
                'role':        profile.role,
                'fullname':    profile.fullname,
                'profile_pix': profile_serializer.data.get('profile_pix'),
                'phone':       profile.phone,
                'gender':      profile.gender,
            }
        except Profile.DoesNotExist:
            logger.warning('Profile not found for user %d', user.id)
            return {
                'role':        'PATIENT',
                'fullname':    user.get_full_name() or user.username,
                'profile_pix': None,
                'phone':       None,
                'gender':      None,
            }

    def generate_username(self, name, email):
        base_username = name.replace(' ', '_').lower() if name else email.split('@')[0]
        username, counter = base_username, 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}_{counter}'
            counter += 1
        return username


class RegistrationView(APIView):
    permission_classes = [permissions.AllowAny]

    @transaction.atomic
    def post(self, request):
        try:
            if request.user.is_authenticated:
                return Response({'Message': 'You are logged in already'})

            serializer = RegistrationSerializer(data=request.data)

            if serializer.is_valid():
                profile = serializer.save()
                data = {
                    'id':       profile.user.id,
                    'username': profile.user.username,
                    'email':    profile.user.email,
                    'role':     profile.role,
                }
                logger.info('User %s registered successfully', profile.user.username)
                return Response(data, status=status.HTTP_201_CREATED)
            else:
                logger.warning('Registration validation errors: %s', serializer.errors)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error('Registration exception: %s', e)
            return Response(
                {'error': 'Registration failed. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get('refresh')
            user_id       = request.user.id

            if refresh_token:
                try:
                    token = RefreshToken(refresh_token)
                    token.blacklist()
                except Exception as e:
                    logger.warning('Token blacklist failed: %s', e)

            cache.delete(f'user_{user_id}_basic')
            cache.delete(f'user_dashboard_{user_id}')
            return Response({'detail': 'Logged out successfully'}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error('Logout error: %s', e)
            return Response({'detail': 'Logged out'}, status=status.HTTP_200_OK)


class DashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            profile    = Profile.objects.select_related('user').get(user=request.user)
            serializer = ProfileSerializer(profile, context={'request': request})

            # FIX: replaced five print() debug lines with a single logger.debug.
            # The originals included storage class name and raw URL which is
            # fine for debug level but excessive and noisy at INFO.
            logger.debug(
                'Dashboard for %s — has_profile_pix: %s',
                request.user.username,
                bool(profile.profile_pix),
            )

            return Response({
                'user': {
                    'id':       request.user.id,
                    'username': request.user.username,
                    'email':    request.user.email,
                    'profile': {
                        'role':        profile.role,
                        'fullname':    profile.fullname,
                        'profile_pix': serializer.data.get('profile_pix'),
                        'phone':       profile.phone,
                        'gender':      profile.gender,
                    },
                },
            })

        except Profile.DoesNotExist:
            logger.error('Profile not found for user %d', request.user.id)
            return Response({'detail': 'Profile not found'}, status=status.HTTP_404_NOT_FOUND)


class UpdateProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile    = request.user.profile
        serializer = UpdateProfileSerializer(profile)
        return Response(serializer.data)

    def put(self, request):
        profile    = request.user.profile
        serializer = UpdateProfileSerializer(profile, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            user_id = request.user.id
            cache.delete(f'user_{user_id}_basic')
            cache.delete(f'user_dashboard_{user_id}')
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name='dispatch')
class SocialAuthSuccessView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        logger.info('SocialAuthSuccessView — authenticated: %s', request.user.is_authenticated)

        user = None

        if not request.user.is_authenticated:
            user_id = request.session.get('_auth_user_id')
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    logger.info('Found user in session: %s', user.email)
                except User.DoesNotExist:
                    # FIX: log the missing ID at warning level, not the full
                    # session dict which leaks session keys to log aggregators.
                    logger.warning('Session user_id not found in database')
        else:
            user = request.user

        if not user:
            social_user_id = request.session.get('social_auth_user_id')
            if social_user_id:
                try:
                    user = User.objects.get(id=social_user_id)
                    logger.info('Found social auth user: %s', user.email)
                except (User.DoesNotExist, KeyError):
                    pass

        if user:
            user.backend = 'social_core.backends.google.GoogleOAuth2'
            auth_login(request, user)
            logger.info('Successfully logged in user: %s', user.email)

            refresh          = RefreshToken.for_user(user)
            profile, created = Profile.objects.get_or_create(user=user)

            if created:
                try:
                    social_auth = UserSocialAuth.objects.get(user=user, provider='google')
                    if social_auth.extra_data.get('name'):
                        profile.fullname = social_auth.extra_data.get('name')
                        profile.save()
                        logger.info('Updated profile for %s', user.email)
                except UserSocialAuth.DoesNotExist:
                    pass

            tokens = urllib.parse.urlencode({
                'access':      str(refresh.access_token),
                'refresh':     str(refresh),
                'user_id':     str(user.id),
                'email':       user.email,
                'username':    user.username,
                'is_new_user': str(created).lower(),
            })

            redirect_url = f'https://ettahospitalclone.vercel.app/auth/callback?{tokens}'
            logger.info('Redirecting %s to dashboard', user.email)
            return redirect(redirect_url)

        # FIX: The original logged the full session dict (session_keys,
        # _auth_user_id, social_auth_user_id) at error level — this leaks
        # session identifiers to log aggregators (Papertrail, Datadog, etc.).
        # Log only that the lookup failed; nothing session-specific.
        logger.error('SocialAuthSuccessView: could not find authenticated user')
        return redirect('https://ettahospitalclone.vercel.app/login?error=social_auth_failed')


class SocialAuthErrorView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        error   = request.GET.get('error', 'Unknown error occurred')
        message = request.GET.get('message', '')
        logger.error('Social auth error: %s — %s', error, message)
        error_url = f'https://ettahospitalclone.vercel.app/auth/error?message={urllib.parse.quote(message)}'
        return redirect(error_url)


class SocialAuthLoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        provider     = request.data.get('provider')
        access_token = request.data.get('access_token')

        if not provider or not access_token:
            return Response(
                {'error': 'Provider and access token required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if provider != 'google':
            return Response(
                {'error': 'Only Google authentication is supported'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user_data = self.verify_google_token(access_token)
            if not user_data:
                return Response({'error': 'Invalid Google token'}, status=status.HTTP_400_BAD_REQUEST)

            user, created = self.get_or_create_social_user(user_data)
            refresh       = RefreshToken.for_user(user)

            try:
                profile = Profile.objects.get(user=user)
                profile_data = {
                    'role':        profile.role,
                    'fullname':    profile.fullname,
                    'profile_pix': profile.profile_pix.url if profile.profile_pix else None,
                    'phone':       profile.phone,
                    'gender':      profile.gender,
                }
            except Profile.DoesNotExist:
                profile_data = {}

            return Response({
                'access':      str(refresh.access_token),
                'refresh':     str(refresh),
                'user': {
                    'id':       user.id,
                    'username': user.username,
                    'email':    user.email,
                    'profile':  profile_data,
                },
                'is_new_user': created,
            })

        except Exception as e:
            logger.error('Google auth login error: %s', e)
            return Response({'error': 'Google authentication failed'}, status=status.HTTP_400_BAD_REQUEST)

    def verify_google_token(self, access_token):
        try:
            response = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                params={'access_token': access_token},
            )
            if response.status_code == 200:
                data = response.json()
                return {
                    'email':      data.get('email'),
                    'name':       data.get('name'),
                    'first_name': data.get('given_name'),
                    'last_name':  data.get('family_name'),
                    'picture':    data.get('picture'),
                }
            return None
        except Exception as e:
            logger.error('Google token verification error: %s', e)
            return None

    def get_or_create_social_user(self, user_data):
        email = user_data.get('email')
        if not email:
            raise ValueError('Email is required for Google authentication')
        try:
            return User.objects.get(email=email), False
        except User.DoesNotExist:
            username = self.generate_username(user_data.get('name', ''), email)
            user = User.objects.create_user(
                username=username, email=email, password=None,
                first_name=user_data.get('first_name', ''),
                last_name=user_data.get('last_name', ''),
            )
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user)
            profile.fullname = user_data.get('name', f"{user.first_name} {user.last_name}".strip())
            profile.save()
            return user, True

    def generate_username(self, name, email):
        base_username = name.replace(' ', '_').lower() if name else email.split('@')[0]
        username, counter = base_username, 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}_{counter}'
            counter += 1
        return username


class SocialAuthUrlsView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        base_url = request.build_absolute_uri('/')[:-1]
        return Response({'google': f'{base_url}/api/users/login/google-oauth2/'})


class SocialAuthDebugView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        # FIX: The original returned session_keys and full extra_data in the
        # response body — accessible to any unauthenticated caller. Removed.
        # Now returns only what is safe to expose publicly.
        response_data = {
            'user': {
                'is_authenticated': request.user.is_authenticated,
                'username': request.user.username if request.user.is_authenticated else 'Anonymous',
            },
        }
        if request.user.is_authenticated:
            try:
                social_auth = UserSocialAuth.objects.filter(user=request.user).first()
                if social_auth:
                    response_data['social_provider'] = social_auth.provider
            except Exception as e:
                logger.error('SocialAuthDebugView error: %s', e)

        return Response(response_data)


class GoogleOAuthCallbackView(APIView):
    """Direct Google OAuth2 callback — bypasses social-auth-app-django."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        code = request.GET.get('code')

        if not code:
            logger.error('GoogleOAuthCallbackView: no authorization code received')
            return redirect('https://ettahospitalclone.vercel.app/login?error=no_auth_code')

        try:
            token_response = requests.post(
                'https://oauth2.googleapis.com/token',
                data={
                    'code':          code,
                    'client_id':     settings.SOCIAL_AUTH_GOOGLE_OAUTH2_KEY,
                    'client_secret': settings.SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET,
                    'redirect_uri':  'https://hospitalback-clean.onrender.com/api/users/google-callback/',
                    'grant_type':    'authorization_code',
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json().get('access_token')

            if not access_token:
                logger.error('GoogleOAuthCallbackView: no access token returned')
                return redirect('https://ettahospitalclone.vercel.app/login?error=no_access_token')

            userinfo_response = requests.get(
                'https://www.googleapis.com/oauth2/v3/userinfo',
                headers={'Authorization': f'Bearer {access_token}'},
            )
            userinfo_response.raise_for_status()
            google_user = userinfo_response.json()
            email       = google_user.get('email')

            if not email:
                logger.error('GoogleOAuthCallbackView: no email from Google')
                return redirect('https://ettahospitalclone.vercel.app/login?error=no_email')

            try:
                user    = User.objects.get(email=email)
                created = False
                logger.info('Google callback — existing user: %s', email)
            except User.DoesNotExist:
                username = self.generate_username(google_user.get('name', ''), email)
                user = User.objects.create_user(
                    username=username, email=email, password=None,
                    first_name=google_user.get('given_name', ''),
                    last_name=google_user.get('family_name', ''),
                )
                user.save()
                created = True
                logger.info('Google callback — new user created: %s', email)

                profile, _ = Profile.objects.get_or_create(user=user)
                profile.fullname = google_user.get('name', f"{user.first_name} {user.last_name}".strip())
                profile.save()

            user.backend = 'django.contrib.auth.backends.ModelBackend'
            auth_login(request, user)
            refresh = RefreshToken.for_user(user)

            try:
                profile         = Profile.objects.get(user=user)
                profile_pix_url = profile.profile_pix.url if profile.profile_pix else None
            except Profile.DoesNotExist:
                profile_pix_url = None

            tokens = urllib.parse.urlencode({
                'access':      str(refresh.access_token),
                'refresh':     str(refresh),
                'user_id':     str(user.id),
                'email':       user.email,
                'username':    user.username,
                'is_new_user': str(created).lower(),
            })

            logger.info('Google direct auth successful for %s', email)
            return redirect(f'https://ettahospitalclone.vercel.app/auth/callback?{tokens}')

        except requests.RequestException as e:
            logger.error('Google API error in callback: %s', e)
            return redirect('https://ettahospitalclone.vercel.app/login?error=google_api_error')
        except Exception as e:
            logger.exception('Unexpected error in GoogleOAuthCallbackView')
            return redirect('https://ettahospitalclone.vercel.app/login?error=auth_failed')

    def generate_username(self, name, email):
        base_username = name.replace(' ', '_').lower() if name else email.split('@')[0]
        username, counter = base_username, 1
        while User.objects.filter(username=username).exists():
            username = f'{base_username}_{counter}'
            counter += 1
        return username