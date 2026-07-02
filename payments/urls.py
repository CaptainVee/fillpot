from django.urls import path

from . import views

urlpatterns = [
    path("webhooks/nomba/", views.nomba_webhook, name="nomba_webhook"),
]
