from rest_framework.permissions import BasePermission

class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated):
            return False
        return bool(u.is_staff or u.groups.filter(name="admin").exists())
