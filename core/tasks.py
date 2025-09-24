import requests
from celery import shared_task
from core.models import GHLAuthCredentials,LocationSyncLog
from decouple import config
from accounts_management_app.utils import fetch_calls_for_last_days_for_location,fetch_transactions_for_location,update_sms_segments_for_location, sync_wallet_balance
from accounts_management_app.services import fetch_all_contacts, sync_conversations_with_messages
from django.utils import timezone


@shared_task
def make_api_call():
    tokens = GHLAuthCredentials.objects.all()

    for credentials in tokens:
    
        print("credentials tokenL", credentials)
        refresh_token = credentials.refresh_token
        try:

        
            response = requests.post('https://services.leadconnectorhq.com/oauth/token', data={
                'grant_type': 'refresh_token',
                'client_id': config("GHL_CLIENT_ID"),
                'client_secret': config("GHL_CLIENT_SECRET"),
                'refresh_token': refresh_token
            })
            
            new_tokens = response.json()
            obj, created = GHLAuthCredentials.objects.update_or_create(
                    location_id= new_tokens.get("locationId"),
                    defaults={
                        "access_token": new_tokens.get("access_token"),
                        "refresh_token": new_tokens.get("refresh_token"),
                        "expires_in": new_tokens.get("expires_in"),
                        "scope": new_tokens.get("scope"),
                        "user_type": new_tokens.get("userType"),
                        "company_id": new_tokens.get("companyId"),
                        "user_id":new_tokens.get("userId"),

                    }
                )
            print("refreshed: ", obj)
        except:
            continue




# @shared_task
# def async_fetch_all_contacts(location_id, access_token):
#     fetch_all_contacts(location_id, access_token)

# @shared_task
# def async_sync_conversations_with_messages(location_id, access_token):
#     sync_conversations_with_messages(location_id)

# @shared_task
# def async_sync_conversations_with_calls(location_id, access_token):
#     credential = GHLAuthCredentials.objects.get(location_id = location_id)
#     fetch_calls_for_last_days_for_location(credential,days_to_fetch=365*5)
#     # save_conversations_with_calls(location_id)


# @shared_task
# def mark_location_synced(location_id, log_id):
#     try:
#         log = LocationSyncLog.objects.get(id=log_id)
#         log.finished_at = timezone.now()
#         log.status = "success"
#         log.save()
#     except Exception:
#         # Fallback if log not found
#         LocationSyncLog.objects.filter(id=log_id).update(
#             finished_at=timezone.now(),
#             status="failed"
#         )
#         raise


import logging
from celery import shared_task, group
from celery.exceptions import Retry
from django.utils import timezone
from .models import LocationSyncLog, GHLAuthCredentials


logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def async_fetch_all_contacts(self, location_id, access_token, log_id=None):
    """Fetch all contacts for a location with error handling"""
    try:
        if log_id:
            log = LocationSyncLog.objects.get(id=log_id)
            log.status = "fetching_contacts"
            log.save()
        
        logger.info(f"Worker {self.request.hostname}: Starting contact fetch for location {location_id}")
        fetch_all_contacts(location_id, access_token)
        logger.info(f"Worker {self.request.hostname}: Successfully completed contact fetch for location {location_id}")
        
        return f"Contacts fetched successfully for {location_id}"
        
    except Exception as exc:
        logger.error(f"Error fetching contacts for location {location_id}: {str(exc)}")
        
        if log_id:
            try:
                log = LocationSyncLog.objects.get(id=log_id)
                log.status = "failed"
                log.error_message = f"Contact fetch failed: {str(exc)}"
                log.finished_at = timezone.now()
                log.save()
            except:
                pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying contact fetch for location {location_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc)
        else:
            raise exc


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def async_sync_conversations_with_messages(self, location_id, access_token, log_id=None):
    """Sync conversations and messages for a location with error handling"""
    try:
        if log_id:
            log = LocationSyncLog.objects.get(id=log_id)
            log.status = "fetching_conversations"
            log.save()
        
        logger.info(f"Worker {self.request.hostname}: Starting conversation sync for location {location_id}")
        sync_conversations_with_messages(location_id)
        logger.info(f"Worker {self.request.hostname}: Successfully completed conversation sync for location {location_id}")
        
        return f"Conversations synced successfully for {location_id}"
        
    except Exception as exc:
        logger.error(f"Error syncing conversations for location {location_id}: {str(exc)}")
        
        if log_id:
            try:
                log = LocationSyncLog.objects.get(id=log_id)
                log.status = "failed"
                log.error_message = f"Conversation sync failed: {str(exc)}"
                log.finished_at = timezone.now()
                log.save()
            except:
                pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying conversation sync for location {location_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc)
        else:
            raise exc


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def async_sync_conversations_with_calls(self, location_id, access_token, log_id=None):
    """Sync calls for a location with error handling"""
    try:
        if log_id:
            log = LocationSyncLog.objects.get(id=log_id)
            log.status = "fetching_calls"
            log.save()
        
        logger.info(f"Worker {self.request.hostname}: Starting call sync for location {location_id}")
        credential = GHLAuthCredentials.objects.get(location_id=location_id)
        fetch_calls_for_last_days_for_location(credential, days_to_fetch=365)
        logger.info(f"Worker {self.request.hostname}: Successfully completed call sync for location {location_id}")
        
        return f"Calls synced successfully for {location_id}"
        
    except Exception as exc:
        logger.error(f"Error syncing calls for location {location_id}: {str(exc)}")
        
        if log_id:
            try:
                log = LocationSyncLog.objects.get(id=log_id)
                log.status = "failed"
                log.error_message = f"Call sync failed: {str(exc)}"
                log.finished_at = timezone.now()
                log.save()
            except:
                pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying call sync for location {location_id} (attempt {self.request.retries + 1})")
            raise self.retry(exc=exc)
        else:
            raise exc


@shared_task(bind=True)
def mark_location_synced(self, location_id, log_id):
    """Mark a location sync as completed"""
    try:
        logger.info(f"Worker {self.request.hostname}: Marking location {location_id} as synced")
        log = LocationSyncLog.objects.get(id=log_id)
        log.finished_at = timezone.now()
        log.status = "success"
        log.save()
        logger.info(f"Successfully marked location {location_id} as synced")
        return f"Location {location_id} marked as synced"
        
    except LocationSyncLog.DoesNotExist:
        logger.error(f"LocationSyncLog with id {log_id} not found")
        raise
    except Exception as exc:
        logger.error(f"Error marking location {location_id} as synced: {str(exc)}")
        try:
            LocationSyncLog.objects.filter(id=log_id).update(
                finished_at=timezone.now(),
                status="failed",
                error_message=f"Failed to mark as synced: {str(exc)}"
            )
        except:
            pass
        raise exc


# FIXED: Improved parallel processing approach
@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_single_location_parallel(self, location_id, access_token):
    """
    Process a single location using parallel tasks for better distribution
    """
    try:
        # FIXED: Get the credential object first
        credential = GHLAuthCredentials.objects.get(location_id=location_id)
        
        log = LocationSyncLog.objects.create(
            location=credential,  # Pass the credential object, not just location_id
            status="in_progress",
            started_at=timezone.now()
        )
        
        logger.info(f"Starting parallel sync for location {location_id}")
        
        # Create parallel tasks for this location with explicit queue routing
        job = group(
            async_fetch_all_contacts.apply_async(
                args=[location_id, access_token, log.id],
                queue='data_sync'
            ),
            async_sync_conversations_with_messages.apply_async(
                args=[location_id, access_token, log.id],
                queue='celery'
            ),
            async_sync_conversations_with_calls.apply_async(
                args=[location_id, access_token, log.id],
                queue='priority'
            )
        )
        
        # Wait for all tasks to complete
        results = job.get()
        
        # Mark as completed
        log.status = "success"
        log.finished_at = timezone.now()
        log.save()
        
        logger.info(f"Successfully completed parallel sync for location {location_id}")
        return f"Parallel sync completed for location {location_id}"
        
    except Exception as exc:
        logger.error(f"Error in parallel sync for location {location_id}: {str(exc)}")
        
        try:
            log.status = "failed"
            log.error_message = str(exc)
            log.finished_at = timezone.now()
            log.save()
        except:
            pass
        
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300)
        else:
            raise exc


# FIXED: Sequential processing with correct credential handling
@shared_task(bind=True, max_retries=2, default_retry_delay=300)
def sync_location_data_sequential(self, location_id, access_token, daily_fetch=False):
    """
    Sequential sync with improved logging and worker identification
    """
    try:
        # FIXED: Get the credential object first
        credential = GHLAuthCredentials.objects.get(location_id=location_id)
        
        if daily_fetch:
            fetch_calls_for_last_days_for_location(credential, days_to_fetch=2)
            fetch_transactions_for_location(ghl_credential=credential,days_ago_start=2)
            sync_wallet_balance(location_id=credential.location_id)
            update_sms_segments_for_location(ghl_credential=credential, daily_fetch=True)
        else:

            log, created = LocationSyncLog.objects.get_or_create(
                location=credential,
                finished_at__isnull=True,  # unfinished logs
                defaults={
                    "status": "in_progress",
                    "started_at": timezone.now(),
                    "task_id": self.request.id
                }
            )
                    
            logger.info(f"Worker {self.request.hostname}: Starting sequential sync for location {location_id}")
            
            # # Step 1: Fetch Contacts
            # logger.info(f"Worker {self.request.hostname}: Step 1/3 - Fetching contacts for location {location_id}")
            # log.status = "fetching_contacts"
            # log.save()
            # fetch_all_contacts(location_id, access_token)
            
            # # Step 2: Sync Conversations and Messages
            # logger.info(f"Worker {self.request.hostname}: Step 2/3 - Syncing conversations for location {location_id}")
            # log.status = "fetching_conversations"
            # log.save()
            # sync_conversations_with_messages(location_id)
            
            # Step 3: Sync Calls
            logger.info(f"Worker {self.request.hostname}: Step 3/3 - Syncing calls for location {location_id}")
            log.status = "fetching_calls"
            log.save()
            fetch_calls_for_last_days_for_location(credential, days_to_fetch=190)


            logger.info(f"Worker {self.request.hostname}: Step 3.1/3 - Syncing transaction for location {location_id}")
            log.status = "fetching_transactions"
            log.save()

            fetch_transactions_for_location(ghl_credential=credential,days_ago_start=183)

            

            log.status = "fetching_segments"
            log.save()

            sync_wallet_balance(location_id=credential.location_id)


            update_sms_segments_for_location(ghl_credential=credential)

            
            # Mark as completed
            log.status = "success"
            log.finished_at = timezone.now()
            log.save()
            
            logger.info(f"Worker {self.request.hostname}: Successfully completed sequential sync for location {location_id}")
            return f"Sequential sync completed for location {location_id}"
        
    except Exception as exc:
        logger.error(f"Worker {self.request.hostname}: Error in sequential sync for location {location_id}: {str(exc)}")
        
        try:
            log.status = "failed"
            log.error_message = str(exc)
            log.finished_at = timezone.now()
            log.save()
        except:
            pass
        
        if self.request.retries < self.max_retries:
            logger.info(f"Retrying sequential sync for location {location_id}")
            raise self.retry(exc=exc, countdown=300)
        else:
            raise exc
        


@shared_task(bind=True)
def test_task(self, message="Hello"):
    """Test task to verify worker is functioning"""
    logger.info(f"Worker {self.request.hostname}: Test task executed with message: {message}")
    return f"Test task completed on {self.request.hostname}: {message}"



@shared_task
def daily_sync_all_locations(daily_fetch=True):
    """
    Loop over all approved GHLAuthCredentials and trigger sequential sync for each,
    assigning them to queues using round-robin logic.
    """
    credentials = GHLAuthCredentials.objects.filter(is_approved=True)
    total_locations = credentials.count()
    
    print(f"[{timezone.now()}] Starting daily sync for {total_locations} locations")

    queues = ['data_sync', 'celery', 'priority']

    for idx, cred in enumerate(credentials):
        # Round-robin queue selection
        queue = queues[idx % len(queues)]

        # Create a pending log
        log = LocationSyncLog.objects.create(
            location=cred,
            status="pending",
            started_at=timezone.now()
        )

        # Trigger sequential sync task on selected queue
        result = sync_location_data_sequential.apply_async(
            kwargs={
                "location_id": cred.location_id,
                "access_token": cred.access_token,
                "daily_fetch": daily_fetch
            },
            queue=queue
        )

        print(f"[{timezone.now()}] GHLAuthCredentials {cred.id} scheduled! "
              f"Sync started on queue {queue}, task_id={result.id}, log_id={log.id}")

    print(f"[{timezone.now()}] Scheduled sync for all approved locations")