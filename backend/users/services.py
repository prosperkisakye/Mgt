from django.db import transaction
from .models import RolePermission, UserPermission


@transaction.atomic
def sync_permissions_from_roles(user):
    """
    Fully syncs a user's permissions based on their current roles.
    - Adds all permissions from current roles
    - Removes permissions that are no longer granted by any current role
    - PRESERVES manually assigned permissions (those not coming from any role)
    """
    if not user.pk:
        return

    active_role_permission_ids = set(
        RolePermission.objects.filter(
            role__user_roles__user=user,
            role__user_roles__deleted_at__isnull=True,
            deleted_at__isnull=True
        ).values_list('permission_id', flat=True)
    )

    current_user_permission_ids = set(
        UserPermission.objects.filter(
            user=user,
            is_active=True
        ).values_list('permission_id', flat=True)
    )

    to_add = active_role_permission_ids - current_user_permission_ids

    to_remove = current_user_permission_ids - active_role_permission_ids

    if to_add:
        UserPermission.objects.bulk_create(
            [UserPermission(user=user, permission_id=pid) for pid in to_add],
            ignore_conflicts=True
        )

    if to_remove:
        UserPermission.objects.filter(
            user=user,
            permission_id__in=to_remove,
        ).delete()
