from rest_framework.permissions import BasePermission


class IsClient(BasePermission):
    """Only clients can access."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'client'


class IsAstrologer(BasePermission):
    """Only astrologers can access."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'astrologer'


class IsAdminUser(BasePermission):
    """Only admin users can access."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.role == 'admin' or request.user.is_staff
        )


class IsClientOrAstrologer(BasePermission):
    """Clients or astrologers can access."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['client', 'astrologer']
