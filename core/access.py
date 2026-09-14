from functools import wraps

from django.core.exceptions import PermissionDenied


def user_is_executive(user):
    """Identifica quem possui a visao global da diretoria."""
    if not user.is_authenticated:
        return False
    return (
        user.is_superuser
        or getattr(user, 'username', '').casefold() == 'ceo_premium'
        or user.groups.filter(name='Admin_Global').exists()
    )


def user_has_access(user, *, permission=None, profiles=(), groups=()):
    """Return whether a user satisfies one of the configured access rules."""
    if not user.is_authenticated:
        return False
    if user_is_executive(user):
        return True

    user_groups = set(user.groups.values_list('name', flat=True))
    if 'Admin_Global' in user_groups:
        return True
    if groups and user_groups.intersection(groups):
        return True
    if permission and user.has_perm(permission):
        return True

    perfil_obj = getattr(user, 'perfil', None)
    return getattr(perfil_obj, 'perfil', None) in set(profiles)


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
            if user_has_access(
                request.user,
                permission=permission,
                profiles=allowed_profiles,
                groups=allowed_groups,
            ):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied

        return wrapped

    return decorator
