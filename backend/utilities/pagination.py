from django.conf import settings
from rest_framework.pagination import PageNumberPagination


class CustomPageNumberPagination(PageNumberPagination):
    page_size_query_param = "page_size"
    max_page_size = 250

    def _get_page_size(self, obj):
        if obj and hasattr(obj, 'default_pagination_page_size'):
                val = obj.default_pagination_page_size
                if val and val > 0:
                     return val
                return None
        
    def get_page_size(self, request):   
        try:
            requested = super().get_page_size(request)
            if requested is not None:
                return min(requested, self.max_page_size)
        except (ValueError, TypeError):
            pass  

        if not request.user.is_authenticated:
             return getattr(settings, 'DEFAULT_PAGINATION_PAGE_SIZE')
               
        try:
            employee = request.user.employees.first()
            if employee:
                page_size = self._get_page_size(employee)
                if page_size:
                    return min(page_size, self.max_page_size)
                  
                branch = employee.work_branch
                if branch:
                    page_size = self._get_page_size(branch)
                    if page_size:
                        return min(page_size, self.max_page_size)
                    
                    if branch.institution:
                        page_size =self._get_page_size(branch.institution)
                        if page_size:
                            return min(page_size, self.max_page_size)
                        
            institution = request.user.institutions_owned.first()
            if institution:
                page_size = self._get_page_size(institution)
                if page_size:
                    return min(page_size, self.max_page_size)

        except Exception:
            pass  

        return getattr(settings, 'DEFAULT_PAGINATION_PAGE_SIZE', 10)                  
