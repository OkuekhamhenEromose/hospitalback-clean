from rest_framework import permissions

class IsRole(permissions.BasePermission):
    """
    Allow access only to users with one of the allowed roles.
    Example: allowed_roles = ['DOCTOR', 'NURSE']
    """

    def has_permission(self, request, view):
        allowed = getattr(view, 'allowed_roles', None)
        if allowed is None:
            return True

        user = request.user
        if not user or not user.is_authenticated:
            return False

        profile = getattr(user, 'profile', None)
        if not profile or not hasattr(profile, 'role'):
            return False

        return profile.role in allowed
