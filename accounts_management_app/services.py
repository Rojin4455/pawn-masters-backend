import requests
import time
from typing import List, Dict, Any, Optional
from django.utils.dateparse import parse_datetime
from django.db import transaction
from accounts_management_app.models import Contact, GHLConversation, TextMessage, CallRecord
from core.models import GHLAuthCredentials
from django.utils.timezone import make_aware
from datetime import datetime
from zoneinfo import ZoneInfo
import math








def fetch_all_contacts(location_id: str, access_token: str = None) -> List[Dict[str, Any]]:
    """
    Fetch all contacts from GoHighLevel API with proper pagination handling.
    
    Args:
        location_id (str): The location ID for the subaccount
        access_token (str, optional): Bearer token for authentication
        
    Returns:
        List[Dict]: List of all contacts
    """

    
    
    
    
    base_url = "https://services.leadconnectorhq.com/contacts/"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28"
    }
    
    all_contacts = []
    start_after = None
    start_after_id = None
    page_count = 0
    
    while True:
        page_count += 1
        print(f"Fetching page {page_count}...")
        
        # Set up parameters for current request
        params = {
            "locationId": location_id,
            "limit": 100,  # Maximum allowed by API
        }
        
        # Add pagination parameters if available
        if start_after:
            params["startAfter"] = start_after
        if start_after_id:
            params["startAfterId"] = start_after_id
            
        try:
            response = requests.get(base_url, headers=headers, params=params)
            
            if response.status_code != 200:
                print(f"Error Response: {response.status_code}")
                print(f"Error Details: {response.text}")
                raise Exception(f"API Error: {response.status_code}, {response.text}")
            
            data = response.json()
            
            # Get contacts from response
            contacts = data.get("contacts", [])
            if not contacts:
                print("No more contacts found.")
                break
                
            all_contacts.extend(contacts)
            print(f"Retrieved {len(contacts)} contacts. Total so far: {len(all_contacts)}")
            
            # Check if there are more pages
            # GoHighLevel API uses cursor-based pagination
            meta = data.get("meta", {})
            
            # Update pagination cursors for next request
            if contacts:  # If we got contacts, prepare for next page
                last_contact = contacts[-1]
                
                # Get the ID for startAfterId (this should be a string)
                if "id" in last_contact:
                    start_after_id = last_contact["id"]
                
                # Get timestamp for startAfter (this must be a number/timestamp)
                start_after = None
                if "dateAdded" in last_contact:
                    # Convert to timestamp if it's a string
                    date_added = last_contact["dateAdded"]
                    if isinstance(date_added, str):
                        try:
                            from datetime import datetime
                            # Try parsing ISO format
                            dt = datetime.fromisoformat(date_added.replace('Z', '+00:00'))
                            start_after = int(dt.timestamp() * 1000)  # Convert to milliseconds
                        except:
                            # Try parsing as timestamp
                            try:
                                start_after = int(float(date_added))
                            except:
                                pass
                    elif isinstance(date_added, (int, float)):
                        start_after = int(date_added)
                        
                elif "createdAt" in last_contact:
                    created_at = last_contact["createdAt"]
                    if isinstance(created_at, str):
                        try:
                            from datetime import datetime
                            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                            start_after = int(dt.timestamp() * 1000)
                        except:
                            try:
                                start_after = int(float(created_at))
                            except:
                                pass
                    elif isinstance(created_at, (int, float)):
                        start_after = int(created_at)
            
            # Check if we've reached the end
            total_count = meta.get("total", 0)
            if total_count > 0 and len(all_contacts) >= total_count:
                print(f"Retrieved all {total_count} contacts.")
                break
                
            # If we got fewer contacts than the limit, we're likely at the end
            if len(contacts) < 100:
                print("Retrieved fewer contacts than limit, likely at end.")
                break
                
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            raise
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise
            
        # Add a small delay to be respectful to the API
        time.sleep(0.1)
        
        # Safety check to prevent infinite loops
        if page_count > 1000:  # Adjust based on expected contact count
            print("Warning: Stopped after 1000 pages to prevent infinite loop")
            break
    
    print(f"\nTotal contacts retrieved: {len(all_contacts)}")

    sync_contacts_to_db(all_contacts)
    # return all_contacts




def sync_contacts_to_db(contact_data):
    """
    Syncs contact data from API into the local Contact model using bulk upsert.
    
    Args:
        contact_data (list): List of contact dicts from GoHighLevel API
    """
    contacts_to_create = []
    existing_ids = set(Contact.objects.filter(contact_id__in=[c['id'] for c in contact_data]).values_list('contact_id', flat=True))

    for item in contact_data:
        date_added = parse_datetime(item.get("dateAdded")) if item.get("dateAdded") else None
        

        contact_obj = Contact(
            contact_id=item.get("id"),
            first_name=item.get("firstName"),
            last_name=item.get("lastName"),
            phone=item.get("phone"),
            email=item.get("email"),
            dnd=item.get("dnd", False),
            country=item.get("country"),
            date_added=date_added,
            tags=item.get("tags", []),
            custom_fields=item.get("customFields", []),
            location_id=item.get("locationId"),
            timestamp=date_added
        )

        if item.get("id") in existing_ids:
            # Update existing contact
            Contact.objects.filter(contact_id=item["id"]).update(
                first_name=contact_obj.first_name,
                last_name=contact_obj.last_name,
                phone=contact_obj.phone,
                email=contact_obj.email,
                dnd=contact_obj.dnd,
                country=contact_obj.country,
                date_added=contact_obj.date_added,
                tags=contact_obj.tags,
                custom_fields=contact_obj.custom_fields,
                location_id=contact_obj.location_id,
                timestamp=contact_obj.timestamp
            )
        else:
            contacts_to_create.append(contact_obj)

    if contacts_to_create:
        with transaction.atomic():
            Contact.objects.bulk_create(contacts_to_create, ignore_conflicts=True)

    print(f"{len(contacts_to_create)} new contacts created.")
    print(f"{len(existing_ids)} existing contacts updated.")





def sync_conversation_text_messages(conversation_id, location_id, access_token):
    """
    Sync all SMS messages for a specific conversation from GHL to the local DB.
    """

    # Get location and timezone
    try:
        location = GHLAuthCredentials.objects.get(location_id=location_id)
        tz = ZoneInfo(location.timezone or "UTC")
    except GHLAuthCredentials.DoesNotExist:
        print(f"Location {location_id} not found.")
        return 0
    except Exception as e:
        print(f"Timezone error: {e}")
        return 0

    # Get conversation instance
    try:
        conversation = GHLConversation.objects.get(conversation_id=conversation_id)
    except GHLConversation.DoesNotExist:
        print(f"Conversation {conversation_id} not found.")
        return 0

    base_url = f"https://services.leadconnectorhq.com/conversations/{conversation_id}/messages?type=TYPE_SMS"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Version": "2021-04-15"
    }

    def to_local_dt(date_str):
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).astimezone(tz) if date_str else None
        except Exception as e:
            print(f"Date parse error: {e}")
            return None

    def build_message_obj(msg):
        return TextMessage(
            message_id=msg["id"],
            conversation=conversation,
            body=msg.get("body", ""),
            content_type=msg.get("contentType", "text/plain"),
            message_type=msg.get("messageType", "TYPE_SMS"),
            direction=msg.get("direction", ""),
            status=msg.get("status", ""),
            type=msg.get("type", 0),
            source=msg.get("source", ""),
            user_id=msg.get("userId", ""),
            attachments=msg.get("attachments", []),
            date_added=to_local_dt(msg.get("dateAdded")),
            body_length=len(msg.get("body", "")),
            segments=math.ceil(len(msg.get("body", "")) / 160)
        )

    all_messages = []
    last_message_id = None
    page = 0

    while True:
        page += 1
        params = {"lastMessageId": last_message_id} if last_message_id else {}

        print(f"Fetching page {page} for conversation {conversation_id}")
        res = requests.get(base_url, headers=headers, params=params)

        if res.status_code != 200:
            print(f"Failed: {res.text}")
            break

        data = res.json().get("messages", {})
        messages = data.get("messages", [])
        if not messages:
            break

        all_messages += [build_message_obj(msg) for msg in messages]
        last_message_id = messages[-1]["id"]

        if not data.get("nextPage") or page > 100:
            break

    # Save to DB
    if not all_messages:
        return 0

    try:
        with transaction.atomic():
            existing_ids = set(
                TextMessage.objects.filter(
                    message_id__in=[m.message_id for m in all_messages]
                ).values_list("message_id", flat=True)
            )

            to_create = [m for m in all_messages if m.message_id not in existing_ids]
            to_update_map = {m.message_id: m for m in all_messages if m.message_id in existing_ids}

            if to_create:
                TextMessage.objects.bulk_create(to_create, ignore_conflicts=True)

            if to_update_map:
                existing = TextMessage.objects.filter(message_id__in=to_update_map.keys())
                for msg in existing:
                    new_data = to_update_map[msg.message_id]
                    if msg.status != new_data.status:
                        msg.status = new_data.status
                TextMessage.objects.bulk_update(existing, ['status'])

        print(f"Synced {len(all_messages)} messages ({len(to_create)} new)")
    except Exception as e:
        print(f"Error during DB sync: {e}")

    return len(all_messages)




def sync_conversations_with_messages(location_id):

    
    token = GHLAuthCredentials.objects.get(location_id=location_id)
    access_token = token.access_token
    """
    Enhanced version of sync_conversations that also syncs messages for each conversation
    """
    base_url = "https://services.leadconnectorhq.com/conversations/search"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-04-15"
    }
    
    # Get location object and timezone
    try:
        location_instance = GHLAuthCredentials.objects.get(location_id=location_id)
        location_timezone_str = location_instance.timezone or "UTC"
        location_tz = ZoneInfo(location_timezone_str)
    except GHLAuthCredentials.DoesNotExist:
        print(f"Location {location_id} not found.")
        return
    except Exception as e:
        print(f"Invalid timezone: {e}")
        return
    
    all_conversations = []
    limit = 100
    start_after_id = None
    start_after_date = None
    total_fetched = 0
    page = 0
    
    # First, sync all conversations (your existing logic)
    while True:
        page += 1
        params = {
            "locationId": location_id,
            "lastMessageType": "TYPE_SMS",
            "limit": limit
        }
        
        if start_after_date:
            params["startAfterDate"] = start_after_date
        
        print(f"Making request for page {page} with params: {params}")
        
        response = requests.get(base_url, headers=headers, params=params)
        
        if response.status_code != 200:
            print(f"Failed to fetch conversations: {response.text}")
            break
        
        data = response.json()
        conversations = data.get("conversations", [])
        total_conversations = data.get("total", 0)
        
        if not conversations:
            print("No more conversations found.")
            break
        
        print(f"Fetched {len(conversations)} conversations in this batch (page {page})")
        total_fetched += len(conversations)
        
        # Check for duplicate conversations
        conversation_ids_in_batch = [conv["id"] for conv in conversations]
        existing_ids_in_all = [conv.conversation_id for conv in all_conversations]
        
        duplicate_count = len(set(conversation_ids_in_batch) & set(existing_ids_in_all))
        if duplicate_count > 0:
            print(f"Found {duplicate_count} duplicate conversations - pagination may be looping")
            if duplicate_count == len(conversations):
                print("All conversations in this batch are duplicates. Stopping pagination.")
                break
        
        # Process conversations for this batch
        batch_conversations = []
        
        for conv in conversations:
            contact_id = conv.get("contactId")
            contact = Contact.objects.filter(contact_id=contact_id).first()
            
            conv_id = conv["id"]
            
            def to_datetime(ts):
                if ts:
                    utc_dt = datetime.utcfromtimestamp(ts / 1000).replace(tzinfo=ZoneInfo("UTC"))
                    return utc_dt.astimezone(location_tz)
                return None
            
            conversation_data = GHLConversation(
                conversation_id=conv_id,
                location=location_instance,
                contact=contact,
                last_message_body=conv.get("lastMessageBody"),
                last_message_type=conv.get("lastMessageType"),
                last_message_direction=conv.get("lastMessageDirection"),
                last_outbound_action=conv.get("lastOutboundMessageAction"),
                unread_count=conv.get("unreadCount", 0),
                date_added=to_datetime(conv.get("dateAdded")),
                date_updated=to_datetime(conv.get("dateUpdated")),
                last_manual_message_date=to_datetime(conv.get("lastManualMessageDate")),
                tags=conv.get("tags", [])
            )
            batch_conversations.append(conversation_data)
        
        all_conversations.extend(batch_conversations)
        
        # Get the last conversation for next iteration
        last_conversation = conversations[-1]
        last_conversation_id = last_conversation["id"]
        last_message_date = last_conversation.get("lastMessageDate")
        
        # Check termination conditions
        if (len(conversations) < limit or 
            total_fetched >= total_conversations or 
            last_conversation_id == start_after_id):
            print(f"Reached end of conversations. Total fetched: {total_fetched}")
            if last_conversation_id == start_after_id:
                print("Detected pagination loop - same startAfterId returned. Stopping.")
            break
        
        # Set pagination parameters for next request
        start_after_id = last_conversation_id
        if last_message_date:
            start_after_date = last_message_date
        
        # Safety break
        if page > 50:
            print(f"Reached maximum page limit ({page}). Stopping to prevent infinite loop.")
            break
    
    # Save conversations to database
    if all_conversations:
        try:
            from django.db import transaction
            
            with transaction.atomic():
                existing_ids = set(GHLConversation.objects.filter(
                    conversation_id__in=[c.conversation_id for c in all_conversations]
                ).values_list("conversation_id", flat=True))
                
                to_create = []
                to_update_data = []
                
                for conv in all_conversations:
                    if conv.conversation_id not in existing_ids:
                        to_create.append(conv)
                    else:
                        to_update_data.append({
                            'conversation_id': conv.conversation_id,
                            'last_message_body': conv.last_message_body,
                            'last_message_type': conv.last_message_type,
                            'last_message_direction': conv.last_message_direction,
                            'last_outbound_action': conv.last_outbound_action,
                            'unread_count': conv.unread_count,
                            'date_updated': conv.date_updated,
                            'last_manual_message_date': conv.last_manual_message_date,
                            'tags': conv.tags
                        })
                
                created_count = 0
                if to_create:
                    GHLConversation.objects.bulk_create(to_create, ignore_conflicts=True)
                    created_count = len(to_create)
                    print(f"Created {created_count} new conversations.")
                
                updated_count = 0
                if to_update_data:
                    existing_conversations = GHLConversation.objects.filter(
                        conversation_id__in=[data['conversation_id'] for data in to_update_data]
                    )
                    
                    update_mapping = {data['conversation_id']: data for data in to_update_data}
                    conversations_to_update = []
                    
                    for conv in existing_conversations:
                        update_data = update_mapping.get(conv.conversation_id)
                        if update_data:
                            conv.last_message_body = update_data['last_message_body']
                            conv.last_message_type = update_data['last_message_type']
                            conv.last_message_direction = update_data['last_message_direction']
                            conv.last_outbound_action = update_data['last_outbound_action']
                            conv.unread_count = update_data['unread_count']
                            conv.date_updated = update_data['date_updated']
                            conv.last_manual_message_date = update_data['last_manual_message_date']
                            conv.tags = update_data['tags']
                            conversations_to_update.append(conv)
                    
                    if conversations_to_update:
                        GHLConversation.objects.bulk_update(
                            conversations_to_update,
                            ['last_message_body', 'last_message_type', 'last_message_direction',
                             'last_outbound_action', 'unread_count', 'date_updated',
                             'last_manual_message_date', 'tags']
                        )
                        updated_count = len(conversations_to_update)
                        print(f"Updated {updated_count} existing conversations.")
                
                print(f"Successfully processed {len(all_conversations)} conversations ({created_count} new, {updated_count} updated).")
                
        except Exception as e:
            print(f"Error processing conversations: {e}")
            try:
                with transaction.atomic():
                    GHLConversation.objects.bulk_create(all_conversations, ignore_conflicts=True)
                    print(f"Fallback successful: Processed {len(all_conversations)} conversations.")
            except Exception as fallback_e:
                print(f"Fallback also failed: {fallback_e}")
                return
            
    # save_conversations_with_messges(location_id, access_token)
    


def save_conversations_with_messges(location_id, access_token):
    all_conversations = GHLConversation.objects.filter(location__location_id=location_id)
    # Now sync messages for each conversation
    print("\n" + "="*50)
    print("STARTING MESSAGE SYNC FOR ALL CONVERSATIONS")
    print("="*50)
    
    # Get all conversation IDs that were just processed
    conversation_ids = [conv.conversation_id for conv in all_conversations]
    total_messages_synced = 0
    
    for i, conv_id in enumerate(conversation_ids, 1):
        print(f"\nSyncing messages for conversation {i}/{len(conversation_ids)}: {conv_id}")
        messages_count = sync_conversation_text_messages(conv_id, location_id, access_token)
        
        total_messages_synced += messages_count
        
        # Optional: Add a small delay to avoid rate limiting
        import time
        time.sleep(0.1)  # 100ms delay between requests
    
    print(f"\n" + "="*50)
    print(f"SYNC COMPLETED")
    print(f"Total conversations processed: {len(all_conversations)}")
    print(f"Total messages synced: {total_messages_synced}")
    print("="*50)




def sync_conversation_calls(conversation_id, location_id, access_token):
    """
    Sync all call records for a specific conversation from GHL to the local DB.
    """

    # Get location and timezone
    try:
        location = GHLAuthCredentials.objects.get(location_id=location_id)
        tz = ZoneInfo(location.timezone or "UTC")
    except GHLAuthCredentials.DoesNotExist:
        print(f"Location {location_id} not found.")
        return 0
    except Exception as e:
        print(f"Timezone error: {e}")
        return 0

    # Get conversation instance
    try:
        conversation = GHLConversation.objects.get(conversation_id=conversation_id)
    except GHLConversation.DoesNotExist:
        print(f"Conversation {conversation_id} not found.")
        return 0

    base_url = f"https://services.leadconnectorhq.com/conversations/{conversation_id}/messages?type=TYPE_CALL"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Version": "2021-04-15"
    }

    def to_local_dt(date_str):
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00')).astimezone(tz) if date_str else None
        except Exception as e:
            print(f"Date parse error: {e}")
            return None

    def build_call_obj(msg):
        # Extract call metadata
        call_meta = msg.get("meta", {}).get("call", {})
        duration = call_meta.get("duration", 0)
        
        return CallRecord(
            message_id=msg["id"],
            conversation=conversation,
            alt_id=msg.get("altId", ""),
            message_type=msg.get("messageType", "TYPE_CALL"),
            direction=msg.get("direction", ""),
            status=msg.get("meta", {}).get("status") if msg.get("meta", {}).get("status", "") else msg.get("status", ""),
            type=msg.get("type", 0),
            duration=duration,
            call_meta=msg.get("meta", {}),
            location_id=msg.get("locationId", location_id),
            contact_id=msg.get("contactId", ""),
            user_id=msg.get("userId", ""),
            date_added=to_local_dt(msg.get("dateAdded")),
        )

    all_calls = []
    last_message_id = None
    page = 0

    while True:
        page += 1
        params = {"lastMessageId": last_message_id} if last_message_id else {}
        params["limit"] = 100

        print(f"Fetching call records page {page} for conversation {conversation_id}")
        res = requests.get(base_url, headers=headers, params=params)

        if res.status_code != 200:
            print(f"Failed to fetch calls: {res.text}")
            break

        data = res.json().get("messages", {})
        messages = data.get("messages", [])
        if not messages:
            break

        all_calls += [build_call_obj(msg) for msg in messages]
        last_message_id = messages[-1]["id"]

        # if not data.get("nextPage") or page > 100:
        #     break

    # Save to DB
    if not all_calls:
        print(f"No call records found for conversation {conversation_id}")
        return 0

    try:
        with transaction.atomic():
            existing_ids = set(
                CallRecord.objects.filter(
                    message_id__in=[c.message_id for c in all_calls]
                ).values_list("message_id", flat=True)
            )

            to_create = [c for c in all_calls if c.message_id not in existing_ids]
            to_update_map = {c.message_id: c for c in all_calls if c.message_id in existing_ids}

            if to_create:
                CallRecord.objects.bulk_create(to_create, ignore_conflicts=True)
                print(f"Created {len(to_create)} new call records")

            if to_update_map:
                existing = CallRecord.objects.filter(message_id__in=to_update_map.keys())
                updated_count = 0
                for call in existing:
                    new_data = to_update_map[call.message_id]
                    if call.status != new_data.status or call.duration != new_data.duration:
                        call.status = new_data.status
                        call.duration = new_data.duration
                        call.call_meta = new_data.call_meta
                        updated_count += 1
                
                if updated_count > 0:
                    CallRecord.objects.bulk_update(existing, ['status', 'duration', 'call_meta'])
                    print(f"Updated {updated_count} existing call records")

        print(f"Synced {len(all_calls)} call records ({len(to_create)} new, {len(to_update_map)} existing)")
    except Exception as e:
        print(f"Error during call records DB sync: {e}")
        return 0

    return len(all_calls)


def save_conversations_with_calls(location_id):

    token = GHLAuthCredentials.objects.get(location_id=location_id)
    access_token=token.access_token
    """
    Main function to sync call records for all conversations.
    """
    all_conversations = GHLConversation.objects.filter(location__location_id=location_id)
    
    print("\n" + "="*50)
    print("STARTING CALL RECORDS SYNC FOR ALL CONVERSATIONS")
    print("="*50)
    
    # Get all conversation IDs that were just processed
    conversation_ids = [conv.conversation_id for conv in all_conversations]
    total_calls_synced = 0
    
    for i, conv_id in enumerate(conversation_ids, 1):
        print(f"\nSyncing call records for conversation {i}/{len(conversation_ids)}: {conv_id}")
        calls_count = sync_conversation_calls(conv_id, location_id, access_token)
        
        total_calls_synced += calls_count
        
        # Optional: Add a small delay to avoid rate limiting
        import time
        time.sleep(0.1)  # 100ms delay between requests
    
    print(f"\n" + "="*50)
    print(f"CALL RECORDS SYNC COMPLETED")
    print(f"Total conversations processed: {len(all_conversations)}")
    print(f"Total call records synced: {total_calls_synced}")
    print("="*50)
    
    return total_calls_synced



def save_conversations_with_messages_and_calls(location_id):

    token = GHLAuthCredentials.objects.get(location_id=location_id)
    access_token=token.access_token
    """
    Combined function to sync both text messages and call records.
    """
    all_conversations = GHLConversation.objects.filter(location__location_id=location_id)
    
    print("\n" + "="*60)
    print("STARTING COMBINED SYNC FOR ALL CONVERSATIONS")
    print("="*60)
    
    conversation_ids = [conv.conversation_id for conv in all_conversations]
    total_messages_synced = 0
    total_calls_synced = 0
    
    for i, conv_id in enumerate(conversation_ids, 1):
        print(f"\nProcessing conversation {i}/{len(conversation_ids)}: {conv_id}")
        
        # Sync text messages
        print(f"  → Syncing text messages...")
        messages_count = sync_conversation_text_messages(conv_id, location_id, access_token)
        total_messages_synced += messages_count
        
        # Small delay between different API calls
        import time
        time.sleep(0.1)
        
        # Sync call records
        print(f"  → Syncing call records...")
        calls_count = sync_conversation_calls(conv_id, location_id, access_token)
        total_calls_synced += calls_count
        
        print(f"  → Conversation summary: {messages_count} messages, {calls_count} calls")
        
        # Delay between conversations
        time.sleep(0.1)
    
    print(f"\n" + "="*60)
    print(f"COMBINED SYNC COMPLETED")
    print(f"Total conversations processed: {len(all_conversations)}")
    print(f"Total text messages synced: {total_messages_synced}")
    print(f"Total call records synced: {total_calls_synced}")
    print("="*60)
    
    return {
        'conversations': len(all_conversations),
        'messages': total_messages_synced,
        'calls': total_calls_synced
    }