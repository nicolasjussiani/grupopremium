from functools import wraps

from django.core.exceptions import PermissionDenied


def access_required(*, permission=None, profiles=(), groups=()):
    """Autoriza por permissao Django, grupo explicito ou perfil legado.

    Superusuarios e membros de Admin_Global sempre possuem acesso. O fallback
    por perfil mantem compatibilidade com usuarios existentes enquanto os
    grupos granulares sao implantados.
    """

    allowed_profiles = set(profiles)
    allowed_groups = set(groups)

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                raise PermissionDenied
            if user.is_superuser:
                return view_func(request, *args, **kwargs)

            user_groups = set(user.groups.values_list('name', flat=True))
            if 'Admin_Global' in user_groups:
                return view_func(request, *args, **kwargs)
            if allowed_groups and user_groups.intersection(allowed_groups):
                return view_func(request, *args, **kwargs)
            if permission and user.has_perm(permission):
                return view_func(request, *args, **kwargs)

            perfil_obj = getattr(user, 'perfil', None)
            if getattr(perfil_obj, 'perfil', None) in allowed_profiles:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return wrapped

    return decorator
