from celery import shared_task
from core.models import GHLAuthCredentials
from django.utils.dateparse import parse_datetime
from accounts_management_app.helpers import create_or_update_contact, delete_contact, handle_message_event

import requests
import math
from django.utils.dateparse import parse_datetime
from datetime import datetime
from zoneinfo import ZoneInfo

from accounts_management_app.models import Contact, GHLConversation, TextMessage
from accounts_management_app.utils import sync_wallet_balance,process_all_ghl_locations_for_calls,fetch_calls_for_last_days_for_location



@shared_task
def handle_webhook_event(data, event_type):
    try:
        if event_type in ["ContactCreate", "ContactUpdate"]:
            create_or_update_contact(data)
        elif event_type == "ContactDelete":
            delete_contact(data)
        elif event_type in ["OutboundMessage", "InboundMessage"]:
            handle_message_event(data)
        else:
            print(f"Unhandled event type: {event_type}")
    except Exception as e:
        print(f"Error handling webhook event {event_type}: {str(e)}")




@shared_task
def refresh_wallet_balance_and_sync_call():
    sync_wallet_balance()
    process_all_ghl_locations_for_calls()




@shared_task
def fetch_calls_task(credential_id):
    try:
        credential = GHLAuthCredentials.objects.get(id=credential_id)
        fetch_calls_for_last_days_for_location(credential)
    except GHLAuthCredentials.DoesNotExist:
        # Log this instead of raising for silent failure
        pass


@shared_task
def refresh_all_sync_call_for_last_750_day():
    # sync_wallet_balance()
    # process_all_ghl_locations_for_calls()
    """
    Fetches calls for all GHL locations configured in the database.
    """
    ghl_credentials = GHLAuthCredentials.objects.all()
    if not ghl_credentials.exists():
        print("No GHLAuthCredentials found in the database. Please add locations.")
        return

    for credential in ghl_credentials:
        # if credential.location_id in ['jl8fn7mpZ2UUZ6ZCOus8']:
        print(f"\n--- Processing location: {credential.location_name} (ID: {credential.location_id}) ---")
        fetch_calls_for_last_days_for_location(credential,days_to_fetch=750)
        print(f"--- Finished processing for {credential.location_name} ---\n")