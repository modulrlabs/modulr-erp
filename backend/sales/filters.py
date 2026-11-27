import django_filters

from .models import Customer, Invoice, PDCheque


class InvoiceFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name='status', lookup_expr='iexact')
    payment_method = django_filters.CharFilter(field_name='payment_method', lookup_expr='iexact')
    date_from = django_filters.DateFilter(field_name='created_at__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='created_at__date', lookup_expr='lte')
    customer = django_filters.NumberFilter(field_name='customer_id')

    class Meta:
        model = Invoice
        fields = ['status', 'payment_method', 'date_from', 'date_to', 'customer']


class CustomerFilter(django_filters.FilterSet):
    has_credit = django_filters.BooleanFilter(method='filter_has_credit')

    class Meta:
        model = Customer
        fields = ['has_credit']

    def filter_has_credit(self, queryset, name, value):
        if value is True:
            return queryset.filter(total_credit_balance__gt=0)
        if value is False:
            return queryset.filter(total_credit_balance__lte=0)
        return queryset


class PDChequeFilter(django_filters.FilterSet):
    status = django_filters.CharFilter(field_name='status', lookup_expr='iexact')
    due_from = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_to = django_filters.DateFilter(field_name='due_date', lookup_expr='lte')

    class Meta:
        model = PDCheque
        fields = ['status', 'due_from', 'due_to']
