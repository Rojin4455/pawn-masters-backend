
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import GHLAuthCredentials
from accounts_management_app.services import fetch_all_contacts, sync_conversations_with_messages


@receiver(pre_save, sender=GHLAuthCredentials)
def trigger_on_approval(sender, instance, **kwargs):
    if not instance.pk:
        # New instance, skip
        return

    try:
        previous = GHLAuthCredentials.objects.get(pk=instance.pk)
    except GHLAuthCredentials.DoesNotExist:
        return

    # Check if is_approved changed from False to True
    if not previous.is_approved and instance.is_approved:
        if not instance.is_contact_pulled:
            fetch_all_contacts(instance.location_id, instance.access_token)
            instance.is_contact_pulled = True
            instance.save()
        if not instance.is_conversation_pulled:
            sync_conversations_with_messages(instance.location_id, instance.access_token)
            instance.is_conversation_pulled = True
            instance.save()



        # Perform your operations here
        print(f"GHLAuthCredentials {instance.id} is now approved!")