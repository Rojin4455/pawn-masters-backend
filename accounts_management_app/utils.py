import requests
from decouple import config
from core.serializers import FirebaseTokenSerializer, LeadConnectorAuthSerializer, IdentityToolkitAuthSerializer
from core.models import FirebaseToken, LeadConnectorAuth, IdentityToolkitAuth, GHLAuthCredentials, CallReport
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