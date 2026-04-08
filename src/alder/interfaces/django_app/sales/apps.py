from django.apps import AppConfig


class SalesConfig(AppConfig):
    # Django requires the label to match the import path's last segment.
    name = "alder.interfaces.django_app.sales"
    label = "sales"
    verbose_name = "Alder Sales"

    def ready(self) -> None:
        # Initialise SQLAlchemy schema + container on boot. Idempotent.
        from alder.bootstrap import get_container, init_db

        init_db()
        get_container()
