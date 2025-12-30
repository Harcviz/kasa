from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Dict, List

from models import CarryState, LedgerEntry, Shareholder

ROOT = Path(".")
SHAREHOLDER_FILE = ROOT / "shareholders.json"
LEDGER_FILE = ROOT / "ledger.json"
CARRY_FILE = ROOT / "carry.json"


def _to_decimal_map(raw: Dict[str, str]) -> Dict[str, Decimal]:
    return {k: Decimal(str(v)) for k, v in raw.items()}


def _decimal_to_str_map(raw: Dict[str, Decimal]) -> Dict[str, str]:
    return {k: str(v) for k, v in raw.items()}


def load_shareholders() -> List[Shareholder]:
    if not SHAREHOLDER_FILE.exists():
        raise FileNotFoundError("shareholders.json bulunamadı.")
    data = json.loads(SHAREHOLDER_FILE.read_text(encoding="utf-8"))
    holders = []
    for item in data:
        holders.append(Shareholder(name=item["name"], percent=Decimal(str(item["percent"]))))
    return holders


def save_shareholders(holders: List[Shareholder]) -> None:
    payload = [{"name": h.name, "percent": str(h.percent)} for h in holders]
    SHAREHOLDER_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_ledger_entry(month: str) -> LedgerEntry:
    if not LEDGER_FILE.exists():
        raise FileNotFoundError("ledger.json bulunamadı.")
    data = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    if month not in data:
        raise KeyError(f"ledger.json içinde {month} ayı yok.")
    entry = data[month]
    return LedgerEntry(
        month=month,
        total_cash=Decimal(str(entry["toplam_kasa"])),
        keep_cash=Decimal(str(entry.get("kasada_birakilacak_tutar", 0))),
        advances=_to_decimal_map(entry.get("avanslar", {})),
    )


def save_ledger_entry(entry: LedgerEntry) -> None:
    data = {}
    if LEDGER_FILE.exists():
        data = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    data[entry.month] = {
        "toplam_kasa": str(entry.total_cash),
        "kasada_birakilacak_tutar": str(entry.keep_cash),
        "avanslar": _decimal_to_str_map(entry.advances),
    }
    LEDGER_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_carry() -> CarryState:
    if not CARRY_FILE.exists():
        return CarryState(balances={})
    data = json.loads(CARRY_FILE.read_text(encoding="utf-8"))
    return CarryState(balances=_to_decimal_map(data))


def save_carry(state: CarryState) -> None:
    CARRY_FILE.write_text(json.dumps(_decimal_to_str_map(state.balances), indent=2), encoding="utf-8")
