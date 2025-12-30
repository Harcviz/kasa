from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List


@dataclass
class Shareholder:
    name: str
    percent: Decimal  # 0-100


@dataclass
class LedgerEntry:
    month: str  # YYYY-MM
    total_cash: Decimal
    keep_cash: Decimal
    advances: Dict[str, Decimal]


@dataclass
class CarryState:
    balances: Dict[str, Decimal]


@dataclass
class ResultRow:
    name: str
    percent: Decimal
    entitlement: Decimal
    advance: Decimal
    prev_carry: Decimal
    paid: Decimal
    new_carry: Decimal


@dataclass
class DistributionResult:
    month: str
    distributable: Decimal
    rows: List[ResultRow]
    total_entitlement: Decimal
    total_paid: Decimal
