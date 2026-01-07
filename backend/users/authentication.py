from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
import jwt
import json
import logging
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q
from rest_framework_simplejwt.authentication import JWTAuthentication


logger = logging.getLogger(__name__)


def some_function():
    User = get_user_model()


class CrossSystemAuthentication(BaseAuthentication):
    """
    Custom authentication class for external system authentication via API keys and access tokens.
    """

    def authenticate(self, request):
        api_key = self.extract_api_key(request)

        if not api_key:
            return None

        return self.authenticate_external_system(request, api_key)

    def extract_api_key(self, request):
        return (
            request.headers.get("X-API-Key")
            or request.headers.get("x-api-key")
            or request.headers.get("API-Key")
        )

    def authenticate_external_system(self, request, api_key):
        from .models import System

        try:

            system = self.get_system_from_api_key(api_key)

            access_token = self.extract_access_token(request)

            if not access_token:
                raise AuthenticationFailed(_("Access token is required"))

            access_token_payload = self.decode_access_token(access_token, system)

            user = self.get_user_from_payload(system, access_token_payload)

            if not user:
                raise AuthenticationFailed(
                    _("User not found or not associated with system")
                )

            request.external_system = system
            request.access_token_payload = access_token_payload

            return (user, access_token)

        except AuthenticationFailed as e:
            raise
        except System.DoesNotExist:
            raise AuthenticationFailed(_("Invalid API key"))
        except (jwt.InvalidTokenError, json.JSONDecodeError) as e:
            raise AuthenticationFailed(_("Invalid access token format"))
        except Exception as e:
            raise AuthenticationFailed(_("Authentication failed"))

    def get_system_from_api_key(self, api_key):
        from .models import System

        return System.objects.select_related("system_type").get(
            api_key=api_key, system_type__is_active=True
        )

    def extract_access_token(self, request):
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()

        if hasattr(request, "data"):
            access_token = request.data.get("access_token")
            if access_token:
                return access_token

        return request.GET.get("access_token")

    def decode_access_token(self, access_token, system):
        if hasattr(system, "jwt_secret") and system.jwt_secret:
            try:
                return jwt.decode(access_token, system.jwt_secret, algorithms=["HS256"])
            except jwt.InvalidTokenError as e:
                raise

        try:
            payload = jwt.decode(access_token, options={"verify_signature": False})
            return payload
        except jwt.InvalidTokenError:
            return json.loads(access_token)

    def get_user_from_payload(self, system, access_token_payload):
        from users.models import User

        email = access_token_payload.get("email")

        if not email:
            return None

        try:
            users = User.objects.filter(email=email)

            for user in users:
                if self.verify_user_system_association(user, system):
                    return user

            return None

        except Exception as e:
            return None

    def verify_user_system_association(self, user, system):
        try:

            if hasattr(user, "institutions_owned"):
                if user.institutions_owned.filter(system=system).exists():
                    return True

            if hasattr(user, "employee_profile"):
                employee = user.employee_profile
                if (
                    employee.work_branch
                    and employee.work_branch.institution.system == system
                ):
                    return True

            if hasattr(user, "profile") and user.profile.institution:
                if user.profile.institution.system == system:
                    return True

            return False

        except Exception as e:
            return False


class CustomAuthBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(
                Q(username__exact=username)
                | Q(email__iexact=username)
                | Q(employees__phone_number=username)
            )
            if user.check_password(password):
                return user
        except UserModel.DoesNotExist:
            return None
        except UserModel.MultipleObjectsReturned:
            return None
        return None

    def get_user(self, user_id):
        UserModel = get_user_model()
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None


class CustomJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        user_auth_tuple = super().authenticate(request)
        if user_auth_tuple is None:
            return None

        user, token = user_auth_tuple

        if user.session_id and token.get("session_id") != user.session_id:
            raise AuthenticationFailed(
                {
                    "code": "invalid_session",
                    "error": (
                        "We have detected a new sign-in to your account from another device."
                        "For your security, only one active session is allowed at a time, "
                        "so this session has been automatically signed out.\n\n"
                        "Please confirm if this was you, or reset your password to secure your account if it wasn't."
                    ),
                }
            )

        return user_auth_tuple
