
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import GHLAuthCredentials, LocationSyncLog
from accounts_management_app.services import fetch_all_contacts, sync_conversations_with_messages
from .tasks import async_fetch_all_contacts, async_sync_conversations_with_messages,async_sync_conversations_with_calls,sync_location_data_sequential
# from celery import chain
from celery import group
from django.utils import timezone




# @receiver(pre_save, sender=GHLAuthCredentials)
# def trigger_on_approval(sender, instance, **kwargs):
#     if not instance.pk:
#         # New instance, skip
#         return

#     try:
#         previous = GHLAuthCredentials.objects.get(pk=instance.pk)
#     except GHLAuthCredentials.DoesNotExist:
#         return

#     if not previous.is_approved and instance.is_approved:
#         tasks_to_run = []
        
#         if not instance.is_contact_pulled:
#             tasks_to_run.append(async_fetch_all_contacts.si(instance.location_id, instance.access_token))
#             instance.is_contact_pulled = True

#         if not instance.is_conversation_pulled:
#             tasks_to_run.append(async_sync_conversations_with_messages.si(instance.location_id, instance.access_token))
#             instance.is_conversation_pulled = True

#         if not instance.is_calls_pulled:
#             tasks_to_run.append(async_sync_conversations_with_calls.si(instance.location_id, instance.access_token))
#             instance.is_calls_pulled = True

#         # if tasks_to_run:
#         #     chain(*tasks_to_run).delay()
#         #     instance.save()

#         if tasks_to_run:
#             group(tasks_to_run).apply_async()


#         # Perform your operations here
#         print(f"GHLAuthCredentials {instance.id} is now approved!")



@receiver(pre_save, sender=GHLAuthCredentials)
def trigger_on_approval(sender, instance, **kwargs):
    if not instance.pk:
        return

    try:
        previous = GHLAuthCredentials.objects.get(pk=instance.pk)
    except GHLAuthCredentials.DoesNotExist:
        return

    # When approval changes from False → True
    if not previous.is_approved and instance.is_approved:
        # Pick queue using round robin logic
        queues = ['data_sync', 'celery', 'priority']
        cred_count = GHLAuthCredentials.objects.filter(is_approved=True).count()
        queue = queues[cred_count % len(queues)]

        log = LocationSyncLog.objects.create(
            location=instance,
            status="pending",
            started_at=timezone.now()
        )

        result = sync_location_data_sequential.apply_async(
            args=[instance.location_id, instance.access_token],
            queue=queue
        )

        print(f"GHLAuthCredentials {instance.id} is now approved! "
              f"Sync started on queue {queue}, task_id={result.id}, log_id={log.id}")