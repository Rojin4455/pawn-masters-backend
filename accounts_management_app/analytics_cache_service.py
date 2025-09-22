# services/analytics_cache_service.py

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Q, Count, Sum, Min, Value
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from dateutil.relativedelta import relativedelta
import hashlib
import json
from .models import AnalyticsCache
logger = logging.getLogger(__name__)

class AnalyticsCacheService:
    """
    Service class to handle analytics data caching
    """
    
    @staticmethod
    def generate_cache_key(cache_type, period_type, data_type, filters):
        """Generate a unique cache key based on parameters"""
        key_data = {
            'cache_type': cache_type,
            'period_type': period_type,
            'data_type': data_type,
            'filters': filters
        }
        key_string = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    @staticmethod
    def get_date_ranges_to_cache():
        """
        Define the date ranges we want to pre-cache
        Returns list of (start_date, end_date) tuples
        """
        now = timezone.now()
        ranges = []
        
        # Last 30 days
        ranges.append((now - timedelta(days=30), now))
        
        # Last 90 days
        ranges.append((now - timedelta(days=90), now))
        
        # Last 6 months
        ranges.append((now - relativedelta(months=6), now))
        
        # Last 12 months
        ranges.append((now - relativedelta(months=12), now))
        
        # Current year
        current_year_start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        ranges.append((current_year_start, now))
        
        # Previous year
        prev_year_start = current_year_start - relativedelta(years=1)
        prev_year_end = current_year_start - timedelta(seconds=1)
        ranges.append((prev_year_start, prev_year_end))
        
        return ranges
    
    @staticmethod
    def get_cached_data(cache_type, period_type, data_type, filters, date_range=None):
        """
        Retrieve cached data if available and valid
        """
        try:
            query = AnalyticsCache.objects.filter(
                cache_type=cache_type,
                period_type=period_type,
                data_type=data_type,
                is_valid=True
            )
            
            # Apply filters
            if filters.get('category_id'):
                query = query.filter(category_id=filters['category_id'])
            if filters.get('company_id'):
                query = query.filter(company_id=filters['company_id'])
            if filters.get('location_id'):
                query = query.filter(location_id=filters['location_id'])
            
            # Apply date range filter
            if date_range:
                query = query.filter(
                    start_date__lte=date_range['start'],
                    end_date__gte=date_range['end']
                )
            
            # Get the most recent cache entry
            cache_entry = query.order_by('-created_at').first()
            
            if cache_entry:
                logger.info(f"Cache hit for {cache_type}_{period_type}_{data_type}")
                return cache_entry.cached_data
            
            logger.info(f"Cache miss for {cache_type}_{period_type}_{data_type}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving cached data: {str(e)}")
            return None
    
    @staticmethod
    def save_cached_data(cache_type, period_type, data_type, filters, data, date_range, total_count=0):
        """
        Save computed analytics data to cache
        """

        def decimal_to_float(obj):
            import decimal

            print(obj)
            if isinstance(obj, decimal.Decimal):
                return float(obj)
            if isinstance(obj, dict):
                return {k: decimal_to_float(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [decimal_to_float(v) for v in obj]
            return obj
        try:
            with transaction.atomic():
                # Invalidate existing cache entries for the same parameters
                AnalyticsCache.objects.filter(
                    cache_type=cache_type,
                    period_type=period_type,
                    data_type=data_type,
                    category_id=filters.get('category_id'),
                    company_id=filters.get('company_id'),
                    location_id=filters.get('location_id'),
                ).update(is_valid=False)
                
                # Create new cache entry
                cache_entry = AnalyticsCache.objects.create(
                    cache_type=cache_type,
                    period_type=period_type,
                    data_type=data_type,
                    category_id=filters.get('category_id'),
                    company_id=filters.get('company_id'),
                    location_id=filters.get('location_id'),
                    start_date=date_range['start'],
                    end_date=date_range['end'],
                    cached_data=decimal_to_float(data),
                    total_count=total_count,
                )
                
                logger.info(f"Cached data saved: {cache_entry.id}")
                return cache_entry
                
        except Exception as e:
            logger.error(f"Error saving cached data: {str(e)}")
            return None
    
    @staticmethod
    def invalidate_cache(cache_type=None, filters=None):
        """
        Invalidate cached data based on criteria
        """
        try:
            query = AnalyticsCache.objects.filter(is_valid=True)
            
            if cache_type:
                query = query.filter(cache_type=cache_type)
            
            if filters:
                if filters.get('category_id'):
                    query = query.filter(category_id=filters['category_id'])
                if filters.get('company_id'):
                    query = query.filter(company_id=filters['company_id'])
                if filters.get('location_id'):
                    query = query.filter(location_id=filters['location_id'])
            
            updated_count = query.update(is_valid=False)
            logger.info(f"Invalidated {updated_count} cache entries")
            return updated_count
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {str(e)}")
            return 0
    
    @staticmethod
    def cleanup_old_cache():
        """
        Remove old cache entries (older than 30 days)
        """
        try:
            cutoff_date = timezone.now() - timedelta(days=30)
            deleted_count = AnalyticsCache.objects.filter(
                created_at__lt=cutoff_date
            ).delete()[0]
            
            logger.info(f"Cleaned up {deleted_count} old cache entries")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up cache: {str(e)}")
            return 0


class AnalyticsDataGenerator:
    """
    Generates analytics data for caching
    """
    
    def __init__(self, viewset_instance):
        """
        Initialize with the SMSAnalyticsViewSet instance to reuse existing methods
        """
        self.viewset = viewset_instance
    
    def generate_account_view_data(self, filters, date_range):
        """Generate account view data"""
        try:
            # Use existing viewset method
            data = self.viewset.get_account_view_data({
                **filters,
                'date_range': date_range
            })
            return data
        except Exception as e:
            logger.error(f"Error generating account view data: {str(e)}")
            raise
    
    def generate_company_view_data(self, filters, date_range):
        """Generate company view data"""
        try:
            # Use existing viewset method
            data = self.viewset.get_company_view_data({
                **filters,
                'date_range': date_range
            })
            return data
        except Exception as e:
            logger.error(f"Error generating company view data: {str(e)}")
            raise
    
    def generate_bar_graph_data(self, filters, date_range, graph_type, data_type, view_type):
        """Generate bar graph analytics data"""
        try:
            # Build filters for the existing method
            filter_params = {
                'date_range': date_range,
                **filters
            }
            
            if graph_type == 'daily':
                data = self.viewset._get_daily_analytics(filter_params, data_type, view_type)
            elif graph_type == 'weekly':
                data = self.viewset._get_weekly_analytics(filter_params, data_type, view_type)
            elif graph_type == 'monthly':
                data = self.viewset._get_monthly_analytics(filter_params, data_type, view_type)
            else:
                raise ValueError(f"Invalid graph_type: {graph_type}")
            
            return data
        except Exception as e:
            logger.error(f"Error generating bar graph data: {str(e)}")
            raise