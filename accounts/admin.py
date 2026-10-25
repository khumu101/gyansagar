from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Profile

User = get_user_model()


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    autocomplete_fields = ("level", "program")


class UserAdmin(DjangoUserAdmin):
    inlines = [ProfileInline]
    list_display = ("username", "email", "first_name", "last_name", "role", "is_staff", "date_joined")
    list_filter = DjangoUserAdmin.list_filter + ("profile__role",)
    list_select_related = ("profile",)

    @admin.display(description="Role", ordering="profile__role")
    def role(self, obj):
        return obj.profile.get_role_display() if hasattr(obj, "profile") else "-"


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
