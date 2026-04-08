from django.urls import path

from . import views

app_name = "sales"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sales/", views.sale_list, name="list"),
    path("sales/new/", views.sale_new, name="new"),
    path("sales/<int:sale_id>/", views.sale_detail, name="detail"),
    path("sales/<int:sale_id>/ready/", views.mark_ready, name="mark_ready"),
    path("clients/new/", views.client_new, name="client_new"),
]
