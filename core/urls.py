from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("search/", views.search, name="search"),
    path("level/<slug:slug>/", views.level_detail, name="level_detail"),
    path("program/<slug:slug>/", views.program_detail, name="program_detail"),
    path("subject/<slug:slug>/", views.subject_detail, name="subject_detail"),
    path("subject/<slug:slug>/syllabus.txt", views.subject_syllabus, name="subject_syllabus"),
    path("resource/<int:pk>/open/", views.resource_open, name="resource_open"),
    path("resource/<int:pk>/", views.resource_view, name="resource_view"),
    path("resource/<int:pk>/report/", views.resource_report, name="resource_report"),
    path("healthz/", views.healthz, name="healthz"),
    path("readyz/", views.readyz, name="readyz"),
    path("courses/", views.courses, name="courses"),
    path("syllabus/", views.syllabus, name="syllabus"),
    path("browse/<slug:section>/", views.browse, name="browse"),
]
