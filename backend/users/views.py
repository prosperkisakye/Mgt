from django.shortcuts import render
from typing import Literal
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema
from django.db.models import Prefetch
from utilities.helpers import (
    build_password_link,
    create_and_institution_otp,
    error_response,
    fingerprint,
    send_otp_to_user,
    send_email_to_user,
    send_password_link_to_user,
    verify_otp,
    cleanup_expired_otps,
    send_password_reset_link_to_user,
    create_and_institution_token,
)
from rest_framework.throttling import UserRateThrottle
from drf_spectacular.openapi import OpenApiTypes
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django.utils import timezone
from .serializers import (
    CustomUserSerializer,
    LoginRequestSerializer,
    ReadManyMinimalPermissionSerializer,
    RoleSerializer,
    PermissionSerializer,
    PermissionCategorySerializer,
    UserOTPVerificationSerializer,
    UserPasswordResetSerializer,
    UserPermissionSerializer,
    UserResendOTPVerificationSerializer,
    UserSendForgotPasswordTokenSerializer,
    ResendOTPSerializer,
    LogoutRequestSerializer,
    ChangePasswordSerializer,
)
from utilities.sortable_api import SortableAPIMixin
from .models import (
    CustomUser,
    Role,
    Permission,
    PermissionCategory,
    UserPermission,
    UserType,
    OTPModel,
)
from django.contrib.auth import authenticate
from rest_framework_simplejwt.views import TokenRefreshView
from django.core.exceptions import ObjectDoesNotExist
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken, OutstandingToken, BlacklistedToken  
from utilities.pagination import CustomPageNumberPagination
from utilities.password_validator import validate_password_strength
from django.conf import settings
from django.core.cache import cache
import requests
import secrets
import urllib.parse
from .utils import generate_compliant_password
from django.db.models import Q
import logging
from django.db import transaction


logger = logging.getLogger(__name__)

class SignupThrottle(UserRateThrottle):
    scope = 'signup'


class UserListAPIView(APIView, SortableAPIMixin):
    permission_classes = [permissions.AllowAny]
    throttle_scope = "signup"
    allowed_ordering_fields = ['fullname', 'created_at', 'email', 'is_active', 'gender']
    default_ordering = ['fullname']

    def get_throttles(self):
        if self.request.method == 'POST':
            return [SignupThrottle()]
        return super().get_throttles()

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            fp = fingerprint(request)
            if cache.get(f"signup_junk_{fp}", 0) >= 5:
                return error_response("You are temporarily blocked.", 403)
        return super().dispatch(request, *args, **kwargs)

    @extend_schema(
        request=CustomUserSerializer,
        responses={201: CustomUserSerializer},
        description="Register a new user with email, full name, and password.",
        summary="Create a new user",
        tags=["User Management"],
    )
    def post(self, request):

        serializer = CustomUserSerializer(data=request.data)
        if serializer.is_valid():

            user = serializer.save()


            otp = create_and_institution_otp(
                user_id=user.id, purpose=f"registration_{user.id}", expiry_minutes=15
            )

            send_otp_to_user(user, otp)
            cleanup_expired_otps()

            return Response(
                CustomUserSerializer(user).data,
                status=status.HTTP_201_CREATED,
            )
        
        fp = fingerprint(request)
        cache.set(f"signup_junk_{fp}", cache.get(f"signup_junk_{fp}", 0) + 1, 86400)

        first_error = next(iter(serializer.errors.values()))[0]
        error_msg = str(first_error)

        logger.warning("Signup failed", extra={
            "ip": request.META.get("REMOTE_ADDR"),
            "error": error_msg,
            "payload": request.data
        })  

        return Response(
            {"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


    @extend_schema(
        responses={200: CustomUserSerializer(many=True)},
        description="Retrieve the authenticated user's details.",
        summary="Get user details",
        tags=["User Management"],
    )
    def get(self, request):

        queryset = CustomUser.objects.filter(
            deleted_at__isnull=True
        )
        search_query = request.query_params.get("search")

        if search_query:
            queryset = queryset.filter(
                Q(fullname__icontains=search_query) |
                Q(email__icontains=search_query)
            )
        try:
            queryset = self.apply_sorting(queryset, request)
        except ValueError as e:
            return Response ({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST) 
        
        paginator = CustomPageNumberPagination()
        paginated_users = paginator.paginate_queryset(queryset, request)
        serializer = CustomUserSerializer(paginated_users, many=True)
        return paginator.get_paginated_response(serializer.data)


class ChangePasswordAPIView(APIView):
    @extend_schema(
        request=ChangePasswordSerializer,
        responses={200: {"description": "Password changed successfully"}},
        description="Change the authenticated user's password.",
        summary="Change password",
        tags=["User Management"],
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            serializer.save()
            return Response({"message": "Password changed successfully"}, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)    


class ChangeEmailAndResendOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request={
            "type": "object",
            "properties": {
                "old_email": {"type": "string", "format": "email"},
                "new_email": {"type": "string", "format": "email"},
            },
            "required": ["old_email", "new_email"],
        },
        responses={
            200: {"message": "string"},
            400: {"detail": "string"},
            404: {"detail": "string"},
        },
        description="Change user email and resend OTP for registration verification",
        summary="Change email and resend OTP",
        tags=["User Management"],
    )
    def post(self, request):
        old_email = request.data.get("old_email")
        new_email = request.data.get("new_email")

        if not old_email or not new_email:
            return Response(
                {"detail": "Both old_email and new_email are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if old_email == new_email:
            return Response(
                {"detail": "New email must be different from the old email"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = CustomUser.objects.get(email=old_email)
            if CustomUser.objects.filter(email=new_email).exists():
                return Response(
                    {"detail": "New email is already in use"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.email = new_email
            user.save()

            otp = create_and_institution_otp(
                user_id=user.id, purpose=f"registration_{user.id}", expiry_minutes=15
            )

            send_otp_to_user(user, otp)

            cleanup_expired_otps()

            print(f"Email changed for user {user.id} from {old_email} to {new_email}, OTP resent")
            return Response(
                {"message": f"OTP sent to new email: {new_email}"},
                status=status.HTTP_200_OK,
            )

        except CustomUser.DoesNotExist:
            print(f"User with email {old_email} not found during email change")
            return Response(
                {"detail": "User with old email not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            print(f"Error during email change for user with email {old_email}: {str(e)}")
            return Response(
                {"detail": "An error occurred during email change"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
class UserDetailAPIView(APIView):
    @extend_schema(
        responses={200: CustomUserSerializer},
        description="Retrieve a specific user's details.",
        summary="Get user details",
        tags=["User Management"],
    )
    def get(self, request, base_uuid):
        try:
            user = CustomUser.objects.get(base_uuid=base_uuid)
            serializer = CustomUserSerializer(user)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except CustomUser.DoesNotExist:
            return Response(
                {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )

    @extend_schema(
        request=CustomUserSerializer(partial=True),
        responses={200: CustomUserSerializer},
        description="Update the authenticated user's details (partial update).",
        summary="Update user details",
        tags=["User Management"],
    )
    def patch(self, request, base_uuid):
        if base_uuid:
            try:
                user = CustomUser.objects.get(base_uuid=base_uuid)
                serializer = CustomUserSerializer(user, data=request.data, partial=True)
                if serializer.is_valid():
                    serializer.save()
                    return Response(
                        {
                            "message": "User updated successfully",
                            "user": serializer.data,
                        },
                        status=status.HTTP_200_OK,
                    )
                return Response(
                    {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
                )
            except CustomUser.DoesNotExist:
                return Response(
                    {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )
        return Response(
            {"detail": "User ID is required for updating."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @extend_schema(
        responses={204: None},
        description="Delete a specific user.",
        summary="Delete user",
        tags=["User Management"],
    )
    def delete(self, request, base_uuid):
        if base_uuid:
            try:
                user = CustomUser.objects.get(base_uuid=base_uuid)
                user.delete()
                return Response(
                    {"message": "User deleted successfully"},
                    status=status.HTTP_204_NO_CONTENT,
                )
            except CustomUser.DoesNotExist:
                return Response(
                    {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
                )
        return Response(
            {"detail": "User ID is required for deletion."},
            status=status.HTTP_400_BAD_REQUEST,
        )  


class VerifyOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=UserOTPVerificationSerializer,
        responses={200: {"message": "string"}},
        description="Verify OTP for user registration",
        tags=["User Management"],
    )
    def post(self, request):
        serializer = UserOTPVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        try:
            user = CustomUser.objects.get(email=email)

            success, message = verify_otp(user.id, received_otp=otp)

            if success:
                user.is_active = True
                user.is_email_verified = True
                user.save()

                print(f"User {user.id} verified and activated successfully")
                return Response(
                    {"message": "OTP verified successfully. Account activated."},
                    status=status.HTTP_200_OK,
                )
            else:
                print(f"OTP verification failed for user {user.id}: {message}")
                return Response(
                    {"message": message}, status=status.HTTP_400_BAD_REQUEST
                )

        except CustomUser.DoesNotExist:
            print(f"User {user.id} not found during OTP verification")
            return Response(
                {"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            print(f"Error during OTP verification for user {user.id}: {str(e)}")
            return Response(
                {"detail": "An error occurred during verification"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ResendOTPAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=UserResendOTPVerificationSerializer,
        responses={200: {"message": "string"}},
        description="Resend email OTP for user registration",
        tags=["User Management"],
    )
    def post(self, request):
        mode: Literal["otp", "password_link"] = request.query_params.get("mode", "otp")
        serializer = ResendOTPSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        try:

            email = serializer.validated_data["email"]
            user_instance = CustomUser.objects.get(email=email)
            otp = create_and_institution_otp(
                user_id=user_instance.id, purpose="registration", expiry_minutes=15
            )
            if mode == "otp":
                send_otp_to_user(user_instance, otp)
            else:
                token = create_and_institution_token(
                    user=user_instance,
                    purpose="registration",
                    expiry_minutes=15,
                )
                password_link = build_password_link(request=request, token=token)
                send_password_link_to_user(user=user_instance, link=password_link)

            return Response(
                CustomUserSerializer(user_instance).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {"detail": "Could not send the OTP"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        if serializer.is_valid():
            username = serializer.validated_data["username"]
            password = serializer.validated_data["password"]

            user = authenticate(request, username=username, password=password)

            if user is not None:
                for token in OutstandingToken.objects.filter(user=user):
                    BlacklistedToken.objects.get_or_create(token=token)

                if not user.is_password_verified and not user.is_email_verified:
                    return Response(
                        {
                            "detail": "You need to reset your password to be able to login",
                            "custom_code": "ADMIN_CREATED_UNVERIFIED",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if not user.is_email_verified:
                    return Response(
                        {
                            "detail": "You need to verify your email to gain access to your account",
                            "custom_code": "SELF_CREATED_UNVERIFIED",
                        },
                        status=status.HTTP_403_FORBIDDEN,
                    )

                if not user.is_active:
                    return Response(
                        {"detail": "Your account is currently inactive. Contact Admin to have it activated"},
                        status=status.HTTP_403_FORBIDDEN,
                    )

            return Response(
                {
                    "detail": "Invalid Credentials",
                    "custom_code": "INVALID_CREDENTIALS",
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )


class RoleListAPIView(APIView, SortableAPIMixin):
    allowed_ordering_fields = ['name', 'created_at', 'is_active']
    default_ordering = ['name']
    @extend_schema(
        request=RoleSerializer,
        responses={201: RoleSerializer},
        description="Create a new role.",
        summary="Create a new role",
        tags=["User Management"],
    )
    @transaction.atomic()
    def post(self, request):
        serializer: RoleSerializer = RoleSerializer(data=request.data)

        if serializer.is_valid():
            role = serializer.save()
            return Response(
                RoleSerializer(role).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        responses={200: RoleSerializer(many=True)},
        description="Retrieve all roles.",
        summary="Get all roles",
        tags=["User Management"],
    )
    def get(self, request):
        roles = Role.objects.order_by(
            "name"
        )
        try:
            roles = self.apply_sorting(roles, request)
        except ValueError as e:
            return Response ({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)    
        paginator = CustomPageNumberPagination()
        paginator_qs = paginator.paginate_queryset(roles, request)
        serializer = RoleSerializer(
            paginator_qs, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)


class RoleDetailAPIView(APIView):
    @extend_schema(
        responses={200: RoleSerializer},
        summary="Get a role",
        tags=["User Management"],
    )
    def get(self, request, base_uuid):
        role = get_object_or_404(Role, base_uuid=base_uuid)
        serializer = RoleSerializer(role)
        return Response(serializer.data)

    @extend_schema(
        request=RoleSerializer,
        responses={200: RoleSerializer},
        summary="Update a role",
        tags=["User Management"],
    )
    @transaction.atomic()
    def patch(self, request, base_uuid):
        role = get_object_or_404(Role, base_uuid=base_uuid)
        serializer = RoleSerializer(role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        responses={204: None},
        summary="Delete a role",
        tags=["User Management"],
    )
    def delete(self, request, base_uuid):
        role = get_object_or_404(Role, base_uuid=base_uuid)
        role.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
    

class PermissionCategoryListAPIView(APIView):
    @extend_schema(
        request=PermissionSerializer,
        responses={201: PermissionSerializer},
        description="Create a new permission Category.",
        summary="Create a new permission Category",
        tags=["User Management"],
    )
    def post(self, request):
        serializer: PermissionCategorySerializer = PermissionCategorySerializer(
            data=request.data
        )

        if serializer.is_valid():
            permission_category = serializer.save()
            return Response(
                PermissionCategorySerializer(permission_category).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        responses={200: PermissionCategorySerializer(many=True)},
        description="Retrieve all permission categories.",
        summary="Retrieve all permission categories",
        tags=["User Management"],
    )
    def get(self, request):
        permission_categories = PermissionCategory.objects.all().order_by("-created_at")
        paginator = CustomPageNumberPagination()
        paginated_qs = paginator.paginate_queryset(permission_categories, request)
        serializer = PermissionCategorySerializer(paginated_qs, many=True)
        return paginator.get_paginated_response(serializer.data)


class PermissionCategoryDetailAPIView(APIView):
    @extend_schema(
        responses={200: PermissionCategorySerializer},
        summary="Get a permission category",
        tags=["User Management"],
    )
    def get(self, request, base_uuid):
        role = get_object_or_404(PermissionCategory, base_uuid=base_uuid)
        serializer = PermissionCategorySerializer(role)
        return Response(serializer.data)

    @extend_schema(
        request=PermissionCategorySerializer,
        responses={200: PermissionCategorySerializer},
        summary="Update a permission category",
        tags=["User Management"],
    )
    def patch(self, request, base_uuid):
        role = get_object_or_404(PermissionCategory, base_uuid=base_uuid)
        serializer = PermissionCategory(role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        responses={204: None},
        summary="Delete a permission category",
        tags=["User Management"],
    )
    def delete(self, request, base_uuid):
        permission_category = get_object_or_404(PermissionCategory, base_uuid=base_uuid)
        permission_category.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionListAPIView(APIView):
    @extend_schema(
        request=PermissionSerializer,
        responses={201: PermissionSerializer},
        description="Create a new permission.",
        summary="Create a new permission",
        tags=["User Management"],
    )
    def post(self, request):
        serializer: PermissionSerializer = PermissionSerializer(data=request.data)

        if serializer.is_valid():
            permission = serializer.save()
            return Response(
                PermissionSerializer(permission).data, status=status.HTTP_201_CREATED
            )
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        responses={200: PermissionSerializer(many=True)},
        description="Retrieve all permissions.",
        summary="Retrieve all permissions",
        tags=["User Management"],
    )
    def get(self, request):
        system_permissions = Permission.objects.all()
        paginator = CustomPageNumberPagination()
        paginated_qs = paginator.paginate_queryset(system_permissions, request)
        serializer = PermissionSerializer(paginated_qs, many=True)
        return paginator.get_paginated_response(serializer.data)


class PermissionDetailAPIView(APIView):
    @extend_schema(
        responses={200: PermissionSerializer},
        summary="Get a permission",
        tags=["User Management"],
    )
    def get(self, request, base_uuid):
        role = get_object_or_404(Permission, base_uuid=base_uuid)
        serializer = PermissionSerializer(role)
        return Response(serializer.data)

    @extend_schema(
        request=PermissionSerializer,
        responses={200: PermissionSerializer},
        summary="Update a permission",
        tags=["User Management"],
    )
    def patch(self, request, base_uuid):
        role = get_object_or_404(Permission, base_uuid=base_uuid)
        serializer = PermissionSerializer(role, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(
            {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        responses={204: None},
        summary="Delete a permission",
        tags=["User Management"],
    )
    def delete(self, request, base_uuid):
        permission = get_object_or_404(Permission, base_uuid=base_uuid)
        permission.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForgotPasswordAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=UserSendForgotPasswordTokenSerializer,
        responses={200: {"detail": "string"}},
        description="Request a password reset link",
        summary="Forgot Password",
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = UserSendForgotPasswordTokenSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        email = serializer.validated_data["email"].lower()
        frontend_url = serializer.validated_data.get("frontend_url")

        user = CustomUser.objects.filter(email=email).first()

        if not user:
            return Response(
                {"detail": "No user found with this email address."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            token = create_and_institution_token(
                user=user, purpose="password_reset", expiry_minutes=1440
            )

            reset_link = f"{frontend_url}/forgot-password/reset-password/{token}"

            send_password_reset_link_to_user(user=user, link=reset_link)

            return Response(
                {"detail": "Password reset link sent successfully."},
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(f"Error in forgot password: {str(e)}")
            return Response(
                {"detail": "An error occurred while processing your request."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VerifyTokenAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request={"token": "string"},
        responses={200: {"valid": "boolean"}},
        description="Verify if a password reset token is valid",
        summary="Verify Reset Token",
        tags=["Authentication"],
    )
    def post(self, request):
        token = request.data.get("token")

        if not token:
            return Response(
                {"detail": "Token is required"}, status=status.HTTP_400_BAD_REQUEST
            )

        try:
            token_obj = OTPModel.objects.filter(
                value=token,
                purpose="password_reset",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            return Response({"valid": bool(token_obj)}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"detail": "An error occurred while verifying the token."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
class ResetPasswordAPIView(APIView):
    permission_classes = [permissions.AllowAny]

    @extend_schema(
        request=UserPasswordResetSerializer,
        responses={200: {"detail": "string"}},
        description="Reset password using token",
        summary="Reset Password",
        tags=["Authentication"],
    )
    def post(self, request):
        serializer = UserPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"detail": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )

        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        try:
            try:
                validate_password_strength(new_password)
            except Exception as e:
                return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            token_obj = OTPModel.objects.filter(
                value=token,
                purpose="password_reset",
                is_used=False,
                expires_at__gt=timezone.now(),
            ).first()

            if not token_obj:
                return Response(
                    {"detail": "Invalid or expired token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user = token_obj.user
            user.set_password(new_password)
            user.is_password_verified = True
            user.is_email_verified = True
            user.save()

            token_obj.is_used = True
            token_obj.save()

            print(f"Password reset successful for user {user.id}")
            return Response(
                {"detail": "Password has been reset successfully"},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            print(f"Error in reset password: {str(e)}")
            return Response(
                {"detail": "An error occurred while resetting your password."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            ) 


class LogoutView(APIView):
    @extend_schema(
        request=LogoutRequestSerializer,
        responses={205: None},
        description="Invalidate the refresh token to log out the user.",
        summary="User Logout",
        tags=["Authentication"],
    )   
    def post(self, request):
        serializer = LogoutRequestSerializer(data=request.data)
        if serializer.is_valid():
            try:
                refresh_token = serializer.validated_data['refresh']
                UntypedToken(refresh_token)
                token = RefreshToken(refresh_token)
                token.blacklist()
                return Response({"detail": "Successfully logged out."}, status=status.HTTP_205_RESET_CONTENT)
            except TokenError as e:
                return Response({"detail": "Invalid refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)               
    

class UserPermissionListView(APIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=ReadManyMinimalPermissionSerializer(many=True),
                description="List of user permissions retrieved successfully"
            ),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="User not found",
            ),
        },
        tags=["User Permissions"]
    )
    @transaction.atomic
    def get(self, request, user_base_uuid):
        institution = request.user.profile.institution
        try:
            user = CustomUser.objects.get(base_uuid=user_base_uuid)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": f"User does not exist."},
                status=status.HTTP_404_NOT_FOUND
            )

        user_permissions = UserPermission.objects.filter(user=user, is_active=True)

        paginator = CustomPageNumberPagination()
        paginator_qs = paginator.paginate_queryset(user_permissions, request)
        serializer = ReadManyMinimalPermissionSerializer(paginator_qs, many=True)

        return paginator.get_paginated_response(serializer.data)


class UserPermissionDetailView(APIView):
    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=UserPermissionSerializer(many=True),
                description="Permissions added successfully",
            ),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="User not found",
            ),
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Invalid request data",
            ),
        },
        tags=["User Permissions"],
    )
    @transaction.atomic
    def post(self, request, user_base_uuid):
        try:
            user = CustomUser.objects.get(base_uuid=user_base_uuid)
        except (ValueError, CustomUser.DoesNotExist):
            return Response(
                {"error": "User not found or invalid ID"},
                status=status.HTTP_404_NOT_FOUND,
            )


        data = request.data.copy()
        data["user_id"] = user.base_uuid
        serializer = UserPermissionSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        created_perms = serializer.create(serializer.validated_data)

        return Response(
            UserPermissionSerializer(created_perms, many=True).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        responses={
            200: OpenApiResponse(
                response=UserPermissionSerializer(many=True),
                description="Permissions updated successfully",
            ),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="User not found",
            ),
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Invalid request data",
            ),
        },
        tags=["User Permissions"],
    )
    @transaction.atomic
    def patch(self, request, user_id):
        try:
            user = CustomUser.objects.get(id=int(user_id))
        except (ValueError, CustomUser.DoesNotExist):
            return Response(
                {"error": "User not found or invalid ID"},
                status=status.HTTP_404_NOT_FOUND,
            )


        data = request.data.copy()
        data["user_id"] = user_id
        serializer = UserPermissionSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        updated_perms = serializer.update(None, serializer.validated_data)


        return Response(
            UserPermissionSerializer(updated_perms, many=True).data,
            status=status.HTTP_200_OK,
        )


class UserPermissionDeleteView(APIView):
    @extend_schema(
        responses={
            204: OpenApiResponse(
                description="User permission deleted successfully"
            ),
            404: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="User permission not found",
            ),
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Invalid request",
            ),
        },
        tags=["User Permissions"],
        description="Delete a specific user permission by its ID"
    )
    @transaction.atomic
    def delete(self, request, base_uuid):
        try:
            user_permission_id = base_uuid
        except ValueError:
            return Response(
                {"error": "User permission ID must be a valid integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user_permission = UserPermission.objects.get(
                base_uuid=user_permission_id,
                is_active=True
            )
        except UserPermission.DoesNotExist:
            return Response(
                {"error": f"User permission with id {user_permission_id} does not exist."},
                status=status.HTTP_404_NOT_FOUND
            )

        user_permission.delete()
        return Response(
            {"message": f"User permission with id {user_permission_id} deleted successfully."},
            status=status.HTTP_204_NO_CONTENT
        )    