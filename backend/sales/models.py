from django.db import models

from core.models import ShopAwareModel, User
from inventory.models import Product


class Customer(ShopAwareModel):
    """
    Represents a client or wholesale customer of a shop.

    WHY:
    Tracks individual customer details and their cumulative credit balance.
    Walk-in retail customers don't require a record, but anyone taking items on
    credit (Pay Later) MUST be registered as a Customer.
    """
    name = models.CharField(
        max_length=255,
        help_text="Full name of customer or client business."
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact number for SMS/WhatsApp invoice delivery and credit reminders."
    )
    address = models.TextField(
        blank=True,
        help_text="Billing or delivery address."
    )
    total_credit_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Current outstanding debt owed by the customer to this shop."
    )

    class Meta:
        verbose_name = 'Customer'
        verbose_name_plural = 'Customers'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.phone or 'No Phone'}) - Debt: Rs. {self.total_credit_balance}"


class Invoice(ShopAwareModel):
    """
    Header record for a POS sale / transaction.

    WHY:
    Represents the financial receipt for a completed checkout.
    """
    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        CARD = 'CARD', 'Card'
        CREDIT = 'CREDIT', 'Store Credit (Pay Later)'
        MIXED = 'MIXED', 'Split / Mixed Payment'

    invoice_number = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Sequential human-readable invoice identifier (unique per shop)."
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoices',
        help_text="Customer receiving this invoice. Can be null for walk-in retail sales."
    )
    cashier = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='sales_handled',
        help_text="Staff member who processed the checkout."
    )
    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Gross total of all items before discounts."
    )
    discount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Total discount deducted from the sale."
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Net payable amount (subtotal - discount)."
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
        help_text="Method used for settling the bill."
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Amount received in cash/card at the time of checkout."
    )
    credit_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0.00,
        help_text="Unpaid balance added to customer's credit ledger (if applicable)."
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional remarks or customer notes."
    )

    class Meta:
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-created_at']
        unique_together = ('shop', 'invoice_number')

    def __str__(self):
        return f"{self.invoice_number} - Rs. {self.total_amount} ({self.get_payment_method_display()})"


class InvoiceItem(ShopAwareModel):
    """
    Individual line item in an Invoice.

    WHY cost_price_at_sale:
    Wholesale product costs change over time due to inflation or new supplier batches.
    We snapshot the exact cost price at the moment of checkout so historic gross margin
    reports remain 100% accurate forever, even if product.cost_price changes tomorrow.
    """
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='items',
        help_text="The parent invoice."
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name='sale_items',
        help_text="Product sold. PROTECT prevents accidental deletion of items with sales history."
    )
    quantity = models.PositiveIntegerField(
        default=1,
        help_text="Number of units purchased."
    )
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Selling price per unit at the time of checkout."
    )
    cost_price_at_sale = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Snapshot of the wholesale cost per unit at sale time for accurate profit calculation."
    )
    line_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Total for this line item (quantity * unit_price)."
    )

    class Meta:
        verbose_name = 'Invoice Item'
        verbose_name_plural = 'Invoice Items'
        ordering = ['id']

    def __str__(self):
        return f"{self.product.name} x {self.quantity} (@ Rs. {self.unit_price})"


class CreditPayment(ShopAwareModel):
    """
    Represents a payment made by a customer to settle their outstanding store credit debt.
    """
    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        CHEQUE = 'CHEQUE', 'Cheque'

    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='credit_payments',
        help_text="Customer paying off their credit balance."
    )
    amount_paid = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Amount paid towards settling credit debt."
    )
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH
    )
    notes = models.TextField(
        blank=True,
        help_text="Bank reference, deposit slip number, or notes."
    )
    received_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name='credit_payments_received',
        help_text="Staff member who received the payment."
    )

    class Meta:
        verbose_name = 'Credit Payment'
        verbose_name_plural = 'Credit Payments'
        ordering = ['-created_at']

    def __str__(self):
        return f"Credit Payment: {self.customer.name} - Rs. {self.amount_paid}"


class PDCheque(ShopAwareModel):
    """
    Tracks Post-Dated (PD) Cheques received from customers for credit or wholesale transactions.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Deposit'
        DEPOSITED = 'DEPOSITED', 'Deposited at Bank'
        CLEARED = 'CLEARED', 'Cleared (Funds Realized)'
        BOUNCED = 'BOUNCED', 'Bounced / Returned'

    customer = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pd_cheques',
        help_text="Customer who issued the cheque."
    )
    cheque_number = models.CharField(
        max_length=50,
        help_text="Cheque leaf number."
    )
    bank_name = models.CharField(
        max_length=100,
        help_text="Issuing bank & branch (e.g. Commercial Bank - Colombo 03)."
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Face value amount of the cheque."
    )
    due_date = models.DateField(
        help_text="The date on which the cheque can be deposited at the bank."
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
        help_text="Current clearance status of the cheque."
    )
    notes = models.TextField(
        blank=True,
        help_text="Remarks regarding deposit date, clearance reference, or bounce reason."
    )

    class Meta:
        verbose_name = 'Post-Dated Cheque'
        verbose_name_plural = 'Post-Dated Cheques'
        ordering = ['due_date']

    def __str__(self):
        return f"Cheque #{self.cheque_number} ({self.bank_name}) - Rs. {self.amount} [{self.get_status_display()}]"
