from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0008_alter_transactionaudit_transaction"),
    ]

    operations = [
        migrations.CreateModel(
            name="CashCategory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("direction", models.CharField(choices=[("IN", "Gelir"), ("OUT", "Gider")], max_length=3)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Nakit Kasa Kalemi",
                "verbose_name_plural": "Nakit Kasa Kalemleri",
                "ordering": ["name"],
                "unique_together": {("name", "direction")},
            },
        ),
    ]

