"""Plain Django forms — NOT ModelForms. We never bind to the Django ORM.

The form's ``cleaned_data`` is converted to an application-layer DTO inside
the view and passed to a use case.
"""
from __future__ import annotations

from decimal import Decimal

from django import forms


class ClientForm(forms.Form):
    name = forms.CharField(max_length=200)
    phone_e164 = forms.CharField(
        max_length=32,
        help_text="E.164 format, e.g. +5511999999999",
    )
    email = forms.EmailField(required=False)
    notes = forms.CharField(widget=forms.Textarea, required=False)

    def clean_phone_e164(self) -> str:
        phone = self.cleaned_data["phone_e164"].strip()
        if not phone.startswith("+"):
            raise forms.ValidationError("Phone must start with '+' (E.164).")
        return phone


class SaleItemForm(forms.Form):
    name = forms.CharField(max_length=200)
    quantity = forms.IntegerField(min_value=1)
    filament_grams = forms.DecimalField(min_value=Decimal("0"), decimal_places=2)
    print_hours = forms.DecimalField(min_value=Decimal("0"), decimal_places=2)
    customization_hours = forms.DecimalField(
        min_value=Decimal("0"), decimal_places=2, required=False, initial=Decimal("0")
    )
    painting_hours = forms.DecimalField(
        min_value=Decimal("0"), decimal_places=2, required=False, initial=Decimal("0")
    )


class SaleForm(forms.Form):
    client_id = forms.IntegerField(widget=forms.Select)
    due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    notes = forms.CharField(widget=forms.Textarea, required=False)
