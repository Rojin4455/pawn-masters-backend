import requests
from decouple import config
from core.serializers import FirebaseTokenSerializer, LeadConnectorAuthSerializer, IdentityToolkitAuthSerializer
from core.models import FirebaseToken, LeadConnectorAuth, IdentityToolkitAuth, GHLAuthCredentials, CallReport, GHLTransaction
# from accounts.helpers import get_pipeline_stages, create_or_update_contact # Assuming these are still needed
import pytz
import datetime
from django.utils.dateparse import parse_datetime
from django.db import transaction
from accounts_management_app.models import GHLConversation, GHLWalletBalance

# Constants for the API keys (consider moving to settings or more secure management)
FIREBASE_TOKEN_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"
IDENTITY_TOOLKIT_API_KEY = "AIzaSyB_w3vXmsI7WeQtrIOkjR6xTRVN5uOieiE"

def token_generation_step1(ghl_credential: GHLAuthCredentials):
    """
    Generates the Firebase token using the initial refresh token for a specific GHL credential.
    """
    print(f"token generation step 1 triggered for location: {ghl_credential.location_name}")
    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_TOKEN_API_KEY}"

    headers = {
        "authority": "securetoken.googleapis.com",
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "access-control-request-headers": "x-client-version,x-firebase-client,x-firebase-gmpid",
        "access-control-request-method": "POST",
        "origin": "https://app.gohighlevel.com",
        "referer": "https://app.gohighlevel.com/",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    # Use the ghl_initial_refresh_token stored in GHLAuthCredentials
    data = {
       "refresh_token": ghl_credential.ghl_initial_refresh_token,
        "grant_type": "refresh_token"
    }

    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        response_data = response.json()
        user_id = response_data.get("user_id")
        project_id = response_data.get("project_id")

        # Associate the FirebaseToken with the current GHLAuthCredentials instance
        token_instance = FirebaseToken.objects.filter(ghl_credential=ghl_credential).first()
        print("token instance: ", token_instance)
        if token_instance:
            serializer = FirebaseTokenSerializer(token_instance, data=response_data, partial=True)
        else:
            serializer = FirebaseTokenSerializer(data=response_data)

        if serializer.is_valid():
            # Set the ghl_credential before saving for new instances
            if not token_instance:
                serializer.validated_data['ghl_credential'] = ghl_credential
            serializer.save()
            print("Data saved/updated successfully!")
            return fetch_and_store_leadconnector_token(ghl_credential)
        else:
            print("Validation errors:", serializer.errors)
            return False # Indicate failure
    else:
        print(f"API call failed for step 1: {response.status_code} - {response.text}")
        return False # Indicate failure


def fetch_and_store_leadconnector_token(ghl_credential: GHLAuthCredentials):
    """
    Fetches and stores the LeadConnector token for a specific GHL credential.
    """
    firebase_token = FirebaseToken.objects.filter(ghl_credential=ghl_credential).first()
    if not firebase_token:
        print(f"Firebase token not found for location: {ghl_credential.location_name}. Cannot proceed to Step 2.")
        return False

    url = f"https://services.leadconnectorhq.com/oauth/2/login/signin/refresh?version=2&location_id={ghl_credential.location_id}"

    headers = {
        "authority": "services.leadconnectorhq.com",
        "accept": "application/json, text/plain, */*",
        "accept-language": "en-IN,en-US;q=0.9,en;q=0.8,ml;q=0.7",
        "authorization": f"Bearer {firebase_token.access_token}",
        "baggage": "sentry-environment=production,sentry-release=51f978e816451676419adc7a1f15a689366afae4,sentry-public_key=c67431ff70d6440fb529c2705792425f,sentry-trace_id=4bbe54b1784442168fd300b0dec887e0",
        "channel": "APP",
        "content-type": "application/json;charset=UTF-8",
        "origin": "https://app.franchiseexpert.com", # Consider making this dynamic if needed
        "referer": "https://app.franchiseexpert.com/", # Consider making this dynamic if needed
        "sec-ch-ua": '"Google Chrome";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "sentry-trace": "4bbe54b1784442168fd300b0dec887e0-94e9b3f71325b51e",
        "source": "WEB_USER",
        "token-id": firebase_token.access_token,
        "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "version": "2021-07-28",
    }

    response = requests.post(url, headers=headers, json={})

    if response.status_code == 200:
        response_data = response.json()
        response_data["trace_id"] = response_data.pop("traceId", None) # Correcting key name

        print("responseData: ", response_data)
        # Delete existing LeadConnectorAuth for this GHL credential before creating new
        LeadConnectorAuth.objects.filter(ghl_credential=ghl_credential).delete()

        serializer = LeadConnectorAuthSerializer(data=response_data)

        if serializer.is_valid():
            serializer.validated_data['ghl_credential'] = ghl_credential
            serializer.save()
            print("Data saved/updated successfully!")
            return fetch_and_store_final_token(ghl_credential)
        else:
            print("Validation errors:", serializer.errors)
            return False
    elif response.status_code == 401:
        print(f"LeadConnector token refresh failed (401) for {ghl_credential.location_name}. Retrying step 1.")
        return token_generation_step1(ghl_credential) # Retry step 1
    else:
        print(f"API call failed with status code {response.status_code}: {response.text}")
        return False


def fetch_and_store_final_token(ghl_credential: GHLAuthCredentials):
    """
    Fetches and stores the final IdentityToolkit token for a specific GHL credential.
    """
    lead_connector_auth = LeadConnectorAuth.objects.filter(ghl_credential=ghl_credential).first()
    if not lead_connector_auth:
        print(f"LeadConnector Auth token not found for location: {ghl_credential.location_name}. Cannot proceed to Step 3.")
        return False

    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken?key={IDENTITY_TOOLKIT_API_KEY}"

    # Headers
    headers = {
        "authority": "identitytoolkit.googleapis.com",
        "accept": "*/*",
        "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        "content-type": "application/json",
        "origin": "https://app.gohighlevel.com",
        "sec-ch-ua": '"Wavebox";v="119", "Chromium";v="119", "Not?A_Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        "x-client-data": "CMeCywE=",
        "x-client-version": "Chrome/JsCore/9.15.0/FirebaseCore-web",
        "x-firebase-gmpid": "1:439472444885:android:c48022009a58ffc7",
    }

    data = {
        "token": lead_connector_auth.token,
        "returnSecureToken": True
    }

    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        response_data = response.json()

        serializer_data = {
            "kind": response_data.get("kind"),
            "id_token": response_data.get("idToken"),
            "refresh_token": response_data.get("refreshToken"),
            "expires_in": int(response_data.get("expiresIn", 0)),
            "is_new_user": response_data.get("isNewUser", False),
        }

        # Delete existing IdentityToolkitAuth for this GHL credential before creating new
        IdentityToolkitAuth.objects.filter(ghl_credential=ghl_credential).delete()

        serializer = IdentityToolkitAuthSerializer(data=serializer_data)
        if serializer.is_valid():
            serializer.validated_data['ghl_credential'] = ghl_credential
            serializer.save()
            print(f"✅ Data saved successfully for {ghl_credential.location_name}!")
            return True
        else:
            print(f"❌ Serializer errors for {ghl_credential.location_name}:", serializer.errors)
            return False
    elif response.status_code == 401:
        print(f"IdentityToolkit token refresh failed (401) for {ghl_credential.location_name}. Retrying step 1.")
        return token_generation_step1(ghl_credential) # Retry step 1
    else:
        print(f"❌ API request failed with status code {response.status_code}: {response.text}")
        return False


def get_ghl_auth_token(ghl_credential: GHLAuthCredentials):
    """
    Retrieves the current IdentityToolkitAuth token for a GHL credential.
    If the token is expired or not found, it triggers the regeneration process.
    Returns the id_token if successful, else None.
    """
    identity_token = IdentityToolkitAuth.objects.filter(ghl_credential=ghl_credential).first()

    if not identity_token:
        print(f"No existing token found for {ghl_credential.location_name}. Generating new tokens.")
        success = token_generation_step1(ghl_credential)
        if not success:
            return None
        identity_token = IdentityToolkitAuth.objects.filter(ghl_credential=ghl_credential).first()
        if not identity_token: # Check again after generation attempt
            print(f"Failed to generate token for {ghl_credential.location_name}.")
            return None

    # Check for token expiry (consider a buffer, e.g., 5 minutes before actual expiry)
    # The 'expires_in' is usually in seconds
    import datetime
    current_time = datetime.datetime.now(pytz.utc)
    token_expiry_time = identity_token.created_at + datetime.timedelta(seconds=identity_token.expires_in)

    # Adding a buffer of 5 minutes to trigger refresh earlier
    if current_time >= token_expiry_time - datetime.timedelta(minutes=5):
        print(f"Token for {ghl_credential.location_name} is expired or nearing expiry. Regenerating tokens.")
        success = token_generation_step1(ghl_credential)
        if not success:
            return None
        identity_token = IdentityToolkitAuth.objects.filter(ghl_credential=ghl_credential).first()
        if not identity_token: # Check again after generation attempt
            print(f"Failed to generate token for {ghl_credential.location_name} after expiry.")
            return None

    return identity_token.id_token


def fetch_calls_for_last_days_for_location(ghl_credential: GHLAuthCredentials, days_ago_start=30, days_ago_end=0, days_to_fetch=3):
    """
    Fetch call reports for a specific location.
    """
    print(f"Attempting to fetch calls for {ghl_credential.location_name} (ID: {ghl_credential.location_id})")

    token_id = get_ghl_auth_token(ghl_credential)
    if not token_id:
        print(f"Failed to get a valid authentication token for {ghl_credential.location_name}. Skipping call fetch.")
        return

    import datetime
    def generate_date_range(days_ago_start_val, days_ago_end_val):
        today = datetime.datetime.now()
        end_date = (today - datetime.timedelta(days=days_ago_end_val)).replace(hour=18, minute=29, second=59, microsecond=999000)
        start_date = (today - datetime.timedelta(days=days_ago_start_val)).replace(hour=18, minute=30, second=0, microsecond=0)
        formatted_end_date = end_date.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        formatted_start_date = start_date.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
        return formatted_start_date, formatted_end_date

    # Iterate through periods (e.g., last 3 days)
    for i in range(days_to_fetch):
        # Adjust range as needed (e.g., 0-2 for today, yesterday, day before yesterday)
        days_back_end = i
        days_back_start = i + 2 # Start date is always 2 days before end date

        start_date, end_date = generate_date_range(days_back_start, days_back_end)
        print(f"Fetching data for period {i+1} for {ghl_credential.location_name}:")
        print(f"Start Date: {start_date}")
        print(f"End Date: {end_date}")

        payload = {
            "callStatus": [],
            "campaign": [],
            "deviceType": [],
            "direction": None,
            "duration": None,
            "endDate": end_date,
            "firstTime": False,
            "keyword": [],
            "landingPage": [],
            "limit": 50,
            "locationId": ghl_credential.location_id, # Use the location_id from the GHLAuthCredentials instance
            "qualifiedLead": False,
            "referrer": [],
            "selectedPool": "all",
            "skip": 0,
            "source": [],
            "sourceType": [],
            "startDate": start_date,
            "userId": "" # This might also be dynamic based on GHLAuthCredentials if needed
        }

        headers = {
            "Token-id": token_id, # Use the retrieved token_id
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Source": "WEB_USER",
            "Channel": "APP",
            "Version": "2021-04-15"
        }

        all_calls = []
        BASE_URL = "https://backend.leadconnectorhq.com/reporting/calls/get-all-phone-calls-new"

        while True:
            response = requests.post(BASE_URL, json=payload, headers=headers)

            if response.status_code == 401:
                print(f"Token expired/invalid for {ghl_credential.location_name} during call fetch. Regenerating and retrying this specific fetch period.")
                token_id = get_ghl_auth_token(ghl_credential) # Attempt to refresh token
                if not token_id:
                    print(f"Failed to refresh token for {ghl_credential.location_name}. Skipping current fetch period.")
                    break # Skip this fetch period and move to the next location or stop
                # Update headers with new token and retry the current payload
                headers["Token-id"] = token_id
                continue # Retry the current request with the new token

            if response.status_code != 201:
                print(f"Error fetching calls for {ghl_credential.location_name}: {response.status_code}, {response.text}")
                break

            data = response.json()
            # print("data: ", data) # Keep this commented unless debugging large outputs
            calls = data.get("rows", [])

            if not calls:
                break

            all_calls.extend(calls)
            payload["skip"] += payload["limit"]

        update_or_store_calls(all_calls, ghl_credential)


def update_or_store_calls(calls, ghl_credential: GHLAuthCredentials):
    """
    Updates or stores call reports, associating them with the specific GHL credential.
    """
    if not calls:
        print(f"No calls to process for {ghl_credential.location_name}.")
        return

    # Filter for existing calls only for the current location and given IDs
    existing_call_ids = set(CallReport.objects.filter(
        ghl_credential=ghl_credential,
        id__in=[call.get("id") for call in calls]
    ).values_list("id", flat=True))

    new_call_objects = []
    update_call_objects = []

    for call in calls:
        
        # Ensure 'id' exists before processing
        call_id = call.get("id")
        if not call_id:
            print(f"Skipping call record with no ID: {call}")
            continue
        conversation = None
        try:
            conversation = GHLConversation.objects.get(contact_id = call.get("contactId"))
        except:
            pass
        
        call_obj = CallReport(
            id=call_id,
            ghl_credential=ghl_credential, # Link to the GHLAuthCredentials instance
            account_sid=call.get("accountSid"),
            assigned_to=call.get("assignedTo"),
            call_sid=call.get("callSid"),
            call_status=call.get("callStatus"),
            # Removed: called, called_city, called_country, called_state, called_zip
            # Removed: caller, caller_city, caller_country, caller_state, caller_zip
            contact_id=call.get("contactId"),
            date_added=parse_datetime(call.get("dateAdded")) if call.get("dateAdded") else None,
            date_updated=parse_datetime(call.get("dateUpdated")) if call.get("dateUpdated") else None,
            deleted=call.get("deleted", False),
            direction=call.get("direction"),
            from_number=call.get("from"),
            # Removed: from_city, from_country, from_state, from_zip
            location_id=call.get("locationId"), # Still keep this for redundancy/cross-referencing if useful
            message_id=call.get("messageId"),
            to_number=call.get("to"),
            # Removed: to_city, to_country, to_state, to_zip
            user_id=call.get("userId"),
            updated_at=parse_datetime(call.get("updatedAt")) if call.get("updatedAt") else None,
            duration=call.get("duration", 0),
            first_time=call.get("firstTime", False),
            recording_url=call.get("recordingUrl"),
            conversation=conversation
            # Removed: created_at (as it's auto_now_add=True)
        )

        if call_id in existing_call_ids:
            update_call_objects.append(call_obj)
        else:
            new_call_objects.append(call_obj)

    with transaction.atomic():
        if new_call_objects:
            CallReport.objects.bulk_create(new_call_objects, ignore_conflicts=True)
            print(f"Inserted {len(new_call_objects)} new call records for {ghl_credential.location_name}.")

        if update_call_objects:
            # We need to specify the fields that are allowed to be updated.
            # Make sure 'ghl_credential' is NOT in this list as it's a FK and shouldn't change
            # once set for a CallReport (unless you have a very specific use case).
            CallReport.objects.bulk_update(update_call_objects, [
                "account_sid", "assigned_to", "call_sid", "call_status",
                "contact_id", "date_added",
                "date_updated", "deleted", "direction", "from_number",
                "location_id", "message_id", "to_number",
                "user_id", "updated_at", "duration",
                "first_time", "recording_url", "conversation"
            ])
            print(f"Updated {len(update_call_objects)} existing call records for {ghl_credential.location_name}.")

# Main function to trigger the process for all locations
def process_all_ghl_locations_for_calls():
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
        fetch_calls_for_last_days_for_location(credential)
        print(f"--- Finished processing for {credential.location_name} ---\n")




import json


class DummyGHLAuthCredentials:
    def __init__(self, location_id, location_name="Dummy Location"):
        self.location_id = location_id
        self.location_name = location_name

# --- Your function to make the API call ---
def fetch_location_wallet_data(ghl_credential):
    """
    Fetches location wallet data from the LeadConnector HQ API.

    Args:
        ghl_credential (GHLAuthCredentials): An instance of GHLAuthCredentials
                                             containing the location_id.

    Returns:
        dict or None: Parsed JSON response if successful, otherwise None.
    """
    base_url = "https://services.leadconnectorhq.com"
    endpoint = f"/saas_wallet_service/location-wallet/{ghl_credential.location_id}"
    request_url = f"{base_url}{endpoint}"

    # Fetch the token using your existing function
    token_id = get_ghl_auth_token(ghl_credential)
    if not token_id:
        print(f"Failed to get a valid authentication token for {ghl_credential.location_name}. Skipping wallet fetch.")
        return None

    # Define the headers based on your network tab capture
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Source": "WEB_USER",
        "Token-Id": token_id, # This is the crucial part using your function's output
        "Version": "2021-07-28" # This 'Version' header might be specific to GHL's internal API versioning
    }

    try:
        print(f"Making GET request to: {request_url}")
        response = requests.get(request_url, headers=headers)
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

        data = response.json()
        print("Successfully fetched location wallet data.")
        # print(json.dumps(data, indent=2)) # Pretty print the response if needed
        return data

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err} - {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An unexpected request error occurred: {req_err}")
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from response: {response.text}")
    return None


def sync_wallet_balance(location_id=None, company_id=None):
    """
    Fetches wallet data and syncs it to the GHLWalletBalance model.
    Returns a dictionary with sync results for the API response.
    """
    sync_results = {
        "status": "success",
        "message": "Wallet sync completed.",
        "details": []
    }
    processed_count = 0
    updated_count = 0
    created_count = 0
    failed_count = 0

    try:
        if location_id:
            ghl_credentials = [GHLAuthCredentials.objects.get(location_id=location_id)]
            if not ghl_credentials: # Check if list is empty after .get()
                 raise GHLAuthCredentials.DoesNotExist
        
        else:
            if company_id:
                ghl_credentials = GHLAuthCredentials.objects.filter(company_id=company_id)
            else:
                ghl_credentials = GHLAuthCredentials.objects.all()

        if not ghl_credentials:
            sync_results["status"] = "info"
            sync_results["message"] = "No GHL credentials found to sync."
            return sync_results

    except GHLAuthCredentials.DoesNotExist:
        sync_results["status"] = "error"
        sync_results["message"] = f"Error: GHLAuthCredentials with location_id '{location_id}' not found. Cannot sync wallet."
        return sync_results
    except Exception as e:
        sync_results["status"] = "error"
        sync_results["message"] = f"An unexpected error occurred while fetching credentials: {e}"
        return sync_results

    for ghl_credential in ghl_credentials:
        detail = {
            "location_id": ghl_credential.location_id,
            "location_name": ghl_credential.location_name, # Assuming location_name on credential
            "status": "pending"
        }
        try:
            wallet_data = fetch_location_wallet_data(ghl_credential)

            if wallet_data:
                with transaction.atomic():
                    wallet_balance_obj, created = GHLWalletBalance.objects.get_or_create(
                        ghl_credential=ghl_credential,
                        defaults={
                            'current_balance': wallet_data.get("currentBalance")
                        }
                    )

                    if not created:
                        wallet_balance_obj.current_balance = wallet_data.get("currentBalance")
                        wallet_balance_obj.save()
                        detail["status"] = "updated"
                        updated_count += 1
                        print(f"Updated wallet balance for {ghl_credential.location_name}.")
                    else:
                        detail["status"] = "created"
                        created_count += 1
                        print(f"Created new wallet balance record for {ghl_credential.location_name}.")

                detail["message"] = "Successfully synced."
                detail["current_balance"] = wallet_data.get("currentBalance")
                processed_count += 1
            else:
                detail["status"] = "failed_api_fetch"
                detail["message"] = "Failed to fetch data from GHL API."
                failed_count += 1
        except Exception as e:
            detail["status"] = "failed_db_save"
            detail["message"] = f"Error during sync: {e}"
            failed_count += 1
            print(f"Error syncing wallet for {ghl_credential.location_name}: {e}")

        sync_results["details"].append(detail)

    sync_results["processed_locations"] = processed_count
    sync_results["created_records"] = created_count
    sync_results["updated_records"] = updated_count
    sync_results["failed_locations"] = failed_count
    return sync_results





from django.db.models import Count, Q, Sum, F,DecimalField
from django.utils import timezone
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.db.models.functions import Coalesce
from datetime import datetime, timedelta
from core.models import CallReport
from accounts_management_app.models import TextMessage
from .models import AnalyticsCache
import logging
from decimal import Decimal
from core.models import GHLTransaction, GHLAuthCredentials

logger = logging.getLogger(__name__)

class AnalyticsComputer:
    """Utility class to compute analytics data using GHLTransaction model"""
    
    @staticmethod
    def serialize_datetime_data(data):
        """Convert datetime objects to ISO format strings for JSON serialization"""
        if isinstance(data, dict):
            return {k: AnalyticsComputer.serialize_datetime_data(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [AnalyticsComputer.serialize_datetime_data(item) for item in data]
        elif isinstance(data, datetime):
            return data.isoformat()
        elif hasattr(data, 'isoformat'):  # Handle date objects
            return data.isoformat()
        elif isinstance(data, Decimal):
            return float(data)
        else:
            return data
    
    @staticmethod
    def get_usage_summary_data():
        """Compute usage summary data from GHLTransaction model"""
        try:
            # Get SMS statistics from transactions
            sms_stats = GHLTransaction.objects.filter(
                transaction_type__in=['sms_inbound', 'sms_outbound']
            ).aggregate(
                total_messages=Coalesce(Count('transaction_id'), 0),
                total_inbound_messages=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_inbound')), 0),
                total_outbound_messages=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_outbound')), 0),
                total_sms_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type__in=['sms_inbound', 'sms_outbound']), output_field=DecimalField()), Decimal('0')),
                total_inbound_sms_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_inbound'), output_field=DecimalField()), Decimal('0')),
                total_outbound_sms_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_outbound'), output_field=DecimalField()), Decimal('0')),
            )

            # Get Call statistics from transactions
            call_stats = GHLTransaction.objects.filter(
                transaction_type__in=['call_inbound', 'call_outbound']
            ).aggregate(
                total_calls=Coalesce(Count('transaction_id'), 0),
                total_call_duration=Coalesce(Sum('duration'), 0),
                total_inbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_inbound')), 0),
                total_outbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_outbound')), 0),
                total_inbound_call_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_inbound')), 0),
                total_outbound_call_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_outbound')), 0),
                total_call_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type__in=['call_inbound', 'call_outbound']), output_field=DecimalField()), Decimal('0')),
                total_inbound_call_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_inbound'), output_field=DecimalField()), Decimal('0')),
                total_outbound_call_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_outbound'), output_field=DecimalField()), Decimal('0')),
            )
            
            result = {
                'sms_summary': sms_stats,
                'call_summary': call_stats,
                'total_records': sms_stats['total_messages'] + call_stats['total_calls'],
                'generated_at': timezone.now().isoformat()
            }
            
            return AnalyticsComputer.serialize_datetime_data(result)
            
        except Exception as e:
            logger.error(f"Error computing usage summary: {str(e)}")
            raise
    
    @staticmethod
    def get_usage_analytics_data(start_date=None, end_date=None, category_id=None, company_id=None, search=None):
        """Compute account-level usage analytics data using GHLTransaction model"""
        try:
            # Get all approved locations with their rates
            location_queryset = GHLAuthCredentials.objects.filter(is_approved=True)
            
            if category_id:
                location_queryset = location_queryset.filter(category_id=category_id)
            if company_id:
                location_queryset = location_queryset.filter(company_id=company_id)
            if search:
                location_queryset = location_queryset.filter(
                    Q(location_name__icontains=search) |
                    Q(location_id__icontains=search) |
                    Q(company_name__icontains=search)
                )
            
            # Get location data with rates
            location_data = {
                loc['location_id']: loc for loc in location_queryset.values(
                    'location_id', 'location_name', 'company_name', 
                    'inbound_rate', 'outbound_rate',
                    'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio'
                )
            }
            
            if not location_data:
                return []

            location_ids = list(location_data.keys())
            
            # Build transaction filters
            transaction_filters = Q(
                ghl_credential__location_id__in=location_ids,
                ghl_credential__is_approved=True,
                transaction_type__in=['sms_inbound', 'sms_outbound', 'call_inbound', 'call_outbound']
            )
            
            if start_date and end_date:
                transaction_filters &= Q(created_at__gte=start_date, created_at__lte=end_date)
            
            # Get SMS and Call statistics by location
            transaction_stats = GHLTransaction.objects.filter(transaction_filters).values(
                'ghl_credential__location_id'
            ).annotate(
                total_inbound_messages=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_inbound')), 0),
                total_outbound_messages=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_outbound')), 0),
                sms_inbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_inbound'), output_field=DecimalField()), Decimal('0')),
                sms_outbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_outbound'), output_field=DecimalField()), Decimal('0')),
                
                total_inbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_inbound')), 0),
                total_outbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_outbound')), 0),
                total_inbound_call_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_inbound')), 0),
                total_outbound_call_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_outbound')), 0),
                call_inbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_inbound'), output_field=DecimalField()), Decimal('0')),
                call_outbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_outbound'), output_field=DecimalField()), Decimal('0')),
            )
            
            # Convert to dictionary for O(1) lookup
            stats_dict = {stat['ghl_credential__location_id']: stat for stat in transaction_stats}
            
            # Build results
            results = []
            for location_id, location_info in location_data.items():
                stats = stats_dict.get(location_id, {
                    'total_inbound_messages': 0, 'total_outbound_messages': 0,
                    'sms_inbound_usage': 0, 'sms_outbound_usage': 0,
                    'total_inbound_calls': 0, 'total_outbound_calls': 0,
                    'total_inbound_call_duration': 0, 'total_outbound_call_duration': 0,
                    'call_inbound_usage': 0, 'call_outbound_usage': 0
                })
                
                # Calculate totals
                total_sms_usage = Decimal(str(stats['sms_inbound_usage'])) + Decimal(str(stats['sms_outbound_usage']))
                total_call_usage = Decimal(str(stats['call_inbound_usage'])) + Decimal(str(stats['call_outbound_usage']))
                total_usage = total_sms_usage + total_call_usage
                
                # Convert call duration to minutes
                inbound_call_minutes = Decimal(str(stats['total_inbound_call_duration'])) / Decimal('60')
                outbound_call_minutes = Decimal(str(stats['total_outbound_call_duration'])) / Decimal('60')
                
                results.append({
                    'company_name': location_info.get('company_name'),
                    'location_name': location_info.get('location_name'),
                    'location_id': location_id,
                    'total_inbound_messages': stats['total_inbound_messages'],
                    'total_outbound_messages': stats['total_outbound_messages'],
                    'sms_inbound_usage': float(stats['sms_inbound_usage']),
                    'sms_outbound_usage': float(stats['sms_outbound_usage']),
                    'total_sms_usage': float(total_sms_usage),
                    'total_inbound_calls': stats['total_inbound_calls'],
                    'total_outbound_calls': stats['total_outbound_calls'],
                    'total_inbound_call_duration': stats['total_inbound_call_duration'],
                    'total_outbound_call_duration': stats['total_outbound_call_duration'],
                    'inbound_call_minutes': float(inbound_call_minutes),
                    'outbound_call_minutes': float(outbound_call_minutes),
                    'call_inbound_usage': float(stats['call_inbound_usage']),
                    'call_outbound_usage': float(stats['call_outbound_usage']),
                    'total_call_usage': float(total_call_usage),
                    'total_inbound_usage': float(stats['sms_inbound_usage']) + float(stats['call_inbound_usage']),
                    'total_outbound_usage': float(stats['sms_outbound_usage']) + float(stats['call_outbound_usage']),
                    'total_usage': float(total_usage),
                })
            
            # Sort by company_name, location_name
            results.sort(key=lambda x: (x['company_name'] or '', x['location_name'] or ''))
            
            return AnalyticsComputer.serialize_datetime_data(results)
            
        except Exception as e:
            logger.error(f"Error computing usage analytics: {str(e)}")
            raise

    @staticmethod
    def get_company_usage_analytics_data(start_date=None, end_date=None, category_id=None, company_id=None):
        """Compute company-level usage analytics data using GHLTransaction model"""
        try:
            company_filter = Q(is_approved=True)
            if category_id:
                company_filter &= Q(category_id=category_id)
            if company_id:
                company_filter &= Q(company_id=company_id)
            
            company_data = {}
            location_rates = GHLAuthCredentials.objects.filter(company_filter).values(
                'company_id', 'company_name', 'location_id'
            )
            
            for item in location_rates:
                company_id = item['company_id']
                if company_id not in company_data:
                    company_data[company_id] = {
                        'company_name': item['company_name'],
                        'locations': [],
                        'location_count': 0
                    }
                company_data[company_id]['locations'].append(item['location_id'])
                company_data[company_id]['location_count'] += 1
            
            if not company_data:
                return []
            
            all_location_ids = []
            for company_info in company_data.values():
                all_location_ids.extend(company_info['locations'])
            
            transaction_filters = Q(
                ghl_credential__location_id__in=all_location_ids,
                ghl_credential__is_approved=True,
                transaction_type__in=['sms_inbound', 'sms_outbound', 'call_inbound', 'call_outbound']
            )
            
            if start_date and end_date:
                transaction_filters &= Q(created_at__gte=start_date, created_at__lte=end_date)
            
            transaction_stats = GHLTransaction.objects.filter(transaction_filters).values(
                'ghl_credential__company_id'
            ).annotate(
                total_inbound_messages=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_inbound')), 0),
                total_outbound_messages=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_outbound')), 0),
                total_inbound_segments=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_inbound')), 0),
                total_outbound_segments=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_outbound')), 0),
                sms_inbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_inbound'), output_field=DecimalField()), Decimal('0')),
                sms_outbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_outbound'), output_field=DecimalField()), Decimal('0')),
                
                total_inbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_inbound')), 0),
                total_outbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_outbound')), 0),
                total_inbound_call_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_inbound')), 0),
                total_outbound_call_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_outbound')), 0),
                call_inbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_inbound'), output_field=DecimalField()), Decimal('0')),
                call_outbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_outbound'), output_field=DecimalField()), Decimal('0')),
            )
            
            stats_dict = {stat['ghl_credential__company_id']: stat for stat in transaction_stats}
            
            results = []
            for company_id, company_info in company_data.items():
                stats = stats_dict.get(company_id, {
                    'total_inbound_messages': 0, 'total_outbound_messages': 0,
                    'total_inbound_segments': 0, 'total_outbound_segments': 0,
                    'sms_inbound_usage': 0, 'sms_outbound_usage': 0,
                    'total_inbound_calls': 0, 'total_outbound_calls': 0,
                    'total_inbound_call_duration': 0, 'total_outbound_call_duration': 0,
                    'call_inbound_usage': 0, 'call_outbound_usage': 0
                })
                
                total_sms_usage = Decimal(str(stats['sms_inbound_usage'])) + Decimal(str(stats['sms_outbound_usage']))
                total_call_usage = Decimal(str(stats['call_inbound_usage'])) + Decimal(str(stats['call_outbound_usage']))
                total_usage = total_sms_usage + total_call_usage
                
                inbound_call_minutes = Decimal(str(stats['total_inbound_call_duration'])) / Decimal('60')
                outbound_call_minutes = Decimal(str(stats['total_outbound_call_duration'])) / Decimal('60')
                
                results.append({
                    'company_name': company_info['company_name'],
                    'company_id': company_id,
                    'total_inbound_messages': stats['total_inbound_messages'],
                    'total_outbound_messages': stats['total_outbound_messages'],
                    'total_inbound_segments': stats['total_inbound_segments'],
                    'total_outbound_segments': stats['total_outbound_segments'],
                    'sms_inbound_usage': float(stats['sms_inbound_usage']),
                    'sms_outbound_usage': float(stats['sms_outbound_usage']),
                    'total_inbound_calls': stats['total_inbound_calls'],
                    'total_outbound_calls': stats['total_outbound_calls'],
                    'total_inbound_call_duration': stats['total_inbound_call_duration'],
                    'total_outbound_call_duration': stats['total_outbound_call_duration'],
                    'total_inbound_call_minutes': float(inbound_call_minutes),
                    'total_outbound_call_minutes': float(outbound_call_minutes),
                    'call_inbound_usage': float(stats['call_inbound_usage']),
                    'call_outbound_usage': float(stats['call_outbound_usage']),
                    'total_inbound_usage': float(stats['sms_inbound_usage']) + float(stats['call_inbound_usage']),
                    'total_outbound_usage': float(stats['sms_outbound_usage']) + float(stats['call_outbound_usage']),
                    'total_usage': float(total_usage),
                    'locations_count': company_info['location_count'],
                })
            
            results.sort(key=lambda x: x['company_name'] or '')
            
            return AnalyticsComputer.serialize_datetime_data(results)
            
        except Exception as e:
            logger.error(f"Error computing company usage analytics: {str(e)}")
            raise
    
    @staticmethod
    def get_bar_graph_analytics_data(start_date=None, end_date=None, graph_type='daily', 
                                   data_type='both', view_type='account', location_ids=None, company_ids=None, category_id=None):
        """Compute bar graph analytics data using GHLTransaction model"""
        try:
            if not end_date:
                end_date = timezone.now().date()
            if not start_date:
                start_date = end_date - timedelta(days=30)
            
            if graph_type == 'daily':
                trunc_func = TruncDay
            elif graph_type == 'weekly':
                trunc_func = TruncWeek
            else:  # monthly
                trunc_func = TruncMonth
            
            base_filters = Q(
                ghl_credential__is_approved=True,
                created_at__gte=start_date,
                created_at__lte=end_date,
                transaction_type__in=['sms_inbound', 'sms_outbound', 'call_inbound', 'call_outbound']
            )
            
            if category_id:
                base_filters &= Q(ghl_credential__category_id=category_id)
            
            if view_type == 'account' and location_ids:
                base_filters &= Q(ghl_credential__location_id__in=location_ids)
            elif view_type == 'company' and company_ids:
                base_filters &= Q(ghl_credential__company_id__in=company_ids)
            
            result_data = {}
            
            if data_type in ['sms', 'both']:
                sms_data = GHLTransaction.objects.filter(
                    base_filters & Q(transaction_type__in=['sms_inbound', 'sms_outbound'])
                ).annotate(
                    period=trunc_func('created_at')
                ).values('period').annotate(
                    total_sms=Coalesce(Count('transaction_id'), 0),
                    inbound_sms=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_inbound')), 0),
                    outbound_sms=Coalesce(Count('transaction_id', filter=Q(transaction_type='sms_outbound')), 0),
                    inbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_inbound'), output_field=DecimalField()), Decimal('0')),
                    outbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='sms_outbound'), output_field=DecimalField()), Decimal('0')),
                    total_usage=Coalesce(Sum(F('amount') * -1, output_field=DecimalField()), Decimal('0'))
                ).order_by('period')
                
                for item in sms_data:
                    period_str = item['period'].strftime('%Y-%m-%d')
                    if period_str not in result_data:
                        result_data[period_str] = {'period': period_str, 'period_date': item['period']}
                    
                    result_data[period_str]['sms_data'] = {
                        'total_sms': item['total_sms'],
                        'inbound_sms': item['inbound_sms'],
                        'outbound_sms': item['outbound_sms'],
                        'inbound_usage': float(item['inbound_usage']),
                        'outbound_usage': float(item['outbound_usage']),
                        'total_usage': float(item['total_usage'])
                    }
            
            if data_type in ['call', 'both']:
                call_data = GHLTransaction.objects.filter(
                    base_filters & Q(transaction_type__in=['call_inbound', 'call_outbound'])
                ).annotate(
                    period=trunc_func('created_at')
                ).values('period').annotate(
                    total_calls=Coalesce(Count('transaction_id'), 0),
                    inbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_inbound')), 0),
                    outbound_calls=Coalesce(Count('transaction_id', filter=Q(transaction_type='call_outbound')), 0),
                    total_duration=Coalesce(Sum('duration'), 0),
                    inbound_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_inbound')), 0),
                    outbound_duration=Coalesce(Sum('duration', filter=Q(transaction_type='call_outbound')), 0),
                    inbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_inbound'), output_field=DecimalField()), Decimal('0')),
                    outbound_usage=Coalesce(Sum(F('amount') * -1, filter=Q(transaction_type='call_outbound'), output_field=DecimalField()), Decimal('0')),
                    total_usage=Coalesce(Sum(F('amount') * -1, output_field=DecimalField()), Decimal('0'))
                ).order_by('period')
                
                for item in call_data:
                    period_str = item['period'].strftime('%Y-%m-%d')
                    if period_str not in result_data:
                        result_data[period_str] = {'period': period_str, 'period_date': item['period']}
                    
                    inbound_minutes = float(item['inbound_duration']) / 60.0
                    outbound_minutes = float(item['outbound_duration']) / 60.0
                    total_minutes = float(item['total_duration']) / 60.0
                    
                    result_data[period_str]['call_data'] = {
                        'total_calls': item['total_calls'],
                        'inbound_calls': item['inbound_calls'],
                        'outbound_calls': item['outbound_calls'],
                        'total_duration': item['total_duration'],
                        'inbound_duration': item['inbound_duration'],
                        'outbound_duration': item['outbound_duration'],
                        'inbound_minutes': inbound_minutes,
                        'outbound_minutes': outbound_minutes,
                        'total_minutes': total_minutes,
                        'inbound_usage': float(item['inbound_usage']),
                        'outbound_usage': float(item['outbound_usage']),
                        'total_usage': float(item['total_usage'])
                    }
            
            if data_type == 'both':
                for period_data in result_data.values():
                    sms_data = period_data.get('sms_data', {})
                    call_data = period_data.get('call_data', {})
                    
                    period_data['combined_usage'] = {
                        'total_inbound_usage': sms_data.get('inbound_usage', 0) + call_data.get('inbound_usage', 0),
                        'total_outbound_usage': sms_data.get('outbound_usage', 0) + call_data.get('outbound_usage', 0),
                        'total_usage': sms_data.get('total_usage', 0) + call_data.get('total_usage', 0)
                    }
            
            result_list = sorted(result_data.values(), key=lambda x: x['period'])
            
            result = {
                'data': result_list,
                'total_records': len(result_list),
                'graph_type': graph_type,
                'data_type': data_type,
                'view_type': view_type,
                'date_range': {
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat()
                }
            }
            
            return AnalyticsComputer.serialize_datetime_data(result)
            
        except Exception as e:
            logger.error(f"Error computing bar graph analytics: {str(e)}")
            raise

    @staticmethod
    def store_analytics_cache(cache_type, data, user_id=None, start_date=None, end_date=None):
        """Store computed analytics data in cache"""
        try:
            cache_key_parts = [cache_type]
            if user_id:
                cache_key_parts.append(f"user_{user_id}")
            if start_date and end_date:
                cache_key_parts.append(f"{start_date}_{end_date}")
            
            cache_key = "_".join(cache_key_parts)
            
            cache_obj, created = AnalyticsCache.objects.update_or_create(
                cache_key=cache_key,
                defaults={
                    'cache_type': cache_type,
                    'data': json.dumps(data),
                    'user_id': user_id,
                    'start_date': start_date,
                    'end_date': end_date,
                    'computed_at': timezone.now(),
                    'record_count': data.get('total_messages', 0) + data.get('total_calls', 0)
                }
            )
            
            logger.info(f"{'Created' if created else 'Updated'} analytics cache: {cache_key}")
            return cache_obj
            
        except Exception as e:
            logger.error(f"Error storing analytics cache: {str(e)}")
            raise

    @staticmethod
    def get_analytics_cache(cache_type, user_id=None, start_date=None, end_date=None, max_age_hours=10):
        """Retrieve analytics data from cache if available and fresh"""
        try:
            cache_key_parts = [cache_type]
            if user_id:
                cache_key_parts.append(f"user_{user_id}")
            if start_date and end_date:
                cache_key_parts.append(f"{start_date}_{end_date}")
            
            cache_key = "_".join(cache_key_parts)
            
            cutoff_time = timezone.now() - timedelta(hours=max_age_hours)
            
            try:
                cache_obj = AnalyticsCache.objects.get(
                    cache_key=cache_key,
                    computed_at__gte=cutoff_time
                )
                logger.info(f"Retrieved fresh analytics cache: {cache_key}")
                return json.loads(cache_obj.data)
            except AnalyticsCache.DoesNotExist:
                logger.info(f"No fresh cache found for: {cache_key}")
                return None
                
        except Exception as e:
            logger.error(f"Error retrieving analytics cache: {str(e)}")
            return None




def fetch_transactions_for_location(ghl_credential: 'GHLAuthCredentials', days_ago_start=10, days_ago_end=0, page_limit=50):
    print(f"Fetching transactions for {ghl_credential.location_name} (ID: {ghl_credential.location_id})")

    token_id = get_ghl_auth_token(ghl_credential)
    if not token_id:
        print(f"Failed to get a valid token for {ghl_credential.location_name}.")
        return

    BASE_URL = f"https://services.leadconnectorhq.com/blade-platform/transactions/LOCATION/{ghl_credential.location_id}"

    today = datetime.now()
    start_date = (today - timedelta(days=days_ago_start)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    end_date = (today - timedelta(days=days_ago_end)).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    skip = 0
    while True:
        payload = {
            "companyId": ghl_credential.company_id,
            "locationId": ghl_credential.location_id,
            "filters": {
                "settlementTime": {
                    "from": start_date,
                    "to": end_date
                }
            },
            "limit": page_limit,
            "skip": skip,
            "timezone": "Asia/Calcutta"
        }

        headers = {
            "Token-id": token_id,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Source": "WEB_USER",
            "Channel": "APP",
            "Version": "2021-04-15"
        }

        response = requests.post(BASE_URL, json=payload, headers=headers)

        if response.status_code == 401:
            token_id = get_ghl_auth_token(ghl_credential)
            if not token_id:
                print(f"Failed to refresh token for {ghl_credential.location_name}.")
                break
            headers["Token-id"] = token_id
            continue

        if response.status_code != 200:
            print(f"Error fetching transactions: {response.status_code} - {response.text}")
            break

        data = response.json().get("data", [])
        if not data:
            break

        to_upsert = []
        for item in data:
            desc = item.get("description", "")
            message_id = None
            if "Ref-" in desc:
                message_id = desc.split("Ref-")[-1].strip()

            # Detect transaction type
            if "Inbound SMS" in desc:
                transaction_type = "sms_inbound"
            elif "Outbound SMS" in desc:
                transaction_type = "sms_outbound"
            elif "Inbound Call" in desc:
                transaction_type = "call_inbound"
            elif "Outbound Call" in desc:
                transaction_type = "call_outbound"
            else:
                transaction_type = "other"

            # Fetch duration for calls
            duration = 0
            if "Call" in desc and message_id:
                try:
                    call = CallReport.objects.get(message_id=message_id)
                    duration = call.duration
                except CallReport.DoesNotExist:
                    duration = 0


    

            # Build object
            to_upsert.append(
                GHLTransaction(
                    transaction_id=item["id"],
                    ghl_credential=ghl_credential,
                    date=item.get("date"),
                    parsed_date=parse_date_string(item.get("date"), ghl_credential.timezone),
                    description=desc,
                    amount=item.get("amount"),
                    balance=item.get("balance"),
                    credits=item.get("credits"),
                    total_balance=item.get("totalBalance"),
                    message_date=item.get("messageDate"),
                    prev_wallet_balance=item.get("prevWalletBalance"),
                    prev_wallet_credits=item.get("prevWalletCredits"),
                    location_name=item.get("locationName"),
                    message_id=message_id,
                    duration=duration,
                    transaction_type=transaction_type,
                )
            )

        # print("test: ", item.get("date"), ghl_credential.timezone)
        # print("convert time: ",parse_date_string(item.get("date"), ghl_credential.timezone))
        # break

        # Bulk insert/update in one go
        if to_upsert:
            with transaction.atomic():
                GHLTransaction.objects.bulk_create(
                    to_upsert,
                    update_conflicts=True,
                    update_fields=[
                        "ghl_credential", "date", "description", "amount",
                        "balance", "credits", "total_balance", "message_date",
                        "prev_wallet_balance", "prev_wallet_credits",
                        "location_name", "message_id", "duration", "transaction_type","parsed_date"
                    ],
                    unique_fields=["transaction_id"],
                )

        if len(data) < page_limit:
            break
        skip += page_limit

        


from datetime import datetime
import re
import pytz

def parse_date_string(date_str, tz_str="UTC"):
    """
    Convert GHL date string into a timezone-aware datetime using the given tz_str.
    Example date_str: "Sep 22nd 2025, 10:28:02 PM"
    """
    print(f"Parsing date_str: '{date_str}' with timezone: '{tz_str}'")
    
    if not date_str:
        print("Empty date_str, returning None")
        return None
    
    try:
        # Remove st/nd/rd/th
        clean_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
        print(f"Cleaned date string: '{clean_str}'")
        
        # Parse naive datetime
        naive_dt = datetime.strptime(clean_str, "%b %d %Y, %I:%M:%S %p")
        print(f"Parsed naive datetime: {naive_dt}")
        
        # Convert to timezone-aware
        try:
            tz = pytz.timezone(tz_str) if tz_str else pytz.UTC
        except Exception as e:
            print(f"Invalid timezone '{tz_str}', using UTC: {e}")
            tz = pytz.UTC
        
        # Use localize for naive datetime
        try:
            aware_dt = tz.localize(naive_dt)
        except ValueError as e:
            # Handle ambiguous times (DST transitions)
            print(f"Ambiguous time, using fold=0: {e}")
            aware_dt = tz.localize(naive_dt, is_dst=False)
        
        print(f"Final timezone-aware datetime: {aware_dt}")
        return aware_dt
        
    except Exception as e:
        print(f"Error parsing date '{date_str}': {e}")
        # Fallback: try to return current time in the specified timezone
        try:
            tz = pytz.timezone(tz_str) if tz_str else pytz.UTC
            return datetime.now(tz)
        except:
            return datetime.now(pytz.UTC)



from django.utils.timezone import make_aware

def update_sms_segments_for_location(ghl_credential: 'GHLAuthCredentials', daily_fetch=False):
    """
    Fetch detailed transaction info for sms_inbound and sms_outbound transactions
    and update their total_segments for all records in one go.
    """
    print(f"[START] Updating SMS segments for {ghl_credential.location_name} (ID: {ghl_credential.location_id})")

    token_id = get_ghl_auth_token(ghl_credential)
    if not token_id:
        print(f"[ERROR] Failed to get a valid token for {ghl_credential.location_name}.")
        return

    headers = {
        "Token-id": token_id,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Source": "WEB_USER",
        "Channel": "APP",
        "Version": "2021-04-15"
    }

    qs = GHLTransaction.objects.filter(
        ghl_credential=ghl_credential,
        transaction_type__in=["sms_inbound", "sms_outbound"],
    )

    # Get all SMS transactions for this location
    if daily_fetch:
        today = make_aware(datetime.now())
        yesterday = today - timedelta(days=1)
        qs = qs.filter(parsed_date__range=(yesterday, today))
        print(f"[INFO] Daily fetch enabled: fetching transactions from {yesterday} to {today}")

    total_records = qs.count()
    print(f"[INFO] Found {total_records} SMS transactions with total_segments=0 for update.")

    to_update = []
    processed = 0
    updated = 0
    failed = 0

    for tx in qs.iterator():
        processed += 1
        print(f"[PROCESS] ({processed}/{total_records}) Fetching details for transaction_id={tx.transaction_id}")

        url = f"https://services.leadconnectorhq.com/saas_service/location-wallet/{ghl_credential.location_id}/details/{tx.transaction_id}"
        response = requests.get(url, headers=headers)

        if response.status_code == 401:
            print(f"[WARN] Token expired while fetching transaction_id={tx.transaction_id}. Refreshing...")
            token_id = get_ghl_auth_token(ghl_credential)
            if not token_id:
                print(f"[ERROR] Failed to refresh token for {ghl_credential.location_name}. Aborting.")
                break
            headers["Token-id"] = token_id
            response = requests.get(url, headers=headers)

        if response.status_code != 200:
            failed += 1
            print(f"[ERROR] Failed to fetch details for transaction_id={tx.transaction_id}: {response.status_code} - {response.text}")
            continue

        try:
            data = response.json()
            segments = (
                data.get("details", {})
                .get("eventBody", {})
                .get("meta", {})
                .get("segments")
            )
            if segments is not None:
                tx.total_segments = segments
                to_update.append(tx)
                updated += 1
                print(f"[SUCCESS] transaction_id={tx.transaction_id} -> segments={segments}")
            else:
                print(f"[INFO] transaction_id={tx.transaction_id} has no 'segments' field in response.")
        except Exception as e:
            failed += 1
            print(f"[EXCEPTION] Parsing error for transaction_id={tx.transaction_id}: {e}")
            continue

    # Final bulk update for all collected records
    if to_update:
        with transaction.atomic():
            GHLTransaction.objects.bulk_update(to_update, ["total_segments"])
        print(f"[DB] Bulk updated {len(to_update)} records with segment counts.")

    print(f"[COMPLETE] Location={ghl_credential.location_name} | Processed={processed}, Updated={updated}, Failed={failed}")
