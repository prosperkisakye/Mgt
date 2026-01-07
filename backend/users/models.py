import uuid
from django.db import models
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models, transaction
from rest_framework_simplejwt.tokens import RefreshToken
from django.utils import timezone
from django.db.models import TextChoices, Q, UniqueConstraint
import secrets
from utilities.models import SoftDeletableTimeStampedModel, TimeStampedModel
from datetime import timedelta
from django.conf import settings

class CustomUserManager(BaseUserManager):
    def generate_unique_username(self, fullname: str) -> str:
        """Generate a unique username from the *string* fullname."""
        if not fullname or not isinstance(fullname, str):
            base = "user"
        else:
            # Clean and split
            parts = [p.strip() for p in fullname.split() if p.strip()]
            if len(parts) >= 2:
                base = f"{parts[0][0].lower()}{parts[1].lower()}"
            else:
                base = "".join(c for c in parts[0].lower() if c.isalnum())
            base = base or "user"

        username = base[:50]
        counter = 1
        while self.filter(Q(username=username)).exists():
            candidate = f"{base}{counter}"[:50]
            if counter > 99:                     # safety net
                username = f"user{uuid.uuid4().hex[:8]}"
                break
            username = candidate
            counter += 1
        return username

    def create_user(self, email, fullname, password=None, **extra_fields):
        """Create and save a regular user with the given email, fullname, and password."""
        if not email:
            raise ValueError('The Email field must be set')
        if not fullname:
            raise ValueError('The Fullname field must be set')

        email = self.normalize_email(email)
        extra_fields.setdefault('username', self.generate_unique_username(fullname))
        user = self.model(email=email, fullname=fullname, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, fullname, password=None, **extra_fields):
        """Create and save a superuser with the given email, fullname, and password."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, fullname, password, **extra_fields)


class UserType(TextChoices):
    STAFF = "STAFF", "Staff"


class CustomUser(AbstractBaseUser, PermissionsMixin, SoftDeletableTimeStampedModel):
    email = models.EmailField(unique=True, blank=True, null=True)
    username = models.CharField(max_length=50, unique=True, null=True, blank=True)
    fullname = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20, blank=True, null=True, unique=True)
    is_staff = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)
    is_password_verified = models.BooleanField(default=True)
    gender = models.CharField(
        max_length=10,
        choices=[("male", "Male"), ("female", "Female"), ("other", "Other")],
        blank=True,
        null=True,
    )
    welcome_email_sent = models.BooleanField(default=False)
    user_type = models.CharField(
        max_length=20,
        choices=UserType.choices,
        default=UserType.STAFF,
    )
    permissions = models.JSONField(default=list)
    session_id = models.CharField(max_length=36, blank=True, null=True)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["fullname"]

    def __str__(self):
        """Return string representation for audit logs."""
        if self.fullname:
            return self.fullname.strip()[:100]  # Safe, truncated
        if self.email:
            return self.email[:100]
        if self.username:
            return self.username
        return f"User #{self.id or 'new'}"

    def get_token(self):
        """Generate a custom JWT token with additional user details."""
        institution = None
        if hasattr(self, "profile") and self.profile:
            institution = self.profile.institution
        if institution and institution.user_inactivity_time:
            lifetime = timedelta(minutes=institution.user_inactivity_time)
        else:
            lifetime = settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME", timedelta(hours=1))

        self.session_id = str(uuid.uuid4())
        self.save()

        refresh = RefreshToken.for_user(self)
        refresh.access_token.set_exp(lifetime=lifetime)

        refresh["email"] = self.email
        refresh["fullname"] = self.fullname
        refresh["lifetime"] = int(lifetime.total_seconds()) / 60
        refresh["session_id"] = self.session_id

        access_token = str(refresh.access_token)

        return {"refresh": str(refresh), "access": access_token}

    def get_all_permissions(self, obj=None):
        """Get all permissions for this user."""
        perms = Permission.objects.filter(
            roles__role__user_roles__user=self
        ).values_list("permission_code", flat=True)
        return set(perms)
    
    def has_permission(self, perm_name):
        """Check if user has a specific permission."""
        # if self.is_active and self.is_superuser:
        #     return True
        
        # Check if user is the institution owner
        # if hasattr(self, 'profile') and self.profile.institution:
        #     if self.profile.institution.institution_owner == self:
        #         return True
        
        # Check against user's assigned permissions
        return perm_name in self.get_all_permissions()

    def has_perm(self, perm, obj=None):
        """Override Django's default has_perm method."""
        # if self.is_active and self.is_superuser:
        #     return True
        return self.has_permission(perm)

    def has_perms(self, perm_list, obj=None):
        """Check multiple permissions at once."""
        return all(self.has_perm(perm, obj) for perm in perm_list)

    def get_group_permissions(self, obj=None):
        """For compatibility with Django's auth system."""
        return self.get_all_permissions(obj)

    def __str__(self):
        return self.fullname



class OneTimePassword(SoftDeletableTimeStampedModel):
    otp_hash = models.CharField(max_length=256)
    expiry = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    purpose = models.CharField(max_length=255, blank=True, null=True)

    def is_expired(self):
        return timezone.now() > self.expiry

    class Meta:
        indexes = [
            models.Index(fields=["otp_hash"]),
            models.Index(fields=["purpose"]),
            models.Index(fields=["expiry"]),
        ]

    def __str__(self):
        return f"OTP {self.purpose} (expires: {self.expiry})"
    
class PermissionCategory(SoftDeletableTimeStampedModel):
    permission_category_name = models.CharField(max_length=255)
    permission_category_description = models.TextField()

    def __str__(self):
        return self.permission_category_name

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["permission_category_name"],
                condition=Q(deleted_at__isnull=True),
                name="unique_active_permission_category_name",
            )
        ]  

class Permission(SoftDeletableTimeStampedModel):
    permission_code = models.CharField(max_length=255)
    permission_name = models.CharField(max_length=255)
    permission_description = models.TextField(blank=True, null=True)
    category = models.ForeignKey(
        PermissionCategory, related_name="permissions", on_delete=models.CASCADE
    )

    def __str__(self):
        return f"{self.permission_name} ({self.category})"

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=["permission_code"],
                condition=Q(deleted_at__isnull=True),
                name="unique_active_permission_code",
            ),
            UniqueConstraint(
                fields=["permission_name"],
                condition=Q(deleted_at__isnull=True),
                name="unique_active_permission_name",
            ),
        ]

    def delete(self, *args, **kwargs):
        if kwargs.get('hard', False) or not hasattr(self, 'deleted_at'):
            UserPermission.objects.filter(
                permission=self
            ).delete()

            super().delete(*args, **kwargs)
        else:
            self.deleted_at = timezone.now()
            self.save(update_fields=['deleted_at'])    


class Role(SoftDeletableTimeStampedModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)


    def __str__(self):
        return self.name

      
    

class RolePermission(SoftDeletableTimeStampedModel):
    role = models.ForeignKey(Role, related_name="permissions", on_delete=models.CASCADE)
    permission = models.ForeignKey(
        Permission, related_name="roles", on_delete=models.CASCADE
    )


    def __str__(self):
        return f"{self.role} - {self.permission}"


    
class UserPermission(TimeStampedModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.email} - {self.permission.permission_name}"
    
    def save(self, *args, **kwargs):

        is_new = self.pk is None

        super().save(*args, **kwargs)



class UserRole(SoftDeletableTimeStampedModel):
    user = models.ForeignKey(
        CustomUser, related_name="user_roles", on_delete=models.CASCADE
    )
    role = models.ForeignKey(Role, related_name="user_roles", on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.user.email} - {self.role.name}"




class OTPModel(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    value = models.CharField(max_length=64, unique=True)
    purpose = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_expired(self):
        return timezone.now() > self.expires_at