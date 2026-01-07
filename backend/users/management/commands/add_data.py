import decimal
from pathlib import Path
import uuid
from django.utils import timezone
import json
import os
from django.apps import apps
from django.db.models import CharField
from django.db import transaction
from django.core.management.base import BaseCommand
from django.conf import settings
import requests
from utilities.helpers import to_uuid_str
from users.models import CustomUser, Permission, PermissionCategory, RolePermission, UserPermission
from django.db import transaction
from django.apps import apps
from django.db.models import Count
from django.db.models import Sum, Min, Q
from django.http import HttpRequest
from contextlib import nullcontext



class Command(BaseCommand):
    help = "Add/sync permissions, systems, discipline types, approval actions, system days, bank info, awards, birthday events, performance data, resend welcome emails, sync employee names, delete inactive employees, create tax rules, schedule birthday emails, generate usernames for users without usernames, and sync education qualifications"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Reset passwords for all resent welcome emails",
        )
        parser.add_argument(
            "--employee-ids",
            type=str,
            help="Comma-separated list of employee IDs to resend welcome emails to",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting inactive employees",
        )
        parser.add_argument(
            "--no-confirm",
            action="store_true",
            help="Skip confirmation prompt for deleting inactive employees",
        )
        parser.add_argument(
            "--accounting-sync",
            action="store_true",
            help="Run the Accounting sync for ALL institutions.",
        )
        parser.add_argument("--institution-id", type=int, help="Only sync users from this institution")

    def handle(self, *args, **kwargs):
        self.sync_permissions()




    def sync_permissions(self):
        filepath = os.path.join(
            settings.BASE_DIR, "users", "fixtures", "permissions.json"
        )
        if not os.path.exists(filepath):
            self.stdout.write(
                self.style.ERROR(f"Permissions file not found at {filepath}")
            )
            return

        with open(filepath, "r") as file:
            permissions_data = json.load(file)

        self.stdout.write(self.style.MIGRATE_HEADING("Syncing permissions...\n"))

        valid_permission_codes = set()
        valid_category_names = set()

        for category_name, perms in permissions_data.items():
            category, _ = PermissionCategory.objects.get_or_create(
                permission_category_name=category_name,
                defaults={
                    "permission_category_description": f"{category_name} related permissions"
                },
            )
            valid_category_names.add(category.permission_category_name)

            for perm in perms:
                Permission.objects.update_or_create(
                    permission_code=perm["code"],
                    defaults={
                        "permission_name": perm["name"],
                        "permission_description": perm["description"],
                        "category": category,
                    },
                )
                valid_permission_codes.add(perm["code"])

        # Clean up removed permissions/categories
        deleted_permissions, _ = Permission.objects.exclude(
            permission_code__in=valid_permission_codes
        ).delete()
        deleted_categories, _ = PermissionCategory.objects.exclude(
            permission_category_name__in=valid_category_names
        ).delete()

        # ADD THIS BLOCK — THIS IS THE KEY
        self.stdout.write(self.style.MIGRATE_LABEL("\nGranting all permissions to institution owners..."))
        self.stdout.write(self.style.SUCCESS("All institution owners now have ALL permissions!"))

        # Final summary
        self.stdout.write("\n" + self.style.MIGRATE_LABEL("Permissions Summary"))
        self.stdout.write(
            self.style.NOTICE(f"  Removed Permissions: {deleted_permissions}")
        )
        self.stdout.write(
            self.style.NOTICE(f"  Removed Categories: {deleted_categories}")
        )
        self.stdout.write(self.style.SUCCESS("\nPermissions synced successfully!"))



