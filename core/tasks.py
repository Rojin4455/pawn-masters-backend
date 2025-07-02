import requests
from celery import shared_task
from core.models import GHLAuthCredentials
from decouple import config
from accounts_management_app.services import fetch_all_contacts, sync_conversations_with_messages, save_conversations_with_calls

@shared_task
def make_api_call():
    tokens = GHLAuthCredentials.objects.all()

    for credentials in tokens:
    
        print("credentials tokenL", credentials)
        refresh_token = credentials.refresh_token

        
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




@shared_task
def async_fetch_all_contacts(location_id, access_token):
    fetch_all_contacts(location_id, access_token)

@shared_task
def async_sync_conversations_with_messages(location_id, access_token):
    sync_conversations_with_messages(location_id)

@shared_task
def async_sync_conversations_with_calls(location_id, access_token):
    save_conversations_with_calls(location_id, access_token)