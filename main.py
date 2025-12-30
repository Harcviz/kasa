from __future__ import annotations

import argparse
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from calc import DistributionError, compute_distribution
from io_store import (
    CARRY_FILE,
    LEDGER_FILE,
    SHAREHOLDER_FILE,
    CarryState,
    LedgerEntry,
    load_carry,
    load_ledger_entry,
    load_shareholders,
    save_carry,
    save_ledger_entry,
    save_shareholders,
)
from models import Shareholder


def fmt_money(val: Decimal) -> str:
    return f"{val.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def print_table(result) -> None:
    headers = ["İsim", "Yüzde", "Hakediş", "Avans", "Önceki Carry", "Fiili Ödeme", "Yeni Carry"]
    rows = []
    for r in result.rows:
        rows.append(
            [
                r.name,
                f"{r.percent}%",
                fmt_money(r.entitlement),
                fmt_money(r.advance),
                fmt_money(r.prev_carry),
                fmt_money(r.paid),
                fmt_money(r.new_carry),
            ]
        )
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows)]
    line = " | ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" | ".join(str(x).ljust(w) for x, w in zip(row, widths)))
    print("-" * len(line))
    print(
        f"Toplam hakediş: {fmt_money(result.total_entitlement)} | Toplam ödeme: {fmt_money(result.total_paid)} | Dağıtılabilir kasa: {fmt_money(result.distributable)}"
    )


def cmd_close_month(month: str) -> None:
    holders = load_shareholders()
    ledger = load_ledger_entry(month)
    carry_state = load_carry()
    try:
        result = compute_distribution(
            month=month,
            holders=holders,
            total_cash=ledger.total_cash,
            keep_cash=ledger.keep_cash,
            advances=ledger.advances,
            carry=carry_state.balances,
        )
    except DistributionError as exc:
        print(f"Hata: {exc}")
        return

    print_table(result)

    # carry güncelle
    new_carry: Dict[str, Decimal] = {}
    for row in result.rows:
        new_carry[row.name] = row.new_carry
    save_carry(CarryState(balances=new_carry))
    print(f"Carry güncellendi -> {CARRY_FILE}")


def cmd_init_example() -> None:
    holders: List[Shareholder] = [
        Shareholder("Burhan Arslan", Decimal("50")),
        Shareholder("Emre Babur", Decimal("30")),
        Shareholder("Ali Babur", Decimal("10")),
        Shareholder("Selin Özcan", Decimal("10")),
    ]
    save_shareholders(holders)

    entry = LedgerEntry(
        month="2025-12",
        total_cash=Decimal("1000000"),
        keep_cash=Decimal("0"),
        advances={
            "Burhan Arslan": Decimal("120000"),
            "Emre Babur": Decimal("0"),
            "Ali Babur": Decimal("20000"),
            "Selin Özcan": Decimal("5000"),
        },
    )
    save_ledger_entry(entry)
    save_carry(CarryState(balances={}))
    print(f"Örnek dosyalar oluşturuldu: {SHAREHOLDER_FILE}, {LEDGER_FILE}, {CARRY_FILE}")


def cmd_interactive_close() -> None:
    month = input("Ay (YYYY-MM): ").strip()
    toplam = Decimal(input("Toplam kasa: ").strip())
    keep = Decimal(input("Kasada bırakılacak tutar (0): ").strip() or "0")
    holders = load_shareholders()
    advances: Dict[str, Decimal] = {}
    print("Avans tutarları (boş geçersen 0):")
    for h in holders:
        raw = input(f"  {h.name}: ").strip()
        advances[h.name] = Decimal(raw) if raw else Decimal("0")
    entry = LedgerEntry(month=month, total_cash=toplam, keep_cash=keep, advances=advances)
    save_ledger_entry(entry)
    print("Ledger kaydedildi, ay kapatılıyor...\n")
    cmd_close_month(month)


def main() -> None:
    parser = argparse.ArgumentParser(description="Kasa dağıtım aracı")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("init-example", help="Örnek dosyaları oluştur")
    close_p = sub.add_parser("close-month", help="Ay kapat ve dağıtım yap")
    close_p.add_argument("month", help="YYYY-MM")
    sub.add_parser("interactive", help="Etkileşimli ay kapatma (input)")

    args = parser.parse_args()
    if args.cmd == "init-example":
        cmd_init_example()
    elif args.cmd == "close-month":
        cmd_close_month(args.month)
    elif args.cmd == "interactive":
        cmd_interactive_close()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
