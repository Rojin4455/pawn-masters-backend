import requests
from celery import shared_task
from core.models import GHLAuthCredentials,LocationSyncLog
from decouple import config
from accounts_management_app.utils import fetch_calls_for_last_days_for_location
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




@shared_task
def async_fetch_all_contacts(location_id, access_token):
    fetch_all_contacts(location_id, access_token)

@shared_task
def async_sync_conversations_with_messages(location_id, access_token):
    sync_conversations_with_messages(location_id)

@shared_task
def async_sync_conversations_with_calls(location_id, access_token):
    credential = GHLAuthCredentials.objects.get(location_id = location_id)
    fetch_calls_for_last_days_for_location(credential,days_to_fetch=365*5)
    # save_conversations_with_calls(location_id)


@shared_task
def mark_location_synced(location_id, log_id):
    try:
        log = LocationSyncLog.objects.get(id=log_id)
        log.finished_at = timezone.now()
        log.status = "success"
        log.save()
    except Exception:
        # Fallback if log not found
        LocationSyncLog.objects.filter(id=log_id).update(
            finished_at=timezone.now(),
            status="failed"
        )
        raise