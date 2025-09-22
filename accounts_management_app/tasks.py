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
        fetch_calls_for_last_days_for_location(credential,days_to_fetch=365)
        print(f"--- Finished processing for {credential.location_name} ---\n")


@shared_task
def refresh_all_sync_conversation_messages():
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
        fetch_calls_for_last_days_for_location(credential,days_to_fetch=365)
        print(f"--- Finished processing for {credential.location_name} ---\n")




from celery import shared_task
from django.utils import timezone
from django.db.models import Count, Sum, Q
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from datetime import datetime, timedelta
import time
import logging

from .models import AnalyticsCache, AnalyticsCacheLog
from accounts_management_app.models import TextMessage  # Adjust import paths as needed
from core.models import CallReport
from .utils import AnalyticsComputer


logger = logging.getLogger(__name__)

@shared_task(bind=True)
def generate_analytics_cache(self, cache_types=None):
    """
    Main task to generate all analytics cache data
    """
    if cache_types is None:
        cache_types = [
            'usage_analytics_account',
            'usage_analytics_company', 
            'bar_graph_daily',
            'bar_graph_weekly',
            'bar_graph_monthly',
            'usage_summary'
        ]
    
    results = {}
    
    for cache_type in cache_types:
        try:
            if cache_type == 'usage_summary':
                result = generate_usage_summary_cache.delay()
            elif cache_type.startswith('usage_analytics'):
                view_type = cache_type.split('_')[-1]  # account or company
                result = generate_usage_analytics_cache.delay(view_type)
            elif cache_type.startswith('bar_graph'):
                graph_type = cache_type.split('_')[-1]  # daily, weekly, monthly
                result = generate_bar_graph_cache.delay(graph_type)
            
            results[cache_type] = 'scheduled'
            
        except Exception as e:
            logger.error(f"Failed to schedule {cache_type}: {str(e)}")
            results[cache_type] = f'error: {str(e)}'
    
    return results

@shared_task(bind=True)
def generate_usage_summary_cache(self):
    """
    Generate and cache usage summary data
    """
    cache_type = 'usage_summary'
    log_entry = AnalyticsCacheLog.objects.create(
        cache_type=cache_type,
        status='started',
        started_at=timezone.now()
    )
    
    try:
        start_time = time.time()
        
        cached_data = AnalyticsComputer.get_usage_summary_data()
        
        AnalyticsCache.objects.filter(cache_type=cache_type).delete()
        
        AnalyticsCache.objects.create(
            cache_type=cache_type,
            cached_data=cached_data,
            computation_time_seconds=time.time() - start_time,
            record_count=cached_data.get('total_records', 0)
        )
        
        log_entry.status = 'completed'
        log_entry.completed_at = timezone.now()
        log_entry.duration_seconds = time.time() - start_time
        log_entry.records_processed = cached_data.get('total_records', 0)
        log_entry.save()
        
        logger.info(f"Successfully generated {cache_type} cache")
        return {'status': 'success', 'duration': time.time() - start_time}
        
    except Exception as e:
        log_entry.status = 'failed'
        log_entry.completed_at = timezone.now()
        log_entry.error_message = str(e)
        log_entry.save()
        
        logger.error(f"Failed to generate {cache_type} cache: {str(e)}")
        raise

@shared_task(bind=True)
def generate_usage_analytics_cache(self, view_type='account'):
    """
    Generate and cache usage analytics data for account or company view
    """
    cache_type = f'usage_analytics_{view_type}'
    log_entry = AnalyticsCacheLog.objects.create(
        cache_type=cache_type,
        status='started',
        started_at=timezone.now()
    )
    
    try:
        start_time = time.time()
        
        date_ranges = [
            {'days': 30, 'label': 'last_30_days'},
            {'days': 90, 'label': 'last_90_days'},
            {'days': 365, 'label': 'last_365_days'},
        ]
        
        cached_data = {}
        total_records = 0
        
        for date_range in date_ranges:
            end_date = timezone.now().date()
            start_date = end_date - timedelta(days=date_range['days'])
            
            if view_type == 'account':
                data = AnalyticsComputer.get_usage_analytics_data(
                    start_date=start_date, 
                    end_date=end_date
                )
            else:
                data = AnalyticsComputer.get_company_usage_analytics_data(
                    start_date=start_date, 
                    end_date=end_date
                )
            
            cached_data[date_range['label']] = {
                'data': data,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'count': data.get('total_messages', 0) + data.get('total_calls', 0)
            }
            total_records += data.get('total_messages', 0) + data.get('total_calls', 0)
        
        cached_data['generated_at'] = timezone.now().isoformat()
        
        AnalyticsCache.objects.filter(
            cache_type=cache_type,
            view_type=view_type
        ).delete()
        
        AnalyticsCache.objects.create(
            cache_type=cache_type,
            view_type=view_type,
            cached_data=cached_data,
            computation_time_seconds=time.time() - start_time,
            record_count=total_records
        )
        
        log_entry.status = 'completed'
        log_entry.completed_at = timezone.now()
        log_entry.duration_seconds = time.time() - start_time
        log_entry.records_processed = total_records
        log_entry.save()
        
        logger.info(f"Successfully generated {cache_type} cache")
        return {'status': 'success', 'duration': time.time() - start_time}
        
    except Exception as e:
        log_entry.status = 'failed'
        log_entry.completed_at = timezone.now()
        log_entry.error_message = str(e)
        log_entry.save()
        
        logger.error(f"Failed to generate {cache_type} cache: {str(e)}")
        raise

@shared_task(bind=True)
def generate_bar_graph_cache(self, graph_type='daily'):
    """
    Generate and cache bar graph analytics data
    """
    cache_type = f'bar_graph_{graph_type}'
    log_entry = AnalyticsCacheLog.objects.create(
        cache_type=cache_type,
        status='started',
        started_at=timezone.now()
    )
    
    try:
        start_time = time.time()
        
        data_types = ['sms', 'call', 'both']
        view_types = ['account', 'company']
        
        cached_data = {}
        total_records = 0
        
        end_date = timezone.now().date()
        if graph_type == 'daily':
            start_date = end_date - timedelta(days=90)
        elif graph_type == 'weekly':
            start_date = end_date - timedelta(days=365)
        else:  # monthly
            start_date = end_date - timedelta(days=730)  # 2 years
        
        base_filters = {
            'date_range': {
                'start': start_date,
                'end': end_date
            }
        }
        
        for view_type in view_types:
            for data_type in data_types:
                try:
                    data = AnalyticsComputer.get_bar_graph_analytics_data(
                        start_date=start_date,
                        end_date=end_date,
                        graph_type=graph_type,
                        data_type=data_type,
                        view_type=view_type
                    )
                    
                    key = f"{view_type}_{data_type}"
                    cached_data[key] = {
                        'data': data,
                        'count': data.get('total_records', 0)
                    }
                    total_records += data.get('total_records', 0)
                    
                except Exception as e:
                    logger.warning(f"Failed to generate {key} for {graph_type}: {str(e)}")
                    cached_data[key] = {'data': [], 'count': 0, 'error': str(e)}
        
        cached_data['generated_at'] = timezone.now().isoformat()
        cached_data['date_range'] = {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
        
        AnalyticsCache.objects.filter(cache_type=cache_type).delete()
        
        AnalyticsCache.objects.create(
            cache_type=cache_type,
            cached_data=cached_data,
            computation_time_seconds=time.time() - start_time,
            record_count=total_records
        )
        
        log_entry.status = 'completed'
        log_entry.completed_at = timezone.now()
        log_entry.duration_seconds = time.time() - start_time
        log_entry.records_processed = total_records
        log_entry.save()
        
        logger.info(f"Successfully generated {cache_type} cache")
        return {'status': 'success', 'duration': time.time() - start_time}
        
    except Exception as e:
        log_entry.status = 'failed'
        log_entry.completed_at = timezone.now()
        log_entry.error_message = str(e)
        log_entry.save()
        
        logger.error(f"Failed to generate {cache_type} cache: {str(e)}")
        raise

@shared_task
def cleanup_old_cache_entries():
    """
    Clean up old cache entries and logs
    """
    cache_types = AnalyticsCache.objects.values_list('cache_type', flat=True).distinct()
    
    for cache_type in cache_types:
        old_entries = AnalyticsCache.objects.filter(
            cache_type=cache_type
        ).order_by('-created_at')[5:]  # Keep latest 5
        
        if old_entries:
            AnalyticsCache.objects.filter(
                id__in=[entry.id for entry in old_entries]
            ).delete()
    
    cutoff_date = timezone.now() - timedelta(days=30)
    AnalyticsCacheLog.objects.filter(started_at__lt=cutoff_date).delete()
    
    return {'status': 'completed', 'cleaned_at': timezone.now().isoformat()}