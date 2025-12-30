"""
Ziraat Bankası API entegrasyonu için yardımcılar.

Not: Gerçek uç noktalar/değerler için https://developers.ziraatbank.com.tr/ dokümantasyonunu
inceleyin ve .env değişkenlerini doldurun. Env yoksa demo veri döner.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional

import requests


@dataclass
class ZiraatTransaction:
    date: datetime
    description: str
    amount: Decimal
    currency: str
    direction: str  # IN / OUT
    balance: Optional[Decimal] = None


class ZiraatAPIError(Exception):
    pass


def _parse_bool(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


def _demo_transactions() -> List[ZiraatTransaction]:
    today = datetime.now()
    return [
        ZiraatTransaction(
            date=today - timedelta(days=1, hours=2),
            description="EFT Tahsilat",
            amount=Decimal("15000.00"),
            currency="TRY",
            direction="IN",
            balance=Decimal("15000.00"),
        ),
        ZiraatTransaction(
            date=today - timedelta(days=1, hours=1),
            description="POS Bloke Çözümü",
            amount=Decimal("2200.00"),
            currency="TRY",
            direction="IN",
            balance=Decimal("17200.00"),
        ),
        ZiraatTransaction(
            date=today - timedelta(hours=5),
            description="Kira Ödemesi",
            amount=Decimal("8000.00"),
            currency="TRY",
            direction="OUT",
            balance=Decimal("9200.00"),
        ),
        ZiraatTransaction(
            date=today - timedelta(hours=1),
            description="Havale Müşteri",
            amount=Decimal("3500.00"),
            currency="TRY",
            direction="IN",
            balance=Decimal("12700.00"),
        ),
    ]


def fetch_transactions(
    account_iban: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
) -> List[ZiraatTransaction]:
    """
    Ziraat hesabı hareketlerini döndürür. Env ayarları:
    - ZIRAAT_API_BASE: örn. https://api.ziraatbank.com.tr
    - ZIRAAT_API_TOKEN: Bearer token (örnek: OAuth client_credentials sonrası)
    - ZIRAAT_ACCOUNT_IBAN: hedef IBAN
    - ZIRAAT_USE_DEMO: 1/true ise demo veri döner
    """
    use_demo = _parse_bool(os.getenv("ZIRAAT_USE_DEMO")) or not os.getenv("ZIRAAT_API_TOKEN")
    iban = account_iban or os.getenv("ZIRAAT_ACCOUNT_IBAN", "").replace(" ", "")
    base_url = os.getenv("ZIRAAT_API_BASE", "").rstrip("/")
    token = os.getenv("ZIRAAT_API_TOKEN", "")

    if use_demo or not (base_url and token and iban):
        return _demo_transactions()

    url = f"{base_url}/accounts/{iban}/transactions"
    params = {}
    if from_date:
        params["fromDate"] = from_date.strftime("%Y-%m-%d")
    if to_date:
        params["toDate"] = to_date.strftime("%Y-%m-%d")

    resp = requests.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        params=params,
        timeout=15,
    )
    if resp.status_code >= 400:
        raise ZiraatAPIError(f"API hata: {resp.status_code} {resp.text}")

    data = resp.json()
    items = []
    for row in data.get("transactions", []):
        amount = Decimal(str(row.get("amount", "0")))
        direction = "IN" if amount >= 0 else "OUT"
        items.append(
            ZiraatTransaction(
                date=datetime.fromisoformat(row.get("date")),
                description=row.get("description", ""),
                amount=abs(amount),
                currency=row.get("currency", "TRY"),
                direction=direction,
                balance=Decimal(str(row.get("balance"))) if row.get("balance") is not None else None,
            )
        )
    return items
