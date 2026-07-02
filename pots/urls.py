from django.urls import include, path

from . import views
from contributions import views as contribution_views

app_name = "pots"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("create/", views.pot_create, name="create"),
    path("manage/<slug:slug>/", views.organiser_detail, name="organiser_detail"),
    path("manage/<slug:slug>/withdraw/", views.withdrawal_initiate, name="withdrawal"),
    path("manage/<slug:slug>/bank-lookup/", views.bank_lookup, name="bank_lookup"),
    # Public pot pages — no login required
    path("p/<slug:slug>/", contribution_views.public_pot, name="public_pot"),
    path("p/<slug:slug>/join/", contribution_views.join_pot, name="join_pot"),
    path("p/<slug:slug>/feed/", views.pot_feed, name="pot_feed"),
    path("p/<slug:slug>/", include("contributions.urls", namespace="contributions")),
]
