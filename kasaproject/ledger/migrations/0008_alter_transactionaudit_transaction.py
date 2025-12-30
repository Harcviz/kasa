from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ledger", "0007_transaction_approved"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transactionaudit",
            name="transaction",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="audits",
                to="ledger.transaction",
            ),
        ),
    ]
