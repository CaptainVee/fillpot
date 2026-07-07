from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from payments import views as payments_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls", namespace="accounts")),
    path("api/v1/", include("payments.urls")),
    path("transactions/", payments_views.transactions_dashboard, name="transactions_dashboard"),
    path("", include("pots.urls", namespace="pots")),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [path("__debug__/", include(debug_toolbar.urls))] + urlpatterns
