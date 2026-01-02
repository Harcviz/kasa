from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from typing import Dict, List

from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.db.models import Q, Sum
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import SuperuserAuthenticationForm
from .models import (
    CashCategory,
    Counterparty,
    CounterpartyAudit,
    Shareholder,
    Transaction,
    TransactionAudit,
)


# -------------------------------
# Helpers
# -------------------------------


class SuperuserLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = SuperuserAuthenticationForm
    redirect_authenticated_user = True


def superuser_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_superuser:
            logout(request)
            messages.error(request, "Bu panele sadece superuser girebilir.")
            return redirect("login")
        return view_func(request, *args, **kwargs)

    return _wrapped


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
    return list(Shareholder.objects.filter(active=True).order_by("name"))


def _shareholder_counterparty_map() -> Dict[str, Counterparty]:
    mapping = {}
    for cp in Counterparty.objects.all():
        mapping[cp.name.lower()] = cp
    return mapping


# -------------------------------
# Dashboard
# -------------------------------


@superuser_required
def dashboard(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "add_category":
                name = request.POST.get("cash_category_name", "").strip()
                direction = request.POST.get("cash_category_direction", "").strip() or None
                if not name or not direction:
                    raise ValueError("Kategori ad ▒ ve y Ân gerekli.")
                CashCategory.objects.get_or_create(name=name, direction=direction)
                message = "Kalem eklendi."
            elif action == "add":
                amount = Decimal(request.POST.get("amount", "0") or "0")
                if amount <= 0:
                    raise ValueError("Tutar s ▒f ▒r olamaz.")
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
                message = "Kay ▒t eklendi."
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

    now = _now()
    today = _today()
    transactions = Transaction.objects.filter(approved=True)
    cash_qs = transactions.filter(account=Transaction.Account.CASH)
    bank_qs = transactions.filter(account=Transaction.Account.BANK)

    account_cards = []
    # Sadece Nakit ve Banka tekli kartlar ▒ g Âster
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

    # Banka otomatik (bekleyen onayl ▒ olmayan kay ▒tlar)
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
        "account_cards": account_cards,
        "cash_categories": CashCategory.objects.all(),
        "prev_closing": prev_closing,
        "overall_with_auto": _account_totals(cash_qs)["net"] + _account_totals(bank_qs)["net"],
    }
    return render(request, "ledger/dashboard.html", context)


# -------------------------------
# Account detail
# -------------------------------


@superuser_required
def account_detail(request, account: str):
    account = account.upper()
    if account not in dict(Transaction.Account.choices):
        account = Transaction.Account.CASH

    message = error = None
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0") or "0")
            if amount <= 0:
                raise ValueError("Tutar s ▒f ▒r olamaz.")
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
            message = "Kay ▒t eklendi."
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

    # Ayl ▒k kapan ▒ şlar listesi
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
# Bank auto (API import ekran ▒)
# -------------------------------


@superuser_required
def bank_auto(request):
    message = error = None

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "import":
            try:
                tx_id = request.POST.get("transaction_id")
                tx = get_object_or_404(Transaction, id=tx_id, approved=False)
                raw_amount = str(request.POST.get("amount", "0") or "0").strip()
                # T  rk ğe format deste şi: "70.000,00" -> "70000.00"
                normalized_amount = raw_amount.replace(".", "").replace(",", ".")
                amount = Decimal(normalized_amount)
                if amount == 0:
                    raise ValueError("Tutar ge ğersiz.")
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
                # Kategori bilgisi sadece log ama ğl ▒; Transaction modeli CashCategory tutmuyor.
                message = " ░ şlem i ğe aktar ▒ld ▒ ve manuele i şlendi."
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
# Backdate (ge ğmi ş i şlem ekle)
# -------------------------------


@superuser_required
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
                message = "Kay ▒t eklendi."
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


@superuser_required
def transactions_manage(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action in {"update", "delete"}:
            tx_id = request.POST.get("transaction_id")
            tx = Transaction.objects.filter(id=tx_id).first() if tx_id else None
            if not tx:
                error = "Hareket bulunamad ▒."
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
                message = "Kay ▒t silindi."
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
                    message = "Kay ▒t g  ncellendi."
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


@superuser_required
def counterparties(request):
    message = error = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_cari":
            try:
                name = request.POST.get("name", "").strip()
                contact = request.POST.get("contact", "").strip()
                tax_id = request.POST.get("tax_id", "").strip()
                address = request.POST.get("address", "").strip()
                iban = request.POST.get("iban", "").strip()
                contact_person = request.POST.get("contact_person", "").strip()
                website = request.POST.get("website", "").strip()
                notes = request.POST.get("notes", "").strip()
                if not name:
                    raise ValueError("Ad gerekli.")
                defaults = {
                    "contact": contact,
                    "notes": notes,
                    "tax_id": tax_id,
                    "address": address,
                    "iban": iban,
                    "contact_person": contact_person,
                    "website": website,
                }
                cp, created = Counterparty.objects.get_or_create(name=name, defaults=defaults)
                if not created:
                    for field, value in defaults.items():
                        setattr(cp, field, value)
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
        elif action == "update_cari":
            try:
                cp_id = request.POST.get("counterparty_id")
                cp = Counterparty.objects.filter(id=cp_id).first()
                if not cp:
                    raise ValueError("Cari bulunamadı.")
                cp.name = request.POST.get("name", cp.name).strip() or cp.name
                cp.contact = request.POST.get("contact", "").strip()
                cp.tax_id = request.POST.get("tax_id", "").strip()
                cp.address = request.POST.get("address", "").strip()
                cp.iban = request.POST.get("iban", "").strip()
                cp.contact_person = request.POST.get("contact_person", "").strip()
                cp.website = request.POST.get("website", "").strip()
                cp.notes = request.POST.get("notes", "").strip()
                cp.save()
                CounterpartyAudit.objects.create(
                    counterparty_name=cp.name,
                    action="updated",
                    username=getattr(request.user, "username", "") if getattr(request, "user", None) else "",
                    ip_address=_get_client_ip(request),
                    note=request.POST.get("audit_note", "").strip(),
                )
                message = "Cari güncellendi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)
        elif action == "delete_cari":
            try:
                cp_id = request.POST.get("counterparty_id")
                cp = Counterparty.objects.filter(id=cp_id).first()
                if not cp:
                    raise ValueError("Cari bulunamad ▒.")
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
                # Borç kaydı kasa hareketine yansımasın; ödeme yaparken kasa seçilsin.
                if direction == Transaction.Direction.IN:
                    account = Transaction.Account.NONE
                else:
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
    cp_filter = request.GET.get("cp")
    filtered_cp = None
    if cp_filter:
        try:
            filtered_cp = int(cp_filter)
        except Exception:
            filtered_cp = None

    base_holders = _load_shareholders_safe()
    excluded_shareholders = {
        "burhan arslan",
        "emre babur",
        "selin ozcan",
        "selin ?zcan",
        "ali babur",
    } | {h.name.strip().lower() for h in base_holders}

    cp_queryset = Counterparty.objects.all()
    if filtered_cp:
        cp_queryset = cp_queryset.filter(id=filtered_cp)

    for cp in cp_queryset:
        if cp.name.strip().lower() in excluded_shareholders:
            continue  # Hissedar carilerini burada listeleme
        cp_qs = transactions.filter(counterparty=cp)
        totals = _account_totals(cp_qs)
        summaries.append(
            {
                "id": cp.id,
                "name": cp.name,
                "contact": cp.contact,
                "tax_id": getattr(cp, "tax_id", ""),
                "address": getattr(cp, "address", ""),
                "iban": getattr(cp, "iban", ""),
                "contact_person": getattr(cp, "contact_person", ""),
                "website": getattr(cp, "website", ""),
                "notes": cp.notes,
                "net": totals["net"],
                "incoming": totals["incoming"],
                "outgoing": totals["outgoing"],
            }
        )

    counterparties_qs = [cp for cp in cp_queryset if cp.name.strip().lower() not in excluded_shareholders]
    # Yazd?rma ve se?im i?in detayl? veri
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
        # ayl?k ozet
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
        "cp_filter": filtered_cp,
    }
    return render(request, "ledger/counterparties.html", context)


# -------------------------------
# Hisseler
# -------------------------------


@superuser_required
def stocks(request):
    message = error = None
    holders = _load_shareholders_safe()
    holder_names_lower = {h.name.strip().lower() for h in holders}
    if not holders:
        error = "Hissedar tanimi yok. Admin panelinden ekleyin."

    cp_by_name: Dict[str, Counterparty] = {}
    for h in holders:
        cp, _ = Counterparty.objects.get_or_create(name=h.name, defaults={"contact": ""})
        cp_by_name[h.name.lower()] = cp

    account_choices = [
        (Transaction.Account.CASH, dict(Transaction.Account.choices).get(Transaction.Account.CASH)),
        (Transaction.Account.BANK, dict(Transaction.Account.choices).get(Transaction.Account.BANK)),
    ]

    if request.method == "POST":
        if request.POST.get("action") == "add_take":
            try:
                amount = Decimal(str(request.POST.get("amount", "0") or "0"))
                if amount <= 0:
                    raise ValueError("Tutar 0 olamaz.")
                cp_id = request.POST.get("counterparty_id")
                cp = Counterparty.objects.filter(id=cp_id).first()
                if not cp:
                    raise ValueError("Hissedar bulunamad?.")
                account = request.POST.get("account", Transaction.Account.CASH)
                if account not in dict(Transaction.Account.choices):
                    account = Transaction.Account.CASH
                description = request.POST.get("description", "").strip()
                Transaction.objects.create(
                    direction=Transaction.Direction.OUT,
                    account=account,
                    amount=amount,
                    description=description or "Hissedar ?demesi",
                    counterparty=cp,
                    timestamp=_now(),
                    approved=True,
                )
                message = "Kay?t eklendi."
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

    all_cps = list(Counterparty.objects.all())
    shareholder_cps_ids = [cp.id for cp in all_cps if cp.name.lower() in holder_names_lower]
    shareholder_cps = Counterparty.objects.filter(id__in=shareholder_cps_ids)
    # Hissedar carilerine ait eski onaysız kayıtlar varsa dahil et
    transactions = Transaction.objects.filter(Q(approved=True) | Q(counterparty__in=shareholder_cps))
    cash_net = _account_totals(transactions.filter(account=Transaction.Account.CASH))["net"]
    bank_net = _account_totals(transactions.filter(account=Transaction.Account.BANK))["net"]

    takes_qs = transactions.filter(counterparty__name__in=[h.name for h in holders])
    total_taken = _sum_amount(takes_qs, Transaction.Direction.OUT)
    total_pool = cash_net + bank_net + total_taken

    cards = []
    for h in holders:
        cp = cp_by_name.get(h.name.lower())
        taken_qs = transactions.filter(counterparty=cp)
        taken = _sum_amount(taken_qs, Transaction.Direction.OUT)
        share_value = (total_pool * h.percent) / Decimal("100")
        net_due = share_value - taken
        cards.append(
            {
                "id": cp.id if cp else None,
                "name": h.name,
                "percent": h.percent,
                "share_value": share_value,
                "taken": taken,
                "net_due": net_due,
            }
        )

    context = {
        "message": message,
        "error": error,
        "cards": cards,
        "cash_net": cash_net,
        "bank_net": bank_net,
        "total_taken": total_taken,
        "total_pool": total_pool,
        "account_choices": account_choices,
    }
    return render(request, "ledger/stocks.html", context)
# -------------------------------


@superuser_required
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

    # Kategori baz ▒nda (a ğ ▒klamaya g Âre gruplama)
    income_rows = []
    for row in (
        qs.filter(direction=Transaction.Direction.IN)
        .values("description")
        .annotate(amount=Sum("amount"))
        .order_by("-amount")
    ):
        income_rows.append(
            {"name": row["description"] or "Kategorisiz", "amount": row["amount"], "percent": float(row["amount"] / income_total * 100) if income_total else 0}
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
                "name": row["description"] or "Kategorisiz",
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
# Hisse  Ânizleme
# -------------------------------


@superuser_required
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
# Carryover (basit y Ânlendirme)
# -------------------------------


@superuser_required
def carryover(request):
    #  ûzelle ştirilmi ş carry devri yok; ana sayfaya y Ânlendir.
    return redirect("dashboard")



