from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import uuid
from django.utils import timezone
from django.http import HttpResponseForbidden
from functools import wraps
import hashlib
from users.models import CustomUser, OneTimePassword, UserPermission
from django.conf import settings
import logging
import secrets
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import send_mail
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist
from typing import Any
from django.db import transaction
from typing import Dict, Any, List
from django.utils.text import camel_case_to_spaces
import colorsys
import hashlib

logger = logging.getLogger(__name__)

from users.models import Role, RolePermission, Permission, UserRole


def custom_parse_date(value: str):
    if not value:
        return None

    value = value.strip().replace("“", "").replace("”", "")

    if " " in value:
        value = value.split()[0]

    formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError("Invalid date format. Use YYYY-MM-DD, YYYY/MM/DD, or YYYY.MM.DD")


def get_gender_salutation(user):
    """
    Returns appropriate salutation based on user's gender.

    Args:
        user: User object with gender field

    Returns:
        str: Appropriate salutation (Mr., Ms., or empty string)
    """
    if not hasattr(user, "gender") or not user.gender:
        return ""

    gender_salutations = {
        "male": "Mr.",
        "female": "Ms.",
        "other": "Mr./Ms."
    }

    return gender_salutations.get(user.gender.lower(), "")


def get_personalized_greeting(user):
    """
    Returns a personalized greeting with salutation and name.

    Args:
        user: User object with gender and fullname fields

    Returns:
        str: Personalized greeting like "Mr. John Doe" or "Ms. Jane Smith"
    """
    salutation = get_gender_salutation(user)
    fullname = getattr(user, "fullname", "there")

    if salutation:
        return f"{salutation} {fullname}"
    return fullname


def get_or_create_default_role_with_permissions(institution):
    role, created = Role.objects.get_or_create(
        name="normal employee role",
        institution=institution,
        defaults={
            "description": "Default role for new employees",
        },
    )

    if created:
        default_permission_codes = [
            "can_view_employee_personal_data",
        ]

        default_permissions = Permission.objects.filter(
            permission_code__in=default_permission_codes
        )

        RolePermission.objects.bulk_create(
            [RolePermission(role=role, permission=perm) for perm in default_permissions]
        )

    return role


def send_activation_confirmation_email(
    owner_fullname,
    owner_email,
    institution_name,
    branches,
    departments,
    employees,
    owner_user=None,
):
    """
    Sends an email to the owner confirming the activation of the institution.
    """

    try:
        subject = "Perrac Module Activation Confirmation"

        # Get personalized greeting if user object is available
        if owner_user:
            personalized_name = get_personalized_greeting(owner_user)
        else:
            personalized_name = owner_fullname

        context = {
            "owner_full_name": personalized_name,
            "owner_email": owner_email,
            "institution_name": institution_name,
            "branches": len(branches),
            "departments": len(departments),
            "employees": len(employees),
            "year": timezone.now().year,
        }

        # Render HTML template
        html_message = render_to_string("activation-emails/perrac.html", context)
        plain_message = strip_tags(html_message)

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[owner_email],
            html_message=html_message,
        )
        logger.info(f"Activation confirmation email sent to {owner_email}")
        return True

    except Exception as e:
        logger.error(f"Error sending activation confirmation email: {e}")
        raise e


def permission_required(perm_name):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated or not request.user.has_permission(
                perm_name
            ):
                return HttpResponseForbidden("Forbidden")
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator


def generate_otp(length=6):
    return "".join(secrets.choice("0123456789") for _ in range(length))


def hash_otp(user_id, otp):
    raw_string = f"{user_id}-{otp}"
    return hashlib.sha256(raw_string.encode()).hexdigest()


def create_and_institution_otp(user_id, purpose=None, expiry_minutes=15) -> str:
    otp = generate_otp()
    otp_hash = hash_otp(user_id, otp)

    expiry_time = timezone.now() + timedelta(minutes=expiry_minutes)

    if purpose:
        cleanup_existing_otps(user_id, purpose)

    OneTimePassword.objects.create(
        otp_hash=otp_hash, expiry=expiry_time, purpose=purpose
    )

    return otp


def cleanup_existing_otps(user_id, purpose):
    if purpose:
        OneTimePassword.objects.filter(purpose=purpose, is_used=False).delete()


def cleanup_expired_otps():
    """
    Utility function to clean up expired OTPs
    This can be called periodically via a scheduled task
    """
    now = timezone.now()
    deleted_count, _ = OneTimePassword.objects.filter(expiry__lt=now).delete()
    return deleted_count

def parse_int_list(values):
    if not values:
        return []
    try:
        return [int(v) for v in values if v.strip()]
    except ValueError:
        return None
    
def parse_id_param(request, param_name):
    """
    Safely parse a query param that can be:
    - Repeated: ?branch_ids=4&branch_ids=15
    - Comma-separated: ?branch_ids=4,15
    - Single value: ?branch_ids=4
    Returns list of integers or None on invalid format.
    """
    # 1. Try repeated params first
    values = request.query_params.getlist(param_name)
    if not values:
        return []

    # If multiple values → already split
    if len(values) > 1:
        try:
            return [int(v.strip()) for v in values if v.strip()]
        except ValueError:
            return None

    # 2. Single value: check if comma-separated
    single_value = values[0]
    if ',' in single_value:
        parts = [part.strip() for part in single_value.split(',') if part.strip()]
        try:
            return [int(p) for p in parts]
        except ValueError:
            return None
    else:
        # Single numeric value
        try:
            return [int(single_value.strip())] if single_value.strip() else []
        except ValueError:
            return None    


def verify_otp(identifier, received_otp):
    otp_hash = hash_otp(identifier, received_otp)
    logger.debug(f"Verifying OTP hash: {otp_hash}")

    try:
        otp_entry = OneTimePassword.objects.get(otp_hash=otp_hash, is_used=False)

        if otp_entry.is_expired():
            logger.warning(f"OTP expired for hash: {otp_hash}")
            return False, "OTP has expired"

        otp_entry.delete()
        logger.info(f"OTP verified and deleted successfully for hash: {otp_hash}")
        return True, "OTP verified successfully"

    except OneTimePassword.DoesNotExist:
        logger.warning(f"Invalid OTP attempt with hash: {otp_hash}")
        return False, "Invalid OTP"


def send_plain_email(receivers, subject, body, fail_silently=False):
    """
    Send plain text email to list of receivers using Gmail SMTP

    Args:
        receivers: List of email addresses or single email address as string
        subject: Email subject
        body: Plain text email body
        fail_silently: If True, exceptions will be suppressed

    Returns:
        Number of successfully sent emails (0 or 1)
    """
    if isinstance(receivers, str):
        receivers = [receivers]

    try:
        num_sent = send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=receivers,
            fail_silently=fail_silently,
        )

        if num_sent > 0:
            logger.info(f"Email sent to {receivers} with subject: {subject}")
        else:
            logger.warning(f"Email failed to send to {receivers}")

        return num_sent

    except Exception as e:
        if not fail_silently:
            raise
        return 0

def send_email_to_user(user, subject, message):
    return send_otp_to_user(user, None, subject, message)


def send_otp_to_user(
    user,
    otp=None,
    subject="Verify Your Account",
    message="Thank you for using Peracosoft. Please use the verification code below to verify access to your account",
    institution=None
):
    context = {
        "subject": subject,
        "user": user,
        "otp_code": otp,
        "year": timezone.now().year,
        "message": message,
        "personalized_greeting": get_personalized_greeting(user),
    }

    html_message = render_to_string("users/emails/signup_otp_verification.html", context)
    plain_message = strip_tags(html_message)

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )   

    return True


def build_password_link(request, token: str) -> str:
    frontend_origin = request.headers.get("Origin")
    if frontend_origin:
        parts = urlparse(frontend_origin)
        base_link = f"{parts.scheme}://{parts.netloc}"
    else:
        base_link = f"{request.scheme}://{request.get_host()}"

    return f"{base_link.rstrip('/')}/reset-password/{token}"


def create_and_institution_token(user, purpose="registration", expiry_minutes=15):
    from users.models import OTPModel

    token = secrets.token_urlsafe(32)
    OTPModel.objects.create(
        user=user,
        value=token,
        purpose=purpose,
        expires_at=timezone.now() + timedelta(minutes=expiry_minutes),
    )
    return token

ACCOUNTING_PERMISSION_CODE = "can_access_accounting_module"


def user_has_accounting_permission(user: CustomUser) -> bool:
    """
    Returns True if the user has the permission either:
      • directly (UserPermission)
      • via a Role (UserRole → RolePermission)
    """
    return (
        UserPermission.objects.filter(
            user=user, permission__permission_code=ACCOUNTING_PERMISSION_CODE
        ).exists()
        or user.user_roles.filter(
            role__permissions__permission__permission_code=ACCOUNTING_PERMISSION_CODE
        ).exists()
    )


def send_password_link_to_user(user, link):
    subject = "Set Your Password"
    context = {
        "link": link,
        "user": user,
        "fullname": user.fullname,
        "year": timezone.now().year,
        "personalized_greeting": get_personalized_greeting(user),
    }
    html_message = render_to_string(
        "institutions/emails/signup_link_email.html", context
    )
    plain_message = strip_tags(html_message)

    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
    )
    return True


def send_password_reset_link_to_user(user, link):
    try:
        subject = "Reset Your Password"
        context = {
            "link": link,
            "user": user,
            "year": timezone.now().year,
            "personalized_greeting": get_personalized_greeting(user),
        }
        html_message = render_to_string("forgot-password/password-reset.html", context)
        plain_message = strip_tags(html_message)

        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
        )
        return True
    except Exception as e:
        return False


accounts_increased_by_debits = [
    "ASSET",
    "EXPENSE",
]

accounts_increased_by_credits = [
    "LIABILITY",
    "EQUITY",
    "REVENUE",
]


def get_system_parameter(code):
    ...
    # return SystemParameters.objects.get(code=code)


def get_accounting_permission():
    """
    Returns the Permission object for 'can_access_accounting_module'.
    Cached for performance.
    """
    try:
        return Permission.objects.get(codename="can_access_accounting_module")
    except Permission.DoesNotExist:
        raise ObjectDoesNotExist(
            "Permission 'can_access_accounting_module' does not exist. "
            "Create it in Django admin or via migration."
        )
    
def to_uuid_str(value: Any) -> str:
    """
    Safely turn a UUID, a string that looks like a UUID, or a model
    that has an ``base_uuid`` (or ``id``) into a string.

    Raises a clear error if the value cannot be converted.
    """
    if value is None:
        raise ValueError("to_uuid_str received None – a UUID is required")

    # 1. Already a UUID instance
    if isinstance(value, uuid.UUID):
        return str(value)

    # 2. String – validate it is a real UUID
    if isinstance(value, str):
        try:
            uuid.UUID(value)          # will raise ValueError if invalid
            return value
        except ValueError as exc:
            raise ValueError(f"'{value}' is not a valid UUID string") from exc

    # 3. Model instance – look for common UUID fields
    if hasattr(value, "base_uuid") and value.base_uuid:
        return str(value.base_uuid)

    if hasattr(value, "id"):
        return str(value.id)

    raise TypeError(f"Cannot convert {type(value)!r} to UUID string")


def _uuid(value) -> uuid.UUID:
    return uuid.UUID(value) if not isinstance(value, uuid.UUID) else value


def get_level_color(level: int) -> str:
    """
    Generates a consistent, visually distinct, beautiful color for any level number.
    Same level → always same color (deterministic via hash)
    """
    hue_seed = int(hashlib.md5(f"approval_level_{level}_v2".encode()).hexdigest(), 16)
    hue = (hue_seed % 360) / 360.0  

    saturation = 0.70   
    lightness = 0.55    

    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"

def to_decimal(value, default=Decimal('0')):
    """Safely convert any value to Decimal."""
    if value is None:
        return default
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return default  
    
def fingerprint(request) -> str:
    ip = request.META.get("REMOTE_ADDR", "")
    ua = request.META.get("HTTP_USER_AGENT", "")
    return hashlib.md5(f"{ip}:{ua}".encode()).hexdigest()

from rest_framework.response import Response

def error_response(message: str, status_code: int = 400):
    """Return only {'error': 'Your message'}"""
    return Response({"error": message}, status=status_code)

def throttled(self, request, wait):
        mins = wait // 60
        secs = wait % 60
        if mins > 0:
            time_str = f"{mins} minute{'s' if mins != 1 else ''}"
            if secs:
                time_str += f" and {secs} second{'s' if secs != 1 else ''}"
        else:
            time_str = f"{secs} second{'s' if secs != 1 else ''}"

        return error_response(f"Too many attempts. Try again in {time_str}.", 429)


_model_name_cache = {}

def humanize_model_name(content_type):
    """
    Turn a ContentType (or model class) into a nice readable string.
    Examples:
        "worktype"          → "Work Type"
        "myapp.mymodel"     → "My Model"
        "MyApp.MyModel"     → "My Model"
    """
    if not content_type:
        return ""

    model = content_type.model_class()
    if not model:
        return content_type.model.title()

    key = f"{model._meta.app_label}.{model._meta.object_name}"
    if key in _model_name_cache:
        return _model_name_cache[key]

    raw = model._meta.object_name
    pretty = camel_case_to_spaces(raw).title()
    _model_name_cache[key] = pretty
    return pretty


