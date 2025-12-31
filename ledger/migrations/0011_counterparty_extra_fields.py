from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0010_alter_transaction_direction"),
    ]

    operations = [
        migrations.AddField(
            model_name="counterparty",
            name="tax_id",
            field=models.CharField(blank=True, max_length=30),
        ),
        migrations.AddField(
            model_name="counterparty",
            name="address",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="counterparty",
            name="iban",
            field=models.CharField(blank=True, max_length=34),
        ),
        migrations.AddField(
            model_name="counterparty",
            name="contact_person",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="counterparty",
            name="website",
            field=models.CharField(blank=True, max_length=200),
        ),
    ]
