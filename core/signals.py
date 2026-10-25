"""Keep Subject.books_count / videos_count in sync and clean up uploaded files."""
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from .models import Resource, Subject


@receiver(pre_save, sender=Resource)
def _remember_old_state(sender, instance, **kwargs):
    instance._old_subject_id = None
    instance._old_file = None
    if instance.pk:
        old = Resource.objects.filter(pk=instance.pk).only("subject_id", "file").first()
        if old:
            instance._old_subject_id = old.subject_id
            instance._old_file = old.file if old.file else None


@receiver(post_save, sender=Resource)
def _after_save(sender, instance, **kwargs):
    instance.subject.refresh_counts()
    old_subject = getattr(instance, "_old_subject_id", None)
    if old_subject and old_subject != instance.subject_id:
        previous = Subject.objects.filter(pk=old_subject).first()
        if previous:
            previous.refresh_counts()
    # replaced file -> delete the old one from disk
    old_file = getattr(instance, "_old_file", None)
    if old_file and old_file.name != (instance.file.name if instance.file else None):
        old_file.delete(save=False)


@receiver(post_delete, sender=Resource)
def _after_delete(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)
    subject = Subject.objects.filter(pk=instance.subject_id).first()
    if subject:
        subject.refresh_counts()
