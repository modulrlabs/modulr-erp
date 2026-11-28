import uuid

from django.db import migrations


def backfill_inventory_public_ids(apps, schema_editor):
    Category = apps.get_model('inventory', 'Category')
    Product = apps.get_model('inventory', 'Product')
    batch_size = 500

    # Backfill Categories
    categories_to_update = []
    for cat in Category.objects.filter(public_id__isnull=True).iterator(chunk_size=batch_size):
        cat.public_id = uuid.uuid4()
        categories_to_update.append(cat)
        if len(categories_to_update) >= batch_size:
            Category.objects.bulk_update(categories_to_update, ['public_id'])
            categories_to_update = []
    if categories_to_update:
        Category.objects.bulk_update(categories_to_update, ['public_id'])

    # Backfill Products
    products_to_update = []
    for prod in Product.objects.filter(public_id__isnull=True).iterator(chunk_size=batch_size):
        prod.public_id = uuid.uuid4()
        products_to_update.append(prod)
        if len(products_to_update) >= batch_size:
            Product.objects.bulk_update(products_to_update, ['public_id'])
            products_to_update = []
    if products_to_update:
        Product.objects.bulk_update(products_to_update, ['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0002_category_public_id_product_public_id'),
    ]

    operations = [
        migrations.RunPython(backfill_inventory_public_ids, reverse_code=migrations.RunPython.noop),
    ]
