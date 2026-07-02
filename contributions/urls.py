from django.urls import path

from . import views

app_name = "contributions"

urlpatterns = [
    path("joined/<uuid:contributor_id>/", views.account_displayed, name="account_displayed"),
]
