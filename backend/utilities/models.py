from django.db import models
from django.utils import timezone
from crum import get_current_user
import uuid
from django.contrib.contenttypes.models import ContentType
from django.core import serializers


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class SoftDeletableTimeStampedModel(TimeStampedModel):
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        "users.CustomUser",
        related_name="%(app_label)s_%(class)s_creates",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        editable=False,
    )
    updated_by = models.ForeignKey(
        "users.CustomUser",
        related_name="%(app_label)s_%(class)s_updates",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    base_uuid = models.UUIDField(
        editable=True, blank=True, null=True, db_index=True, unique=True
    )


    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        user = get_current_user()

        if not self.base_uuid:
            self.base_uuid = self._generate_unique_base_uuid()

        if not self.pk and user and user.is_authenticated:
            self.created_by = user
        if user and user.is_authenticated:
            self.updated_by = user

        super().save(*args, **kwargs)

    def _generate_unique_base_uuid(self):
        model = self.__class__
        while True:
            candidate = str(uuid.uuid4())
            if not model.objects.filter(base_uuid=candidate).exists():
                return candidate

    def delete(self, *args, using_soft_delete=True, **kwargs):
        """
        Soft-delete by default.
        Pass ``using_soft_delete=False`` to perform a real DB delete.
        """

        if using_soft_delete:

            self.deleted_at = timezone.now()
            self.is_active = False

            self.save(update_fields=["deleted_at", "is_active"])

            user = get_current_user()

            institution = None
            if user and hasattr(user, "profile") and user.profile.institution:
                institution = user.profile.institution
                print(">>> Institution from user.profile:", institution)
            elif hasattr(self, "institution"):
                institution = getattr(self, "institution", None)
                print(">>> Institution from self.institution:", institution)

            # from settings.models import RecycleBin

            snapshot = self._get_snapshot()

            # recycle_entry = RecycleBin.objects.create(
            #     content_type=ContentType.objects.get_for_model(self),
            #     object_id=self.pk,
            #     deleted_by=get_current_user() or self.updated_by or self.created_by,
            #     institution=institution,
            #     data=snapshot,
            # )


        else:
            super().delete(*args, **kwargs)


    def _get_snapshot(self):
        """
        Returns a JSON string representing the current state of the instance
        using Django's built-in serializer.
        """
        return serializers.serialize("json", [self])[1:-1]