from django.urls import include, path

urlpatterns = [
    path("", include("alder.interfaces.django_app.sales.urls")),
]
