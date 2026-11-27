from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standardized page-number pagination across all list endpoints.
    Supports `?page=` and `?page_size=` up to `max_page_size = 100`.
    """
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 100
