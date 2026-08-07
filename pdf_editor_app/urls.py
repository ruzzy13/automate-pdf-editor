from django.urls import path

from . import views

app_name = "pdf_editor_app"

urlpatterns = [
    path("home", views.index, name="home"),
    path("", views.editor, name="editor"),
    path("pdf/upload/", views.upload_pdf_api, name="upload_pdf_api"),
    path("pdf/replace/", views.replace_pdf_api, name="replace_pdf_api"),
    path("pdf/occurrences/", views.list_occurrences_api, name="list_occurrences_api")
]