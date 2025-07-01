
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import GHLAuthCredentials
from accounts_management_app.services import fetch_all_contacts, sync_conversations_with_messages
from .tasks import async_fetch_all_contacts, async_sync_conversations_with_messages
from celery import chain



@receiver(pre_save, sender=GHLAuthCredentials)
def trigger_on_approval(sender, instance, **kwargs):
    if not instance.pk:
        # New instance, skip
        return

    try:
        previous = GHLAuthCredentials.objects.get(pk=instance.pk)
    except GHLAuthCredentials.DoesNotExist:
        return

    if not previous.is_approved and instance.is_approved:
        tasks_to_run = []
        
        if not instance.is_contact_pulled:
            tasks_to_run.append(async_fetch_all_contacts.si(instance.location_id, instance.access_token))
            instance.is_contact_pulled = True

        if not instance.is_conversation_pulled:
            tasks_to_run.append(async_sync_conversations_with_messages.si(instance.location_id, instance.access_token))
            instance.is_conversation_pulled = True

        if not instance.is_calls_pulled:
            tasks_to_run.append(async_sync_conversations_with_messages.si(instance.location_id, instance.access_token))
            instance.is_conversation_pulled = True

        if tasks_to_run:
            chain(*tasks_to_run).delay()
            instance.save()


        # Perform your operations here
        print(f"GHLAuthCredentials {instance.id} is now approved!")