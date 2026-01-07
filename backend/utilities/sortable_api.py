from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ObjectDoesNotExist

class SortableAPIMixin:
    allowed_ordering_fields = []
    default_ordering = None

    def apply_sorting(self, queryset, request):
        ordering = request.query_params.get('ordering', None)
        if ordering:
            ordering_fields = [field.strip() for field in ordering.split(',')]
            for field in ordering_fields:
                clean_field = field.lstrip('-')
                if clean_field not in self.allowed_ordering_fields:
                    raise ValueError({"error": f"Invalid ordering field '{clean_field}'. Must be one of {self.allowed_ordering_fields}."})
            return queryset.order_by(*ordering_fields)
        return queryset.order_by(*self.default_ordering) if self.default_ordering else queryset