from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("", include("learning.urls")),
    path("", include("portal.urls")),
    path("", include("core.urls")),
]

admin.site.site_header = "Gyansagar Admin"
admin.site.site_title = "Gyansagar"
admin.site.index_title = "Manage classes, programs, subjects, chapters and study material"
