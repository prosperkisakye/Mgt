from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from communication.views import cleanup_queue  # Adjust import based on your project structure
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Deletes all notifications for all users in Redis.'

    def handle(self, *args, **options):
        User = get_user_model()
        users = User.objects.all()
        total_users = users.count()
        deleted_queues = 0

        self.stdout.write(f"Found {total_users} users. Starting notification cleanup...")

        for user in users:
            try:
                cleanup_queue(user_id=user.id)
                logger.info(f"Cleared notifications for user {user.id}")
                deleted_queues += 1
                self.stdout.write(f"Cleared notifications for user {user.id}")
            except Exception as e:
                logger.error(f"Failed to clear notifications for user {user.id}: {str(e)}")
                self.stdout.write(self.style.ERROR(f"Failed to clear notifications for user {user.id}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"Completed cleanup. Cleared notifications for {deleted_queues}/{total_users} users."))