from django.core.management.base import BaseCommand
from devices.helpers import (
    create_attendance_for_employees_without_today,
    update_yesterdays_checkout_times,
)
from spotcheck.utilities import process_spotchecks_for_today


class Command(BaseCommand):
    help = "Syncs attendance and spotchecks by updating checkout times and creating new records."

    def handle(self, *args, **options):
        # Run all sync processes
        update_yesterdays_checkout_times()
        create_attendance_for_employees_without_today()
        process_spotchecks_for_today()

        self.stdout.write(
            self.style.SUCCESS(
                "✅ Attendance and spotchecks sync completed successfully."
            )
        )
