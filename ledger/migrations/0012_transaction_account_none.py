from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0011_counterparty_extra_fields"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="account",
            field=models.CharField(
                choices=[("CASH", "Nakit"), ("BANK", "Banka"), ("NONE", "Kasa dışı")],
                max_length=5,
            ),
        ),
    ]
