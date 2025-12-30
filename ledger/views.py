from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Tuple

from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from calc import DistributionError, compute_distribution
from io_store import load_carry, load_ledger_entry, load_shareholders
from models import CarryState, LedgerEntry, Shareholder

from .models import (
    CashCategory,
    Counterparty,
    CounterpartyAudit,
    Transaction,
    TransactionAudit,
)


# -------------------------------
# Helpers
# -------------------------------


def _now():
    return timezone.now()


def _today():
    return timezone.localdate()


def _sum_amount(qs, direction: str) -> Decimal:
    return qs.filter(direction=direction).aggregate(total=Sum("amount")).get("total") or Decimal("0")


def _account_totals(qs):
    incoming = _sum_amount(qs, Transaction.Direction.IN)
    outgoing = _sum_amount(qs, Transaction.Direction.OUT)
    return {
        "incoming": incoming,
        "outgoing": outgoing,
        "net": incoming - outgoing,
    }


def _get_client_ip(request) -> str | None:
    return request.META.get("REMOTE_ADDR") or request.META.get("HTTP_X_FORWARDED_FOR")


def _load_shareholders_safe() -> List[Shareholder]:
    try:
        return load_shareholders()
    except Exception:
        # Varsayılan örnekler
        return [
            Shareholder(name="Burhan Arslan", percent=Decimal("50")),
            Shareholder(name="Emre Babur", percent=Decimal("30")),
            Shareholder(name="Ali Babur", percent=Decimal("10")),
            Shareholder(name="Selin Özcan", percent=Decimal("10")),
        ]


def _load_carry_safe() -> CarryState:
    try:
        return load_carry()
    except Exception:
        return CarryState(balances={})


def _load_ledger_entry_safe(month: str) -> LedgerEntry | None:
    try:
        return load_ledger_entry(month)
    except Exception:
        return None


def _shareholder_counterparty_map() -> Dict[str, Counterparty]:
    mapping = {}
    for cp in Counterparty.objects.all():
        mapping[cp.name.lower()] = cp
    return mapping


# -------------------------------
# Dashboard
# -------------------------------


def dashboard(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "add_category":
                name = request.POST.get("cash_category_name", "").strip()
                direction = request.POST.get("cash_category_direction", "").strip() or None
                if not name or not direction:
                    raise ValueError("Kategori adı ve yön gerekli.")
                CashCategory.objects.get_or_create(name=name, direction=direction)
                message = "Kalem eklendi."
            elif action == "add":
                amount = Decimal(request.POST.get("amount", "0") or "0")
                if amount <= 0:
                    raise ValueError("Tutar sıfır olamaz.")
                direction = request.POST.get("direction") or request.POST.get("cash_category_direction") or "IN"
                account = request.POST.get("account", Transaction.Account.CASH)
                description = request.POST.get("description", "").strip()
                cp_id = request.POST.get("counterparty") or None
                cp = Counterparty.objects.filter(id=cp_id).first() if cp_id else None
                Transaction.objects.create(
                    direction=direction,
                    account=account,
                    amount=amount,
                    description=description,
                    counterparty=cp,
                    timestamp=_now(),
                )
                message = "Kayıt eklendi."
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

    now = _now()
    today = _today()
    transactions = Transaction.objects.filter(approved=True)
    cash_qs = transactions.filter(account=Transaction.Account.CASH)
    bank_qs = transactions.filter(account=Transaction.Account.BANK)

    account_cards = []
    # Sadece Nakit ve Banka tekli kartları göster
    for code, label in ((Transaction.Account.CASH, dict(Transaction.Account.choices).get(Transaction.Account.CASH)),
                        (Transaction.Account.BANK, dict(Transaction.Account.choices).get(Transaction.Account.BANK))):
        qs = transactions.filter(account=code)
        today_qs = qs.filter(timestamp__date=today)
        account_cards.append(
            {
                "code": code,
                "label": label or code,
                "overall": _account_totals(qs),
                "today": _account_totals(today_qs),
            }
        )

    # Banka otomatik (bekleyen onaylı olmayan kayıtlar)
    bank_auto_pending = Transaction.objects.filter(account=Transaction.Account.BANK, approved=False)
    bank_auto_totals = _account_totals(bank_auto_pending)

    prev_carry_qs = transactions.filter(is_carryover=True)
    prev_closing = {
        "CASH": _account_totals(prev_carry_qs.filter(account=Transaction.Account.CASH)),
        "BANK": _account_totals(prev_carry_qs.filter(account=Transaction.Account.BANK)),
    }

    context = {
        "now": now,
        "message": message,
        "error": error,
        "display_accounts": Transaction.Account,
        "account_cards": account_cards + [
            {
                "code": "BANK_AUTO",
                "label": "Banka",
                "overall": bank_auto_totals,
                "today": _account_totals(bank_auto_pending.filter(timestamp__date=today)),
            }
        ],
        "cash_categories": CashCategory.objects.all(),
        "prev_closing": prev_closing,
        "prev_bank_auto": bank_auto_totals["net"],
        "prev_total_with_auto": prev_closing["CASH"]["net"] + prev_closing["BANK"]["net"] + bank_auto_totals["net"],
        "overall_with_auto": _account_totals(cash_qs)["net"]
        + _account_totals(bank_qs)["net"]
        + bank_auto_totals["net"],
    }
    return render(request, "ledger/dashboard.html", context)


# -------------------------------
# Account detail
# -------------------------------


def account_detail(request, account: str):
    account = account.upper()
    if account not in dict(Transaction.Account.choices):
        account = Transaction.Account.CASH

    message = error = None
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0") or "0")
            if amount <= 0:
                raise ValueError("Tutar sıfır olamaz.")
            direction = request.POST.get("direction", Transaction.Direction.IN)
            description = request.POST.get("description", "").strip()
            cp_id = request.POST.get("counterparty") or None
            cp = Counterparty.objects.filter(id=cp_id).first() if cp_id else None
            Transaction.objects.create(
                direction=direction,
                account=account,
                amount=amount,
                description=description,
                counterparty=cp,
                timestamp=_now(),
            )
            message = "Kayıt eklendi."
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

    qs = Transaction.objects.filter(account=account, approved=True).order_by("-timestamp")
    summary = _account_totals(qs)
    today = _today()
    today_qs = qs.filter(timestamp__date=today)
    today_in = _sum_amount(today_qs, Transaction.Direction.IN)
    today_out = _sum_amount(today_qs, Transaction.Direction.OUT)
    today_net = today_in - today_out

    prev_carry = _account_totals(qs.filter(is_carryover=True))["net"]
    today_balance = prev_carry + today_net

    selected_day = request.GET.get("day")
    try:
        selected_day = datetime.fromisoformat(selected_day).date() if selected_day else today
    except Exception:
        selected_day = today
    daily_qs = qs.filter(timestamp__date=selected_day)
    daily_in = _sum_amount(daily_qs, Transaction.Direction.IN)
    daily_out = _sum_amount(daily_qs, Transaction.Direction.OUT)
    daily_net = daily_in - daily_out
    daily_closing = prev_carry + daily_net

    def range_totals(days: int):
        start_date = today - timedelta(days=days)
        rqs = qs.filter(timestamp__date__gte=start_date)
        t_in = _sum_amount(rqs, Transaction.Direction.IN)
        t_out = _sum_amount(rqs, Transaction.Direction.OUT)
        return {"incoming": t_in, "outgoing": t_out, "net": t_in - t_out}

    weekly = range_totals(7)
    monthly = range_totals(30)
    yearly = range_totals(365)
    ranges = [weekly, monthly, yearly]

    weekly_transactions = qs.filter(timestamp__date__gte=today - timedelta(days=7))
    monthly_transactions = qs.filter(timestamp__month=today.month, timestamp__year=today.year)

    weekly_closing = prev_carry + weekly["net"]
    monthly_closing = prev_carry + monthly["net"]

    # Aylık kapanışlar listesi
    month_closures = []
    for row in (
        qs.annotate(month_label=TruncMonth("timestamp"))
        .values("month_label")
        .annotate(net=Sum("amount", filter=Q(direction=Transaction.Direction.IN)) - Sum("amount", filter=Q(direction=Transaction.Direction.OUT)))
        .order_by("month_label")
    ):
        label = row["month_label"].strftime("%Y-%m") if row["month_label"] else ""
        month_closures.append((label, row["net"]))

    context = {
        "account": {"code": account, "label": dict(Transaction.Account.choices).get(account, account)},
        "transactions": list(qs[:100]),
        "counterparties": Counterparty.objects.all(),
        "summary": summary,
        "message": message,
        "error": error,
        "prev_carry": prev_carry,
        "today_in": today_in,
        "today_out": today_out,
        "today_net": today_net,
        "today_balance": today_balance,
        "selected_day": selected_day,
        "daily_in": daily_in,
        "daily_out": daily_out,
        "daily_net": daily_net,
        "daily_closing": daily_closing,
        "ranges": ranges,
        "weekly_transactions": weekly_transactions,
        "monthly_transactions": monthly_transactions,
        "weekly_closing": weekly_closing,
        "monthly_closing": monthly_closing,
        "month_closures": month_closures,
    }
    return render(request, "ledger/account_detail.html", context)


# -------------------------------
# Bank auto (API import ekranı)
# -------------------------------


def bank_auto(request):
    message = error = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "import":
            try:
                tx_id = request.POST.get("transaction_id")
                tx = get_object_or_404(Transaction, id=tx_id, approved=False)
                raw_amount = str(request.POST.get("amount", "0") or "0").strip()
                # Türkçe format desteği: "70.000,00" -> "70000.00"
                normalized_amount = raw_amount.replace(".", "").replace(",", ".")
                amount = Decimal(normalized_amount)
                if amount == 0:
                    raise ValueError("Tutar geçersiz.")
                direction = request.POST.get("direction", Transaction.Direction.IN)
                account = request.POST.get("account", Transaction.Account.BANK)
                description = request.POST.get("description", "").strip()
                dir_label = "Gelir" if direction == Transaction.Direction.IN else "Gider"
                if description and dir_label not in description:
                    description = f"{description} ({dir_label})"
                cat_id = request.POST.get("cash_category_id") or None
                ts_raw = request.POST.get("timestamp")
                timestamp = datetime.fromisoformat(ts_raw) if ts_raw else tx.timestamp
                if timezone.is_naive(timestamp):
                    timestamp = timezone.make_aware(timestamp)

                tx.direction = direction
                tx.account = account
                tx.amount = amount
                tx.description = description
                tx.timestamp = timestamp
                tx.counterparty = tx.counterparty  # no change
                tx.approved = True
                tx.save(update_fields=["direction", "account", "amount", "description", "timestamp", "approved"])
                # Kategori bilgisi sadece log amaçlı; Transaction modeli CashCategory tutmuyor.
                message = "İşlem içe aktarıldı ve manuele işlendi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

    pending = Transaction.objects.filter(account=Transaction.Account.BANK, approved=False).order_by("-timestamp")
    api_totals = _account_totals(pending)
    manual_net = _account_totals(Transaction.objects.filter(account=Transaction.Account.BANK, approved=True))["net"]
    diff_net = manual_net - api_totals["net"]

    context = {
        "transactions": pending,
        "incoming": api_totals["incoming"],
        "outgoing": api_totals["outgoing"],
        "net": api_totals["net"],
        "manual_net": manual_net,
        "diff_net": diff_net,
        "cash_categories": CashCategory.objects.all(),
        "message": message,
        "error": error,
    }
    return render(request, "ledger/banka_otomatik.html", context)


# -------------------------------
# Backdate (geçmiş işlem ekle)
# -------------------------------


def backdate(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_past":
            try:
                date_raw = request.POST.get("date")
                time_raw = request.POST.get("time") or "00:00"
                ts = datetime.fromisoformat(f"{date_raw}T{time_raw}")
                amount = Decimal(request.POST.get("amount", "0") or "0")
                direction = request.POST.get("direction", Transaction.Direction.IN)
                account = request.POST.get("account", Transaction.Account.CASH)
                description = request.POST.get("description", "").strip()
                cp_id = request.POST.get("counterparty") or None
                cp_new = request.POST.get("new_counterparty", "").strip()
                cp = None
                if cp_id:
                    cp = Counterparty.objects.filter(id=cp_id).first()
                elif cp_new:
                    cp, _ = Counterparty.objects.get_or_create(name=cp_new)
                Transaction.objects.create(
                    direction=direction,
                    account=account,
                    amount=amount,
                    description=description,
                    counterparty=cp,
                    timestamp=timezone.make_aware(ts) if timezone.is_naive(ts) else ts,
                )
                message = "Kayıt eklendi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

    transactions = Transaction.objects.filter(approved=True).order_by("-timestamp")[:50]
    context = {
        "message": message,
        "error": error,
        "transactions": transactions,
        "directions": Transaction.Direction,
        "accounts": Transaction.Account,
        "counterparties": Counterparty.objects.all(),
    }
    return render(request, "ledger/backdate.html", context)


# -------------------------------
# Hareketler (edit/delete)
# -------------------------------


def _log_transaction_audit(tx: Transaction | None, old: dict, new: dict, note: str | None, request):
    tx_id = tx.id if tx is not None and tx.id else None
    TransactionAudit.objects.create(
        transaction_id=tx_id,
        old_direction=old.get("direction", ""),
        new_direction=new.get("direction", ""),
        old_account=old.get("account", ""),
        new_account=new.get("account", ""),
        old_amount=old.get("amount", Decimal("0")),
        new_amount=new.get("amount", Decimal("0")),
        old_description=old.get("description", ""),
        new_description=new.get("description", ""),
        old_counterparty=old.get("counterparty") or "",
        new_counterparty=new.get("counterparty") or "",
        username=getattr(request.user, "username", "") if getattr(request, "user", None) else "",
        ip_address=_get_client_ip(request),
        note=note or "",
    )


def transactions_manage(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"update", "delete"}:
            tx_id = request.POST.get("transaction_id")
            tx = Transaction.objects.filter(id=tx_id).first() if tx_id else None
            if not tx:
                error = "Hareket bulunamadı."
            elif action == "delete":
                old = {
                    "direction": tx.direction,
                    "account": tx.account,
                    "amount": tx.amount,
                    "description": tx.description,
                    "counterparty": tx.counterparty.name if tx.counterparty else "",
                }
                _log_transaction_audit(tx, old, {}, request.POST.get("audit_note"), request)
                tx.delete()
                message = "Kayıt silindi."
            else:
                try:
                    old = {
                        "direction": tx.direction,
                        "account": tx.account,
                        "amount": tx.amount,
                        "description": tx.description,
                        "counterparty": tx.counterparty.name if tx.counterparty else "",
                    }
                    tx.direction = request.POST.get("direction", tx.direction)
                    tx.account = request.POST.get("account", tx.account)
                    tx.amount = Decimal(request.POST.get("amount", tx.amount) or tx.amount)
                    tx.description = request.POST.get("description", tx.description)
                    cp_id = request.POST.get("counterparty") or None
                    tx.counterparty = Counterparty.objects.filter(id=cp_id).first() if cp_id else None
                    ts_raw = request.POST.get("timestamp")
                    if ts_raw:
                        tx.timestamp = datetime.fromisoformat(ts_raw)
                        if timezone.is_naive(tx.timestamp):
                            tx.timestamp = timezone.make_aware(tx.timestamp)
                    tx.save()
                    new = {
                        "direction": tx.direction,
                        "account": tx.account,
                        "amount": tx.amount,
                        "description": tx.description,
                        "counterparty": tx.counterparty.name if tx.counterparty else "",
                    }
                    _log_transaction_audit(tx, old, new, request.POST.get("audit_note"), request)
                    message = "Kayıt güncellendi."
                except Exception as exc:  # noqa: BLE001
                    error = str(exc)

    transactions = Transaction.objects.filter(approved=True).order_by("-timestamp", "-id")[:50]
    audits = TransactionAudit.objects.all().order_by("-changed_at")[:200]
    context = {
        "transactions": transactions,
        "counterparties": Counterparty.objects.all(),
        "audits": audits,
        "message": message,
        "error": error,
    }
    return render(request, "ledger/transactions.html", context)


# -------------------------------
# Cariler
# -------------------------------


def counterparties(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_cari":
            try:
                name = request.POST.get("name", "").strip()
                contact = request.POST.get("contact", "").strip()
                notes = request.POST.get("notes", "").strip()
                if not name:
                    raise ValueError("Ad gerekli.")
                cp, created = Counterparty.objects.get_or_create(name=name, defaults={"contact": contact, "notes": notes})
                if not created:
                    cp.contact = contact
                    cp.notes = notes
                    cp.save()
                CounterpartyAudit.objects.create(
                    counterparty_name=cp.name,
                    action="created",
                    username=getattr(request.user, "username", "") if getattr(request, "user", None) else "",
                    ip_address=_get_client_ip(request),
                    note="",
                )
                message = "Cari kaydedildi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
        elif action == "delete_cari":
            try:
                cp_id = request.POST.get("counterparty_id")
                cp = Counterparty.objects.filter(id=cp_id).first()
                if not cp:
                    raise ValueError("Cari bulunamadı.")
                name = cp.name
                cp.delete()
                CounterpartyAudit.objects.create(
                    counterparty_name=name,
                    action="deleted",
                    username=getattr(request.user, "username", "") if getattr(request, "user", None) else "",
                    ip_address=_get_client_ip(request),
                    note=request.POST.get("audit_note", "").strip(),
                )
                message = "Cari silindi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
        elif action == "add_tx":
            try:
                amount = Decimal(str(request.POST.get("amount", "0") or "0"))
                if amount <= 0:
                    raise ValueError("Tutar sıfır olamaz.")
                direction = request.POST.get("direction", Transaction.Direction.IN)
                account = request.POST.get("account", Transaction.Account.CASH)
                description = request.POST.get("description", "").strip()
                cp_id = request.POST.get("counterparty") or None
                cp = Counterparty.objects.filter(id=cp_id).first() if cp_id else None
                Transaction.objects.create(
                    direction=direction,
                    account=account,
                    amount=amount,
                    description=description,
                    counterparty=cp,
                    timestamp=_now(),
                )
                message = "Cari hareket kaydedildi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

    transactions = Transaction.objects.filter(approved=True)
    summaries = []
    shareholder_names = {h.name.lower() for h in _load_shareholders_safe()}
    for cp in Counterparty.objects.all():
        if cp.name.lower() in shareholder_names:
            continue  # Hissedar carilerini burada listeleme
        cp_qs = transactions.filter(counterparty=cp)
        totals = _account_totals(cp_qs)
        summaries.append(
            {
                "id": cp.id,
                "name": cp.name,
                "contact": cp.contact,
                "notes": cp.notes,
                "net": totals["net"],
                "incoming": totals["incoming"],
                "outgoing": totals["outgoing"],
            }
        )

    counterparties_qs = Counterparty.objects.exclude(name__in=shareholder_names)
    # Yazdırma ve seçim için detaylı veri
    cp_print_data = []
    cp_monthly = []
    cp_tx_map = []
    for cp in counterparties_qs:
        cp_qs = transactions.filter(counterparty=cp)
        totals = _account_totals(cp_qs)
        cp_print_data.append(
            {
                "id": cp.id,
                "name": cp.name,
                "contact": cp.contact,
                "incoming": totals["incoming"],
                "outgoing": totals["outgoing"],
                "net": totals["net"],
            }
        )
        # aylık özet
        months = []
        for row in (
            cp_qs.annotate(month_label=TruncMonth("timestamp"))
            .values("month_label")
            .annotate(
                incoming=Sum("amount", filter=Q(direction=Transaction.Direction.IN)),
                outgoing=Sum("amount", filter=Q(direction=Transaction.Direction.OUT)),
            )
            .order_by("month_label")
        ):
            label = row["month_label"].strftime("%Y-%m") if row["month_label"] else ""
            inc = row["incoming"] or Decimal("0")
            out = row["outgoing"] or Decimal("0")
            months.append({"name": label, "incoming": inc, "outgoing": out, "net": inc - out})
        cp_monthly.append({"id": cp.id, "name": cp.name, "months": months})
        cp_tx_map.append(
            {
                "id": cp.id,
                "name": cp.name,
                "transactions": list(cp_qs.order_by("-timestamp")[:100]),
            }
        )

    context = {
        "message": message,
        "error": error,
        "summaries": summaries,
        "counterparties": counterparties_qs,
        "directions": Transaction.Direction,
        "accounts": Transaction.Account,
        "cp_print_data": cp_print_data,
        "cp_monthly": cp_monthly,
        "cp_tx_map": cp_tx_map,
    }
    return render(request, "ledger/counterparties.html", context)


# -------------------------------
# Hisseler
# -------------------------------


def _shareholder_payouts(
    total_net: Decimal, carry_state: CarryState, holders: List[Shareholder] | None = None
) -> Tuple[List[dict], str | None]:
    holders = holders or _load_shareholders_safe()
    error = None
    try:
        validate = compute_distribution  # noqa: F841 - ensure import
    except Exception:
        pass

    payouts: List[dict] = []
    cp_map = _shareholder_counterparty_map()
    for h in holders:
        entitlement = (total_net * h.percent) / Decimal("100")
        cp = cp_map.get(h.name.lower())
        cp_qs = Transaction.objects.filter(counterparty=cp) if cp else Transaction.objects.none()
        outgoing = _sum_amount(cp_qs, Transaction.Direction.OUT)
        incoming = _sum_amount(cp_qs, Transaction.Direction.IN)
        carry_prev = carry_state.balances.get(h.name, carry_state.balances.get(h.name.lower(), Decimal("0")))
        net_due = entitlement - outgoing + carry_prev
        payouts.append(
            {
                "name": h.name,
                "share": h.percent,
                "share_value": entitlement,
                "outgoing": outgoing,
                "incoming": incoming,
                "net_due": net_due,
                "contact": cp.contact if cp else "",
            }
        )
    return payouts, error


def stocks(request):
    message = error = None
    today = _today()
    month_label = today.strftime("%B %Y")

    holders = _load_shareholders_safe()
    shareholder_names = {h.name.lower() for h in holders}
    carry_state = _load_carry_safe()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_cp_tx":
            try:
                cp = Counterparty.objects.filter(id=request.POST.get("counterparty_id")).first()
                if not cp:
                    raise ValueError("Cari bulunamadı.")
                amount = Decimal(request.POST.get("amount", "0") or "0")
                if amount <= 0:
                    raise ValueError("Tutar sıfır olamaz.")
                direction = request.POST.get("direction", Transaction.Direction.OUT)
                description = request.POST.get("description", "").strip()
                Transaction.objects.create(
                    direction=direction,
                    account=Transaction.Account.CASH,
                    amount=amount,
                    description=description,
                    counterparty=cp,
                    timestamp=_now(),
                    approved=False,  # hissedar gider/gelir kasa toplamını etkilemesin
                )
                message = "Cari hareket eklendi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

    transactions = Transaction.objects.filter(approved=True)
    cash_net = _account_totals(transactions.filter(account=Transaction.Account.CASH))["net"]
    bank_net = _account_totals(transactions.filter(account=Transaction.Account.BANK))["net"]
    bank_auto_net = _account_totals(Transaction.objects.filter(account=Transaction.Account.BANK, approved=False))["net"]
    # Hisselere dağıtılacak toplam: Nakit + Banka Otomatik (bekleyen). Onaylı banka neti ekliyoruz.
    total_net = cash_net + bank_net + bank_auto_net

    payouts, payout_error = _shareholder_payouts(total_net, carry_state, holders)
    if payout_error:
        error = payout_error

    # Hissedar carileri
    shareholder_counterparties = []
    cp_by_name = {cp.name.lower(): cp for cp in Counterparty.objects.all() if cp.name.lower() in shareholder_names}
    for holder in holders:
        key = holder.name.lower()
        cp = cp_by_name.get(key)
        if cp:
            cp_qs_all = Transaction.objects.filter(counterparty=cp)
            totals = _account_totals(cp_qs_all)
            shareholder_counterparties.append(
                {
                    "id": cp.id,
                    "name": cp.name,
                    "contact": cp.contact,
                    "net": totals["net"],
                    "incoming": totals["incoming"],
                    "outgoing": totals["outgoing"],
                }
            )
        else:
            shareholder_counterparties.append(
                {
                    "id": None,
                    "name": holder.name,
                    "contact": "",
                    "net": Decimal("0"),
                    "incoming": Decimal("0"),
                    "outgoing": Decimal("0"),
                }
            )

    # Geçmiş ledger.json dökümü
    history = []
    try:
        import json

        from io_store import LEDGER_FILE

        if LEDGER_FILE.exists():
            data = json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
            carry_balances: Dict[str, Decimal] = dict(carry_state.balances)
            for month_key in sorted(data.keys()):
                entry = load_ledger_entry(month_key)
                if not entry:
                    continue
                result = compute_distribution(
                    month=month_key,
                    holders=_load_shareholders_safe(),
                    total_cash=entry.total_cash,
                    keep_cash=entry.keep_cash,
                    advances=entry.advances,
                    carry=carry_balances,
                )
                rows = []
                for r in result.rows:
                    rows.append(
                        {
                            "name": r.name,
                            "share": r.percent,
                            "share_value": r.entitlement,
                            "paid": r.paid,
                            "due": r.new_carry,
                        }
                    )
                    carry_balances[r.name] = r.new_carry
                history.append({"label": month_key, "rows": rows})
    except Exception:
        pass

    context = {
        "month": month_label,
        "payouts": payouts,
        "message": message,
        "error": error,
        "display_total_net": total_net,
        "display_cash_net": cash_net,
        "display_bank_net": bank_net,
        "display_bank_auto_net": bank_auto_net,
        "bank_auto_error": None,
        "shareholder_counterparties": shareholder_counterparties,
        "history": history,
    }
    return render(request, "ledger/stocks.html", context)


# -------------------------------
# Gelir/Gider özet
# -------------------------------


def summary(request):
    today = _today()
    start_raw = request.GET.get("start")
    end_raw = request.GET.get("end")
    start_date = datetime.fromisoformat(start_raw).date() if start_raw else today.replace(day=1)
    end_date = datetime.fromisoformat(end_raw).date() if end_raw else today
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(microsecond=0)
    end_dt = timezone.make_aware(end_dt) if timezone.is_naive(end_dt) else end_dt

    qs = Transaction.objects.filter(
        timestamp__date__gte=start_date,
        timestamp__date__lte=end_date,
        approved=True,
    )
    income_total = _sum_amount(qs, Transaction.Direction.IN)
    expense_total = _sum_amount(qs, Transaction.Direction.OUT)
    net_total = income_total - expense_total

    # Kategori bazında (açıklamaya göre gruplama)
    income_rows = []
    for row in (
        qs.filter(direction=Transaction.Direction.IN)
        .values("description")
        .annotate(amount=Sum("amount"))
        .order_by("-amount")
    ):
        income_rows.append(
            {"name": row["description"] or "Diğer", "amount": row["amount"], "percent": float(row["amount"] / income_total * 100) if income_total else 0}
        )

    expense_rows = []
    for row in (
        qs.filter(direction=Transaction.Direction.OUT)
        .values("description")
        .annotate(amount=Sum("amount"))
        .order_by("-amount")
    ):
        amt = row["amount"]
        expense_rows.append(
            {
                "name": row["description"] or "Diğer",
                "amount": amt,
                "display_amount": amt.copy_abs() if hasattr(amt, "copy_abs") else abs(amt),
                "percent": float(amt / expense_total * 100) if expense_total else 0,
            }
        )

    context = {
        "start_date": start_date,
        "end_date": end_date,
        "month_label": f"{start_date.strftime('%d.%m.%Y')} - {end_date.strftime('%d.%m.%Y')}",
        "income_total": income_total,
        "expense_total": expense_total,
        "net_total": net_total,
        "income_rows": income_rows,
        "expense_rows": expense_rows,
    }
    return render(request, "ledger/summary.html", context)


# -------------------------------
# Hisse önizleme
# -------------------------------


def stock_preview(request):
    shareholders = _load_shareholders_safe()
    preview_payouts = []
    preview_total = None
    if request.method == "POST":
        raw_amt = request.POST.get("preview_amount", "").strip()
        try:
            preview_total = Decimal(raw_amt)
        except Exception:
            preview_total = None
        if preview_total is not None:
            for h in shareholders:
                preview_payouts.append(
                    {
                        "name": h.name,
                        "share": h.percent,
                        "share_value": preview_total * h.percent / Decimal("100"),
                    }
                )

    context = {
        "preview_payouts": preview_payouts,
        "preview_total": preview_total,
    }
    return render(request, "ledger/stock_preview.html", context)


# -------------------------------
# Carryover (basit yönlendirme)
# -------------------------------


def carryover(request):
    # Özelleştirilmiş carry devri yok; ana sayfaya yönlendir.
    return redirect("dashboard")
