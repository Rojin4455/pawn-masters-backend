from django.shortcuts import render
from decouple import config
import requests
from django.http import JsonResponse
import json
from django.shortcuts import redirect, render
from core.models import GHLAuthCredentials
from django.views.decorators.csrf import csrf_exempt
from core.services import get_location_name
from urllib.parse import urlencode
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .serializers import UserSerializer, RegisterSerializer
from accounts_management_app.models import TextMessage


# Create your views here.

GHL_CLIENT_ID = config("GHL_CLIENT_ID")
GHL_CLIENT_SECRET = config("GHL_CLIENT_SECRET")
GHL_REDIRECTED_URI = config("GHL_REDIRECTED_URI")
FRONTEND_URL = config("FRONTEND_URL")
TOKEN_URL = "https://services.leadconnectorhq.com/oauth/token"
SCOPE = config("SCOPE")

def auth_connect(request):
    auth_url = ("https://marketplace.gohighlevel.com/oauth/chooselocation?response_type=code&"
                f"redirect_uri={GHL_REDIRECTED_URI}&"
                f"client_id={GHL_CLIENT_ID}&"
                f"scope={SCOPE}"
                )
    return redirect(auth_url)



def callback(request):
    
    code = request.GET.get('code')

    if not code:
        return JsonResponse({"error": "Authorization code not received from OAuth"}, status=400)

    return redirect(f'{config("BASE_URI")}/api/core/auth/tokens?code={code}')


def tokens(request):
    authorization_code = request.GET.get("code")

    if not authorization_code:
        return JsonResponse({"error": "Authorization code not found"}, status=400)

    data = {
        "grant_type": "authorization_code",
        "client_id": GHL_CLIENT_ID,
        "client_secret": GHL_CLIENT_SECRET,
        "redirect_uri": GHL_REDIRECTED_URI,
        "code": authorization_code,
    }

    response = requests.post(TOKEN_URL, data=data)

    try:
        response_data = response.json()
        if not response_data:
            return
        print("response.data: ", response_data)
        if not response_data.get('access_token'):
            return render(request, 'onboard.html', context={
                "message": "Invalid JSON response from API",
                "status_code": response.status_code,
                "response_text": response.text[:400]
            }, status=400)
        

        location_name, timezone = get_location_name(location_id=response_data.get("locationId"), access_token=response_data.get('access_token'))
        

        obj, created = GHLAuthCredentials.objects.update_or_create(
            location_id= response_data.get("locationId"),
            defaults={
                "access_token": response_data.get("access_token"),
                "refresh_token": response_data.get("refresh_token"),
                "expires_in": response_data.get("expires_in"),
                "scope": response_data.get("scope"),
                "user_type": response_data.get("userType"),
                "company_id": response_data.get("companyId"),
                "user_id":response_data.get("userId"),
                "location_name":location_name,
                "timezone": timezone
            }
        )
        
        obj.is_approved=True
        obj.save()
        query_params = urlencode({
            "locationId":response_data.get("locationId"),
        })

        frontend_url = f"{FRONTEND_URL}/admin/settings/sms-groups?{query_params}"
        
        return redirect(frontend_url)
        
    except requests.exceptions.JSONDecodeError:
        frontend_url = "http://localhost:3000/admin/error-onboard"
        return redirect(frontend_url)
    



# class RegisterView(APIView):
#     """
#     Register a new user
#     """
#     permission_classes = [AllowAny]
    
#     def post(self, request):
#         serializer = RegisterSerializer(data=request.data)
#         if serializer.is_valid():
#             user = serializer.save()
#             refresh = RefreshToken.for_user(user)
#             return Response({
#                 'user': UserSerializer(user).data,
#                 'refresh': str(refresh),
#                 'access': str(refresh.access_token),
#                 'message': 'User registered successfully'
#             }, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """
    Logout user by blacklisting the refresh token
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data["refresh_token"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({
                'message': 'Successfully logged out'
            }, status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response({
                'error': 'Invalid token'
            }, status=status.HTTP_400_BAD_REQUEST)


# class UserView(APIView):
#     """
#     Get current user details
#     """
#     permission_classes = [IsAuthenticated]
    
#     def get(self, request):
#         serializer = UserSerializer(request.user)
#         return Response(serializer.data)
    
#     def put(self, request):
#         serializer = UserSerializer(request.user, data=request.data, partial=True)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# import math
# text = TextMessage.objects.get(message_id='jWtWLCzqunerFNIwr7eK')
# print("conversation_id:    ",text.conversation.conversation_id)
# print("text: ", len(text.body))

# print("segmants:    ",math.ceil(len(text.body) / 160))
# print(text.conversation.contact.phone)




from django.http import JsonResponse
from django.views import View
from celery import group
from .models import GHLAuthCredentials,LocationSyncLog
from .tasks import (
    async_fetch_all_contacts,
    async_sync_conversations_with_messages,
    async_sync_conversations_with_calls,mark_location_synced,sync_location_data_sequential,sync_single_location_parallel
)
from django.utils import timezone
from celery import chain, group




class RefetchAllLocationsView(View):
    """
    Endpoint to trigger re-fetching with improved load distribution
    """
    def post(self, request, *args, **kwargs):
        # Get approved locations
        try:
            data = json.loads(request.body.decode("utf-8"))
        except json.JSONDecodeError:
            data = {}

        location_ids = data.get("location_ids", [])
        print("location ID:", location_ids)
        if not location_ids:
            # If no ids provided, fallback to all approved
            credentials = GHLAuthCredentials.objects.filter(is_approved=True)
        else:
            # Filter only provided ids
            credentials = GHLAuthCredentials.objects.filter(
                location_id__in=location_ids, is_approved=True
            )
        
        if not credentials.exists():
            return JsonResponse({"status": "error", "message": "No approved locations found."}, status=404)
        
        print(request.GET.get('mode'))
        print(credentials)
        
        # return JsonResponse({"status": "success", "message": "success found"}, status=200)
        # Option 1: Parallel Processing (recommended for better distribution)
        if request.GET.get('mode') == 'parallel':
            return self._handle_parallel_processing(credentials)
        
        # Option 2: Round-robin distribution (alternative approach)
        elif request.GET.get('mode') == 'roundrobin':
            
            return self._handle_round_robin_distribution(credentials)
        
        # Option 3: Default - improved sequential with better queue distribution
        else:
            return self._handle_improved_sequential(credentials)
    
    def _handle_parallel_processing(self, credentials):
        """Process all locations with parallel task distribution"""
        task_results = []
        
        for cred in credentials:
            # Each location gets processed with parallel sub-tasks
            result = sync_single_location_parallel.apply_async(
                args=[cred.location_id, cred.access_token],
                queue='data_sync'  # Primary queue for coordination
            )
            
            task_results.append({
                'location_id': cred.location_id,
                'location_name': cred.location_name,
                'task_id': str(result.id),
                'processing_mode': 'parallel'
            })
        
        return JsonResponse({
            "status": "success",
            "message": f"Triggered parallel processing for {credentials.count()} locations.",
            "locations": task_results,
        })
    
    def _handle_round_robin_distribution(self, credentials):
        """Distribute locations across different queues in round-robin fashion"""
        queues = ['data_sync', 'celery', 'priority']
        task_results = []
        
        for i, cred in enumerate(credentials):
            # Rotate through queues
            queue = queues[i % len(queues)]
            
            log = LocationSyncLog.objects.create(
                location=cred,
                status="pending",
                started_at=timezone.now()
            )
            
            result = sync_location_data_sequential.apply_async(
                args=[cred.location_id, cred.access_token],
                queue=queue
            )
            
            task_results.append({
                'location_id': cred.location_id,
                'location_name': cred.location_name,
                'task_id': str(result.id),
                'queue': queue,
                'log_id': log.id,
                'processing_mode': 'round_robin'
            })
        
        return JsonResponse({
            "status": "success",
            "message": f"Triggered round-robin processing for {credentials.count()} locations.",
            "locations": task_results,
        })
    
    def _handle_improved_sequential(self, credentials):
        """Improved sequential processing with better distribution"""
        task_results = []
        
        for cred in credentials:
            log = LocationSyncLog.objects.create(
                location=cred,
                status="pending",
                started_at=timezone.now()
            )
            
            # Use sequential task but let Celery distribute across workers
            result = sync_location_data_sequential.apply_async(
                args=[cred.location_id, cred.access_token],
                queue='data_sync'
            )
            
            task_results.append({
                'location_id': cred.location_id,
                'location_name': cred.location_name,
                'task_id': str(result.id),
                'log_id': log.id,
                'processing_mode': 'sequential_improved'
            })
        
        return JsonResponse({
            "status": "success",
            "message": f"Triggered improved sequential processing for {credentials.count()} locations.",
            "locations": task_results,
        })

