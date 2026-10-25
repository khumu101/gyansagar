from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _create_teachers_group(sender, **kwargs):
    """Create a 'Teachers' group that can upload content from the admin (idempotent)."""
    from django.apps import apps
    from django.contrib.auth.management import create_permissions
    from django.contrib.auth.models import Group, Permission

    if sender.label != "accounts":
        return
    core = apps.get_app_config("core")
    create_permissions(core, verbosity=0)  # make sure core permissions exist before we look them up
    wanted = [
        "add_resource", "change_resource", "delete_resource", "view_resource",
        "add_chapter", "change_chapter", "delete_chapter", "view_chapter",
        "view_subject", "view_level", "view_program",
    ]
    group, _ = Group.objects.get_or_create(name="Teachers")
    perms = list(Permission.objects.filter(content_type__app_label="core", codename__in=wanted))
    if apps.is_installed("learning"):  # teachers also create quizzes and assignments
        create_permissions(apps.get_app_config("learning"), verbosity=0)
        perms += Permission.objects.filter(
            content_type__app_label="learning",
            content_type__model__in=["quiz", "question", "choice", "assignment"],
            codename__regex=r"^(add|change|delete|view)_")
    group.permissions.set(perms)


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from . import signals  # noqa: F401
        post_migrate.connect(_create_teachers_group, sender=self)
