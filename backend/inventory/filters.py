import django_filters
from django.db.models import F

from .models import Product


class ProductFilter(django_filters.FilterSet):
    category__public_id = django_filters.UUIDFilter(field_name='category__public_id')
    low_stock = django_filters.BooleanFilter(method='filter_low_stock')

    class Meta:
        model = Product
        fields = ['category__public_id', 'low_stock']

    def filter_low_stock(self, queryset, name, value):
        if value is True:
            return queryset.filter(stock_quantity__lte=F('reorder_level'))
        if value is False:
            return queryset.filter(stock_quantity__gt=F('reorder_level'))
        return queryset
