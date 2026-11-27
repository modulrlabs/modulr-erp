import django_filters

from .models import AuditLog


class AuditLogFilter(django_filters.FilterSet):
    action = django_filters.CharFilter(field_name='action', lookup_expr='iexact')
    actor__public_id = django_filters.UUIDFilter(field_name='actor__public_id')
    target_model = django_filters.CharFilter(field_name='target_model', lookup_expr='iexact')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')

    class Meta:
        model = AuditLog
        fields = ['action', 'actor__public_id', 'target_model', 'date_from', 'date_to']
