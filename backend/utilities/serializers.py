from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType


class ContentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentType
        fields = ['id', 'app_label', 'model']
        read_only_fields = ['id', 'app_label', 'model']

class BaseModelSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField(read_only=True)
    updated_by = serializers.SerializerMethodField(read_only=True)

    class Meta:
        abstract = True
        extra_kwargs = {
            "created_by": {"required": False, "allow_null": True},
            "updated_by": {"required": False, "allow_null": True},
            
        }

    def _user_to_dict(self, user):
        if not user:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "name": user.fullname,
        }

    def get_created_by(self, obj):
        return self._user_to_dict(obj.created_by)

    def get_updated_by(self, obj):
        return self._user_to_dict(obj.updated_by)

    def to_representation(self, instance):
        """
        Override to ensure created_by/updated_by are always serialized via method fields,
        even when fields='__all__' is used in child serializers.
        """
        ret = super().to_representation(instance)

        # Re-inject rich user data *after* default serialization
        if hasattr(instance, 'created_by'):
            ret['created_by'] = self.get_created_by(instance)
        if hasattr(instance, 'updated_by'):
            ret['updated_by'] = self.get_updated_by(instance)

        return ret

    def create(self, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        if user:
            validated_data.setdefault("created_by", user)
            validated_data.setdefault("updated_by", user)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        request = self.context.get("request")
        user = request.user if request and request.user.is_authenticated else None
        if user:
            validated_data["updated_by"] = user
        return super().update(instance, validated_data)