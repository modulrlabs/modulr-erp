import uuid

from django.db import migrations


def backfill_sales_public_ids(apps, schema_editor):
    Customer = apps.get_model('sales', 'Customer')
    Invoice = apps.get_model('sales', 'Invoice')
    InvoiceItem = apps.get_model('sales', 'InvoiceItem')
    CreditPayment = apps.get_model('sales', 'CreditPayment')
    PDCheque = apps.get_model('sales', 'PDCheque')
    batch_size = 500

    models_to_backfill = [Customer, Invoice, InvoiceItem, CreditPayment, PDCheque]

    for model in models_to_backfill:
        to_update = []
        for instance in model.objects.filter(public_id__isnull=True).iterator(chunk_size=batch_size):
            instance.public_id = uuid.uuid4()
            to_update.append(instance)
            if len(to_update) >= batch_size:
                model.objects.bulk_update(to_update, ['public_id'])
                to_update = []
        if to_update:
            model.objects.bulk_update(to_update, ['public_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('sales', '0002_creditpayment_public_id_customer_public_id_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_sales_public_ids, reverse_code=migrations.RunPython.noop),
    ]
