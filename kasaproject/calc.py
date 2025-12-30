from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

from models import DistributionResult, ResultRow, Shareholder

TWOPLACES = Decimal("0.01")


class DistributionError(Exception):
    pass


def _quantize(val: Decimal) -> Decimal:
    return val.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def validate_shareholders(holders: List[Shareholder]) -> None:
    total_pct = sum((h.percent for h in holders), Decimal("0"))
    if total_pct != Decimal("100"):
        raise DistributionError(f"Hissedar yüzdeleri 100 değil: {total_pct}")


def compute_distribution(
    month: str,
    holders: List[Shareholder],
    total_cash: Decimal,
    keep_cash: Decimal,
    advances: Dict[str, Decimal],
    carry: Dict[str, Decimal],
) -> DistributionResult:
    validate_shareholders(holders)
    if keep_cash < 0:
        raise DistributionError("Kasada bırakılacak tutar negatif olamaz.")
    distributable = total_cash - keep_cash
    if distributable < 0:
        raise DistributionError("Dağıtılabilir kasa negatif olamaz.")

    entitlements: Dict[str, Decimal] = {}
    rows: List[ResultRow] = []

    for h in holders:
        entitlements[h.name.lower()] = distributable * h.percent / Decimal("100")

    raw_balances: Dict[str, Decimal] = {}
    total_positive = Decimal("0")
    for h in holders:
        name_key = h.name.lower()
        hak = entitlements[name_key]
        avans = advances.get(h.name, advances.get(name_key, Decimal("0")))
        prev_carry = carry.get(h.name, carry.get(name_key, Decimal("0")))
        raw = hak - avans + prev_carry
        raw_balances[name_key] = raw
        if raw > 0:
            total_positive += raw

    scale = Decimal("1")
    if total_positive > distributable and total_positive > 0:
        scale = distributable / total_positive

    total_paid = Decimal("0")
    for h in holders:
        name_key = h.name.lower()
        hak = entitlements[name_key]
        avans = advances.get(h.name, advances.get(name_key, Decimal("0")))
        prev_carry = carry.get(h.name, carry.get(name_key, Decimal("0")))
        raw = raw_balances[name_key]
        pay = raw if raw > 0 else Decimal("0")
        if scale < 1:
            pay = pay * scale
        pay = _quantize(pay)
        new_carry = raw - pay
        total_paid += pay
        rows.append(
            ResultRow(
                name=h.name,
                percent=h.percent,
                entitlement=_quantize(hak),
                advance=_quantize(avans),
                prev_carry=_quantize(prev_carry),
                paid=pay,
                new_carry=_quantize(new_carry),
            )
        )

    total_entitlement = _quantize(sum(entitlements.values(), Decimal("0")))
    total_paid = _quantize(total_paid)
    return DistributionResult(
        month=month,
        distributable=_quantize(distributable),
        rows=rows,
        total_entitlement=total_entitlement,
        total_paid=total_paid,
    )
