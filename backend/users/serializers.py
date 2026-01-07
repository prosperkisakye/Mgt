import re
from rest_framework import serializers
from django.db import transaction
from django.db.models import QuerySet
from .services import sync_permissions_from_roles
from .models import (
    CustomUser,
    PermissionCategory,
    Permission,
    Role,
    RolePermission,
    UserPermission,
    UserRole,
)
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from utilities.password_validator import validate_password_strength
from utilities.serializers import BaseModelSerializer
from django.contrib.auth.password_validation import validate_password
from django.core import exceptions

class PermissionCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionCategory
        fields = '__all__'


class PermissionSerializer(serializers.ModelSerializer):
    category = PermissionCategorySerializer()

    class Meta:
        model = Permission
        fields = '__all__'

class RoleSerializer(BaseModelSerializer):
    permissions_details = serializers.SerializerMethodField()
    permissions = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Permission.objects.all(), write_only=True, required=False
    )

    class Meta:
        model = Role
        fields = '__all__'

        extra_kwargs = {"institution": {"required": False}}

    def get_permissions_details(self, obj):
        permissions = Permission.objects.filter(roles__role=obj)
        return PermissionSerializer(permissions, many=True).data

    def create(self, validated_data):
        permissions = validated_data.pop("permissions", [])
        role = Role.objects.create(**validated_data)

        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=p) for p in permissions]
        )

        return role

    def update(self, instance, validated_data):
        permissions = validated_data.pop("permissions", [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        RolePermission.objects.filter(role=instance).delete()
        RolePermission.objects.bulk_create(
            [RolePermission(role=instance, permission=p) for p in permissions]
        )

        return instance

def clean_fullname(value: str) -> str:
    value = value.strip()

    if len(value) < 2:
        raise serializers.ValidationError("Full name is too short.")
    if len(value) > 100:
        raise serializers.ValidationError("Full name is too long.")

    if re.search(r'(https?://|www\.)', value, re.I):
        raise serializers.ValidationError("URLs are not allowed in the name.")

    emoji = re.compile(
        r'[\U0001F600-\U0001F64F]'
        r'|[\U0001F300-\U0001F5FF]'
        r'|[\U0001F680-\U0001F6FF]'
        r'|[\U0001F1E0-\U0001F1FF]'
        r'|[\U00002600-\U000027BF]'
    )
    if emoji.search(value):
        raise serializers.ValidationError("Emojis are not allowed in the name.")

    if re.search(r'<script|javascript:|on\w+[\s=]', value, re.I):
        raise serializers.ValidationError("Invalid characters in name.")

    if not re.match(r"^[a-zA-Z\s\.\-']+$", value):
        raise serializers.ValidationError("Only letters, spaces, hyphens, dots, and apostrophes allowed.")

    return value      

class CustomUserSerializer(BaseModelSerializer):
    roles = serializers.SerializerMethodField()
    roles_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    email = serializers.EmailField(required=True, validators=[])
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = CustomUser
        fields = "__all__"
        read_only_fields = [
            "is_active",
            "is_staff",
            "roles",
            "is_email_verified",
            "is_password_verified",
        ]
        extra_kwargs = {"password": {"write_only": True}}

    def get_roles(self, obj):
        roles = [ur.role for ur in obj.user_roles.all()]
        return RoleSerializer(roles, many=True).data

  

    # def validate_fullname(self, value):
    #     return clean_fullname(value)

    def validate_password(self, value):
        return validate_password_strength(value)

    @transaction.atomic
    def create(self, validated_data):
        roles_ids = validated_data.pop("roles_ids", [])
        password = validated_data.pop("password", None)

        user = CustomUser.objects.create_user(**validated_data)
        if password:
            user.set_password(password)
            user.save()

        if roles_ids:
            self._update_user_roles(user, roles_ids)

        return user

    @transaction.atomic
    def update(self, instance, validated_data):
        roles_ids = validated_data.pop("roles_ids", None)

        instance.email = validated_data.get("email", instance.email)
        instance.fullname = validated_data.get("fullname", instance.fullname)
        instance.gender = validated_data.get("gender", instance.gender)
        instance.is_staff = validated_data.get("is_staff", instance.is_staff)

        if "password" in validated_data and validated_data["password"]:
            instance.set_password(validated_data["password"])

        instance.save()

        if roles_ids is not None:
            self._update_user_roles(instance, roles_ids)

        return instance

    def _update_user_roles(self, user, role_ids):
        """Replace user's roles and sync permissions safely"""
        from .models import Role, UserRole

        valid_roles = Role.objects.filter(id__in=role_ids)
        found_ids = set(valid_roles.values_list('id', flat=True))
        invalid_ids = set(role_ids) - found_ids
        if invalid_ids:
            raise serializers.ValidationError({"roles_ids": f"Invalid role IDs: {list(invalid_ids)}"})

        UserRole.objects.filter(user=user).delete()
        UserRole.objects.bulk_create([
            UserRole(user=user, role=role) for role in valid_roles
        ])

        sync_permissions_from_roles(user)    


class UserPermissionSerializer(serializers.ModelSerializer):
    user = CustomUserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    permission = PermissionSerializer(read_only=True)
    permission_id = serializers.IntegerField(write_only=True, required=False)
    permission_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = UserPermission
        fields = [
            "id",
            "user",
            "user_id",
            "permission",
            "permission_id",
            "permission_ids",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_permission_ids(self, value):
        if not value:
            raise serializers.ValidationError({"error": "permission_ids cannot be empty if provided."})
        existing_ids = set(Permission.objects.filter(id__in=value).values_list('id', flat=True))
        invalid_ids = set(value) - existing_ids
        if invalid_ids:
            raise serializers.ValidationError({"error": f"Invalid permission IDs: {list(invalid_ids)}"})
        return value

    def validate(self, attrs):
        has_single = "permission_id" in attrs
        has_bulk = "permission_ids" in attrs

        if has_single and has_bulk:
            raise serializers.ValidationError(
                {"error": "Provide either permission_id or permission_ids, not both"}
            )

        if not has_single and not has_bulk:
            raise serializers.ValidationError(
                {"error": "Either permission_id or permission_ids is required"}
            )

        user_id = attrs.get("user_id")
        try:
            CustomUser.objects.get(id=user_id)
        except CustomUser.DoesNotExist:
            raise serializers.ValidationError({"error": f"User with id {user_id} does not exist."})

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        """Handle both single and bulk permission creation"""
        user_id = validated_data.pop("user_id")
        permission_id = validated_data.pop("permission_id", None)
        permission_ids = validated_data.pop("permission_ids", None)
        user = CustomUser.objects.get(id=user_id)

        if permission_id:
            try:
                permission = Permission.objects.get(id=permission_id)
            except Permission.DoesNotExist:
                raise serializers.ValidationError({"error": f"Permission with id {permission_id} does not exist."})

            if UserPermission.objects.filter(
                user=user, permission=permission, is_active=True
            ).exists():
                raise serializers.ValidationError(
                    {"error": f"User {user.email} already has the permission {permission.permission_name}."}
                )

            return UserPermission.objects.create(user=user, permission=permission)
        elif permission_ids:
            existing_permissions = set(
                UserPermission.objects.filter(
                    user=user, permission__id__in=permission_ids
                ).values_list("permission__id", flat=True)
            )

            user_permissions = [
                UserPermission(user=user, permission=perm)
                for perm in Permission.objects.filter(id__in=permission_ids)
                if perm.id not in existing_permissions
            ]

            if not user_permissions:
                raise serializers.ValidationError({"error": "All provided permissions already exist for the user."})

            UserPermission.objects.bulk_create(user_permissions)
            return UserPermission.objects.filter(user=user, is_active=True)

        raise serializers.ValidationError({"error": "Either permission_id or permission_ids is required."})

    @transaction.atomic
    def update(self, instance, validated_data):
        user_id = validated_data.pop("user_id")
        permission_ids = validated_data.pop("permission_ids", [])
        user = CustomUser.objects.get(id=user_id)


        user.user_permissions.all().delete()  


        for perm_id in permission_ids:
            perm = Permission.objects.get(id=perm_id)
            UserPermission.objects.create(user=user, permission=perm)

        return UserPermission.objects.filter(user=user)


class ReadManyMinimalPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPermission
        fields = [
            "id",
            "user",
            "user_id",
            "permission",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def to_representation(self, instance):
        rep = super().to_representation(instance)
        rep["permission"] = PermissionSerializer(instance.permission).data

        return rep       

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, required=True)
    new_password = serializers.CharField(write_only=True, required=True)
    new_password_confirm = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"error": "New passwords do not match."}
            )

        user = self.context["request"].user

        if not user.check_password(data["old_password"]):
            raise serializers.ValidationError(
                {"error": "Old password is incorrect."}
            )

        try:
            validate_password(data["new_password"], user)
        except exceptions.ValidationError as e:
            errors = dict(e.error_list)
            raise serializers.ValidationError({"error": errors})

        return data

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save()
        return user    

class UserOTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)

    def validate_otp(self, value):
        if not value.isdigit():
            raise serializers.ValidationError({"error": "OTP must contain only digits"})
        return value


class ResendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()


class UserPasswordResetSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, min_length=8)


class UserResendOTPVerificationSerializer(serializers.Serializer):
    email = serializers.EmailField()


class UserSendForgotPasswordTokenSerializer(serializers.Serializer):
    email = serializers.EmailField()
    frontend_url = serializers.CharField()


class LoginRequestSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class LoginResponseSerializer(serializers.Serializer):
    tokens = TokenObtainPairSerializer()
    user = CustomUserSerializer()


class LogoutRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField(required=True)      

class RolePermissionSerializer(BaseModelSerializer):
    role = RoleSerializer()
    permission = PermissionSerializer()

    class Meta:
        model = RolePermission
        fields = '__all__'    