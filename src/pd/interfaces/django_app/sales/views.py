"""Django views — thin adapters over application use cases.

NOTE: none of these functions touch SQLAlchemy directly. They open a UoW to
*read* aggregates for display, and call use cases to *write*. There is no
business logic in this module.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from alder.application.services.sales import (
    RegisterSaleInput,
    SaleItemInput,
)
from alder.domain.entities import Client

from ..container import container
from .forms import ClientForm, SaleForm, SaleItemForm

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def dashboard(request: HttpRequest) -> HttpResponse:
    c = container()
    with c.uow_factory() as uow:
        sales = uow.sales.list(limit=10)
        clients_total = len(uow.clients.list())

    revenue = sum((s.total.as_float() for s in sales), 0.0)
    return render(
        request,
        "sales/dashboard.html",
        {
            "recent_sales": sales,
            "clients_total": clients_total,
            "revenue_window": revenue,
        },
    )


# ---------------------------------------------------------------------------
# Sales list & detail
# ---------------------------------------------------------------------------


def sale_list(request: HttpRequest) -> HttpResponse:
    c = container()
    with c.uow_factory() as uow:
        sales = uow.sales.list(limit=200)
    return render(request, "sales/sale_list.html", {"sales": sales})


def sale_detail(request: HttpRequest, sale_id: int) -> HttpResponse:
    c = container()
    with c.uow_factory() as uow:
        sale = uow.sales.get(sale_id)
        if sale is None:
            return HttpResponse("Not found", status=404)
        client = uow.clients.get(sale.client_id)
    return render(
        request,
        "sales/sale_detail.html",
        {"sale": sale, "client": client},
    )


# ---------------------------------------------------------------------------
# Register a new sale
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def sale_new(request: HttpRequest) -> HttpResponse:
    c = container()

    with c.uow_factory() as uow:
        all_clients = uow.clients.list()

    if request.method == "POST":
        sale_form = SaleForm(request.POST)
        # Variable number of item rows: item-0-name, item-0-quantity, ...
        item_count = int(request.POST.get("item_count", "1"))
        item_forms = [
            SaleItemForm(request.POST, prefix=f"item-{i}")
            for i in range(item_count)
        ]

        if sale_form.is_valid() and all(f.is_valid() for f in item_forms):
            cmd = RegisterSaleInput(
                client_id=int(sale_form.cleaned_data["client_id"]),
                due_date=sale_form.cleaned_data.get("due_date"),
                notes=sale_form.cleaned_data.get("notes", ""),
                items=[
                    SaleItemInput(
                        name=f.cleaned_data["name"],
                        quantity=f.cleaned_data["quantity"],
                        filament_grams=f.cleaned_data["filament_grams"],
                        print_hours=f.cleaned_data["print_hours"],
                        customization_hours=f.cleaned_data.get(
                            "customization_hours"
                        ) or Decimal("0"),
                        painting_hours=f.cleaned_data.get("painting_hours")
                        or Decimal("0"),
                    )
                    for f in item_forms
                ],
            )
            try:
                sale = c.register_sale.execute(cmd)
            except LookupError as e:
                messages.error(request, str(e))
            else:
                messages.success(request, f"Sale #{sale.id} registered.")
                return HttpResponseRedirect(
                    reverse("sales:detail", args=[sale.id])
                )
    else:
        sale_form = SaleForm()
        item_forms = [SaleItemForm(prefix="item-0")]

    return render(
        request,
        "sales/sale_new.html",
        {
            "sale_form": sale_form,
            "item_forms": item_forms,
            "clients": all_clients,
        },
    )


@require_POST
def mark_ready(request: HttpRequest, sale_id: int) -> HttpResponse:
    c = container()
    try:
        c.mark_order_ready.execute(sale_id)
        messages.success(
            request,
            f"Sale #{sale_id} marked READY. Client notification dispatched.",
        )
    except (LookupError, ValueError) as e:
        messages.error(request, str(e))
    return HttpResponseRedirect(reverse("sales:detail", args=[sale_id]))


# ---------------------------------------------------------------------------
# New client
# ---------------------------------------------------------------------------


@require_http_methods(["GET", "POST"])
def client_new(request: HttpRequest) -> HttpResponse:
    c = container()
    if request.method == "POST":
        form = ClientForm(request.POST)
        if form.is_valid():
            client = Client(
                name=form.cleaned_data["name"],
                phone_e164=form.cleaned_data["phone_e164"],
                email=form.cleaned_data.get("email") or None,
                notes=form.cleaned_data.get("notes") or "",
            )
            saved = c.register_client.execute(client)
            messages.success(request, f"Client saved (#{saved.id}).")
            return HttpResponseRedirect(reverse("sales:new"))
    else:
        form = ClientForm()
    return render(request, "sales/client_new.html", {"form": form})
