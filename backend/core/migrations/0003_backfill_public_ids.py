import uuid

from django.db import migrations


def backfill_shop_public_ids(apps, schema_editor):
    Shop = apps.get_model('core', 'Shop')
    batch_size = 500
    shops_to_update = []
    for shop in Shop.objects.filter(public_id__isnull=True).iterator(chunk_size=batch_size):
        shop.public_id = uuid.uuid4()
        shops_to_update.append(shop)
        if len(shops_to_update) >= batch_size:
            Shop.objects.bulk_update(shops_to_update, ['public_id'])
            shops_to_update = []
    if shops_to_update:
        Shop.objects.bulk_update(shops_to_update, ['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_shop_public_id'),
    ]

    operations = [
        migrations.RunPython(backfill_shop_public_ids, reverse_code=migrations.RunPython.noop),
    ]
