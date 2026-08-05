from django.urls import path

from . import views

app_name = "pdf_editor_app"

urlpatterns = [
    path("", views.index, name="index"),
]