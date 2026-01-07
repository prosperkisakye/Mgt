import requests
from django.core.management.base import BaseCommand
from django.conf import settings
import os
import json


class Command(BaseCommand):
    help = "Looks for SQL Examples JSON file and sends it to the BAISOFT endpoint"

    def handle(self, *args, **options):
        endpoint = settings.BAISOFT_ASSISTANT_SQL_EXAMPLES_URL
        api_key = settings.BAISOFT_ASSISTANT_API_KEY

        if not endpoint:
            self.stderr.write(
                self.style.ERROR(
                    "❌ Missing BAISOFT_ASSISTANT_SQL_EXAMPLES_URL in .env"
                )
            )
            return

        if not api_key:
            self.stderr.write(self.style.ERROR("❌ Missing BAISOFT_API_KEY in .env"))
            return

        self.stdout.write(
            "🔍 Looking for SQL file to update/create sql examples JSON file..."
        )

        from assistant.utils import parse_sql_file

        parse_sql_file(
            os.path.join(settings.BASE_DIR, "assistant", "fixtures", "examples.sql"),
            os.path.join(settings.BASE_DIR, "users", "fixtures", "sql_examples.json"),
        )

        self.stdout.write("🔍 Looking for SQL Examples JSON file...")

        examples = []

        sql_examples_file = os.path.join(
            settings.BASE_DIR, "users", "fixtures", "sql_examples.json"
        )

        if os.path.exists(sql_examples_file):
            try:
                with open(sql_examples_file, "r") as f:
                    text = f.read().strip()
                    if text:
                        examples = json.loads(text)

            except json.JSONDecodeError:
                print(f"Warning: Invalid JSON in metadata file: {sql_examples_file}")
        else:
            print(f"Warning: Metadata file not found: {sql_examples_file}")

        self.stdout.write(f"📤 Sending sql examples to {endpoint}...")

        headers = {
            "Content-Type": "application/json",
            "X-API-Key": api_key,
        }

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=examples,
                timeout=30,
            )
            response.raise_for_status()
        except requests.RequestException as e:
            self.stderr.write(self.style.ERROR(f"❌ Failed to send sql examples: {e}"))
            return

        self.stdout.write(self.style.SUCCESS("✅ SQL examples successfully sent!"))
        self.stdout.write(f"🌐 Response status: {response.status_code}")
        self.stdout.write(f"📝 Response body: {response.text}")
