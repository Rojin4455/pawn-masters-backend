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
