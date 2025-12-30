from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("carryover/", views.carryover, name="carryover"),
    path("kasa/<str:account>/", views.account_detail, name="account_detail"),
    path("banka-otomatik/", views.bank_auto, name="bank_auto"),
    path("gecmis/", views.backdate, name="backdate"),
    path("hareketler/", views.transactions_manage, name="transactions_manage"),
    path("cariler/", views.counterparties, name="counterparties"),
    path("hisseler/", views.stocks, name="stocks"),
    path("hisse-hesapla/", views.stock_preview, name="stock_preview"),
    path("ozet/", views.summary, name="summary"),
]
