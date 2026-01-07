import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from assistant.utils import extract_database_schema


class Command(BaseCommand):
    help = "Extracts the database schema and sends it to the BAISOFT endpoint"

    def handle(self, *args, **options):
        endpoint = settings.BAISOFT_ASSISTANT_SCHEMA_URL
        api_key = settings.BAISOFT_ASSISTANT_API_KEY

        if not endpoint:
            self.stderr.write(self.style.ERROR("❌ Missing BAISOFT_SCHEMA_URL in .env"))
            return

        if not api_key:
            self.stderr.write(self.style.ERROR("❌ Missing BAISOFT_API_KEY in .env"))
            return

        self.stdout.write("🔍 Extracting database schema...")

        schema = extract_database_schema(
            exclude_tables=[
                "auth_user",
                "django_session",
                "systems_partnersystem",
                "django_site",
                "django_celery_beat_solarschedule",
                "django_celery_beat_intervalschedule",
                "django_celery_beat_clockedschedule",
                "django_celery_beat_crontabschedule",
                "django_celery_beat_periodictasks",
                "audit_auditlog",
                "django_admin_log",
                "auth_permission",
                "auth_group",
                "django_content_type",
                "token_blacklist_outstandingtoken",
                "token_blacklist_blacklistedtoken",
                "users_onetimepassword",
                "users_otpmodel",
            ]
        )

        if not isinstance(schema, dict) or "tables" not in schema:
            self.stderr.write(
                self.style.ERROR(
                    "❌ Invalid schema format returned by extract_database_schema()"
                )
            )
            return

        self.stdout.write(f"📤 Sending schema to {endpoint}...")

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

        try:
            response = requests.post(endpoint, headers=headers, json=schema, timeout=30)
            response.raise_for_status()
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"❌ Failed to send schema: {e}"))
            return

        self.stdout.write(self.style.SUCCESS("✅ Schema successfully sent!"))
        self.stdout.write(f"🌐 Response status: {response.status_code}")
        self.stdout.write(f"📝 Response body: {response.text}")
