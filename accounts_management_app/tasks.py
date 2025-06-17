from celery import shared_task
from core.models import GHLAuthCredentials
from django.utils.dateparse import parse_datetime
from accounts_management_app.helpers import create_or_update_contact, delete_contact

import requests
import math
from django.utils.dateparse import parse_datetime
from datetime import datetime
from zoneinfo import ZoneInfo

from accounts_management_app.models import Contact, GHLConversation, TextMessage



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


def handle_message_event(data):
    """
    Handle OutboundMessage and InboundMessage webhook events.
    Creates SMS record and fetches conversation if it doesn't exist.
    """
    try:
        location_id = data.get("locationId")
        conversation_id = data.get("conversationId")
        contact_id = data.get("contactId")
        message_type = data.get("messageType")
        
        # Only process SMS messages for now
        if message_type not in ["SMS"]:
            print(f"Skipping non-SMS message type: {message_type}")
            return
        
        if not all([location_id, conversation_id, contact_id]):
            print(f"Missing required fields: location_id={location_id}, conversation_id={conversation_id}, contact_id={contact_id}")
            return
        
        # Get GHL credentials for this location
        try:
            ghl_creds = GHLAuthCredentials.objects.get(location_id=location_id)
        except GHLAuthCredentials.DoesNotExist:
            print(f"No GHL credentials found for location_id: {location_id}")
            return
        
        # Get timezone for date conversion
        location_tz = ZoneInfo(ghl_creds.timezone or "UTC")
        
        # Check if conversation exists, if not fetch it
        conversation = None
        try:
            conversation = GHLConversation.objects.get(conversation_id=conversation_id)
            print(f"Found existing conversation: {conversation_id}")
        except GHLConversation.DoesNotExist:
            print(f"Conversation {conversation_id} not found, fetching from GHL...")
            conversation = fetch_and_create_conversation(
                conversation_id, 
                location_id, 
                ghl_creds.access_token,
                ghl_creds
            )
        
        if not conversation:
            print(f"Failed to get or create conversation: {conversation_id}")
            return
        
        # Check if contact exists, if not fetch it
        contact = None
        try:
            contact = Contact.objects.get(contact_id=contact_id)
        except Contact.DoesNotExist:
            print(f"Contact {contact_id} not found, fetching from GHL...")
            contact = fetch_and_create_contact(contact_id, location_id, ghl_creds.access_token)
        
        # Create the SMS message record
        create_sms_from_webhook(data, conversation, location_tz)
        
    except Exception as e:
        print(f"Error in handle_message_event: {str(e)}")


def fetch_and_create_contact(contact_id, location_id, access_token):
    """
    Fetch a single contact from GHL API and create it locally.
    """
    try:
        url = f"https://services.leadconnectorhq.com/contacts/{contact_id}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Version": "2021-07-28"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Failed to fetch contact {contact_id}: {response.text}")
            return None
        
        contact_data = response.json().get("contact", {})
        
        if not contact_data:
            print(f"No contact data returned for {contact_id}")
            return None
        
        # Create contact object
        date_added = parse_datetime(contact_data.get("dateAdded")) if contact_data.get("dateAdded") else None
        
        contact = Contact.objects.create(
            contact_id=contact_data.get("id"),
            first_name=contact_data.get("firstName"),
            last_name=contact_data.get("lastName"),
            phone=contact_data.get("phone"),
            email=contact_data.get("email"),
            dnd=contact_data.get("dnd", False),
            country=contact_data.get("country"),
            date_added=date_added,
            tags=contact_data.get("tags", []),
            custom_fields=contact_data.get("customFields", []),
            location_id=contact_data.get("locationId"),
            timestamp=date_added
        )
        
        print(f"Created contact: {contact.contact_id}")
        return contact
        
    except Exception as e:
        print(f"Error fetching contact {contact_id}: {str(e)}")
        return None


def fetch_and_create_conversation(conversation_id, location_id, access_token, ghl_creds):
    """
    Fetch a single conversation from GHL API and create it locally.
    """
    try:
        url = f"https://services.leadconnectorhq.com/conversations/{conversation_id}"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Version": "2021-04-15"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code != 200:
            print(f"Failed to fetch conversation {conversation_id}: {response.text}")
            return None
        
        conv_data = response.json()
        
        if not conv_data:
            print(f"No conversation data returned for {conversation_id}")
            return None
        
        # Get contact if it exists
        contact_id = conv_data.get("contactId")
        contact = None
        if contact_id:
            try:
                contact = Contact.objects.get(contact_id=contact_id)
            except Contact.DoesNotExist:
                # Fetch contact if it doesn't exist
                contact = fetch_and_create_contact(contact_id, location_id, access_token)
        
        # Helper function to convert timestamps
        location_tz = ZoneInfo(ghl_creds.timezone or "UTC")
        
        def to_datetime(ts):
            if ts:
                try:
                    if isinstance(ts, str):
                        # Handle ISO string format
                        return parse_datetime(ts)
                    else:
                        # Handle timestamp format
                        utc_dt = datetime.utcfromtimestamp(ts / 1000).replace(tzinfo=ZoneInfo("UTC"))
                        return utc_dt.astimezone(location_tz)
                except:
                    return None
            return None
        
        # Create conversation
        conversation = GHLConversation.objects.create(
            conversation_id=conv_data.get("id"),
            location=ghl_creds,
            contact=contact,
            last_message_body=conv_data.get("lastMessageBody"),
            last_message_type=conv_data.get("lastMessageType"),
            last_message_direction=conv_data.get("lastMessageDirection"),
            last_outbound_action=conv_data.get("lastOutboundMessageAction"),
            unread_count=conv_data.get("unreadCount", 0),
            date_added=to_datetime(conv_data.get("dateAdded")),
            date_updated=to_datetime(conv_data.get("dateUpdated")),
            last_manual_message_date=to_datetime(conv_data.get("lastManualMessageDate")),
            tags=conv_data.get("tags", [])
        )
        
        print(f"Created conversation: {conversation.conversation_id}")
        return conversation
        
    except Exception as e:
        print(f"Error fetching conversation {conversation_id}: {str(e)}")
        return None


def create_sms_from_webhook(data, conversation, location_tz):
    """
    Create SMS message record from webhook data.
    """
    try:
        message_id = data.get("messageId")
        
        # Check if message already exists
        if TextMessage.objects.filter(message_id=message_id).exists():
            print(f"Message {message_id} already exists, skipping")
            return
        
        # Convert date
        def to_local_dt(date_str):
            try:
                if date_str:
                    return datetime.fromisoformat(date_str.replace('Z', '+00:00')).astimezone(location_tz)
                return None
            except Exception as e:
                print(f"Date parse error: {e}")
                return None
        
        # Calculate message segments
        body = data.get("body", "")
        body_length = len(body)
        segments = math.ceil(body_length / 160) if body_length > 0 else 1
        
        # Create the message
        message = TextMessage.objects.create(
            message_id=message_id,
            conversation=conversation,
            body=body,
            content_type=data.get("contentType", "text/plain"),
            message_type="TYPE_SMS",
            direction=data.get("direction", ""),
            status=data.get("status", ""),
            type=2,
            source=data.get("source", ""),
            user_id=data.get("userId", ""),
            attachments=data.get("attachments", []),
            date_added=to_local_dt(data.get("dateAdded")),
            body_length=body_length,
            segments=segments
        )
        
        print(f"Created SMS message: {message_id} with {segments} segments")
        return message
        
    except Exception as e:
        print(f"Error creating SMS from webhook: {str(e)}")
        return None