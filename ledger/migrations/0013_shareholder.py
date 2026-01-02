from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ledger", "0012_transaction_account_none"),
    ]

    operations = [
        migrations.CreateModel(
            name="Shareholder",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                ("percent", models.DecimalField(max_digits=5, decimal_places=2)),
                ("active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["name"],
                "verbose_name": "Hissedar",
                "verbose_name_plural": "Hissedarlar",
            },
        ),
    ]
