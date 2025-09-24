from rest_framework import generics, permissions
from core.models import GHLAuthCredentials,SMSDefaultConfiguration,CallReport
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import (
    Sum, Count, Q, F, Case, When, IntegerField, 
    DecimalField, OuterRef, Subquery, Min, Value
)
from django.db.models.functions import Coalesce
from decimal import Decimal
from .models import TextMessage, CallRecord
from .serializers import (
    AccountViewSerializer, CompanyViewSerializer, 
    AnalyticsRequestSerializer,
    GHLAuthCredentialsSerializer, 
    CompanyNameSearchSerializer,
    BarGraphAnalyticsRequestSerializer,
    GHLAuthCredentialsShortSerializer
)
from django.core.exceptions import ObjectDoesNotExist
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.db.models import Count, Sum, Q
import calendar


from django.db import transaction
from .serializers import SMSDefaultConfigurationSerializer, GHLCredentialsUpdateSerializer
from django.db import models

import json
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from accounts_management_app.models import WebhookLog
from accounts_management_app.tasks import handle_webhook_event,fetch_calls_task
from rest_framework.views import APIView
from accounts_management_app.utils import sync_wallet_balance,fetch_calls_for_last_days_for_location





class GHLAuthCredentialsListView(generics.ListAPIView):
    serializer_class = GHLAuthCredentialsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        search_term = self.request.query_params.get('search')
        if search_term:
            return (
                GHLAuthCredentials.objects
                .filter(company_name__icontains=search_term)
                .values('company_name', 'company_id')
                .distinct()
            )
        else:
            return GHLAuthCredentials.objects.all()
    
    def get_serializer_class(self):
        # Use a lightweight serializer if search is present
        if self.request.query_params.get('search'):
            return CompanyNameSearchSerializer
        return GHLAuthCredentialsSerializer


class GHLAuthCredentialsDetailUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = GHLAuthCredentials.objects.all()
    serializer_class = GHLAuthCredentialsSerializer
    lookup_field = 'location_id'
    permission_classes = [permissions.IsAuthenticated]



# from rest_framework.pagination import PageNumberPagination

# from django.db.models import Count, Sum, Q
# from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth
# from django.utils import timezone
# from datetime import timedelta
# from decimal import Decimal
# from rest_framework import viewsets, status
# from rest_framework.decorators import action
# from rest_framework.response import Response
# from rest_framework.pagination import PageNumberPagination

# from .models import AnalyticsCache, AnalyticsCacheLog
# from .tasks import generate_analytics_cache
# from .serializers import AnalyticsRequestSerializer, BarGraphAnalyticsRequestSerializer, AccountViewWithCallsSerializer, CompanyViewWithCallsSerializer
# from dateutil.relativedelta import relativedelta


# class CustomPageNumberPagination(PageNumberPagination):
#     """
#     Custom pagination class to set page size and include additional metadata.
#     """
#     page_size = 10  # Set the default page size to 15 records
#     page_size_query_param = 'page_size'  # Allow client to override page size using ?page_size=X
#     max_page_size = 1000  # Maximum page size allowed

#     def get_paginated_response(self, data):
#         """
#         Overrides the default get_paginated_response to include custom metadata.
#         The custom metadata (view_type, filters_applied, total_results_count, etc.)
#         is expected to be set on the request object by the view.
#         """
#         custom_metadata = getattr(self.request, 'custom_metadata', {})

#         return Response({
#             'count': self.page.paginator.count,  # Total number of items across all pages
#             'next': self.get_next_link(),
#             'previous': self.get_previous_link(),
#             # Include custom metadata from the view
#             'view_type': custom_metadata.get('view_type'),
#             'filters_applied': custom_metadata.get('filters_applied'),
#             'graph_type': custom_metadata.get('graph_type'),
#             'data_type': custom_metadata.get('data_type'),
#             'date_range': custom_metadata.get('date_range'),
#             'location_ids': custom_metadata.get('location_ids'),
#             'company_ids': custom_metadata.get('company_ids'),
#             'total_results_count': custom_metadata.get('total_results_count'), # Total count before pagination
#             'cached': custom_metadata.get('cached', False),
#             'cache_generated_at': custom_metadata.get('cache_generated_at'),
#             'cache_generation_triggered': custom_metadata.get('cache_generation_triggered', False),
#             'data': data  # The paginated list of results for the current page
#         })


# from rest_framework import filters

# class SMSAnalyticsViewSet(viewsets.GenericViewSet):
#     pagination_class = CustomPageNumberPagination
#     filter_backends = [filters.SearchFilter]
#     search_fields = [
#         'conversation__location__location_name',
#         'conversation__location__location_id',
#         'conversation__location__company_name',
#     ]

#     """
#     ViewSet for SMS and Call usage analytics with optimized queries
#     """
#     def get_base_sms_queryset(self, filters):
#         """
#         Optimized SMS queryset with minimal joins and proper indexing
#         """
#         queryset = TextMessage.objects.select_related('conversation__location').filter(
#             conversation__location__is_approved=True
#         )

#         # Apply filters with proper field lookups
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             queryset = queryset.filter(
#                 date_added__gte=date_range['start'],
#                 date_added__lte=date_range['end']
#             )

#         if filters.get('category'):
#             queryset = queryset.filter(
#                 conversation__location__category_id=filters['category']
#             )

#         if filters.get('company_id'):
#             queryset = queryset.filter(
#                 conversation__location__company_id=filters['company_id']
#             )

#         return queryset

#     def get_base_calls_queryset(self, filters):
#         """
#         Optimized Calls queryset
#         """
#         queryset = CallReport.objects.select_related('ghl_credential').filter(
#             ghl_credential__is_approved=True
#         )

#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             queryset = queryset.filter(
#                 date_added__gte=date_range['start'],
#                 date_added__lte=date_range['end']
#             )

#         if filters.get('category'):
#             queryset = queryset.filter(
#                 ghl_credential__category_id=filters['category']
#             )

#         if filters.get('company_id'):
#             queryset = queryset.filter(
#                 ghl_credential__company_id=filters['company_id']
#             )

#         return queryset

#     def get_account_view_data(self, filters):
#         """
#         OPTIMIZED: Single aggregated query approach for better performance
#         """
#         # Get all location data with rates in one query
#         location_queryset = GHLAuthCredentials.objects.filter(is_approved=True)
        
#         if filters.get('category'):
#             location_queryset = location_queryset.filter(category_id=filters['category'])
#         if filters.get('company_id'):
#             location_queryset = location_queryset.filter(company_id=filters['company_id'])


#         if filters.get('search'):
#             search_term = filters['search']
#             location_queryset = location_queryset.filter(
#                 Q(location_name__icontains=search_term) |
#                 Q(location_id__icontains=search_term) |
#                 Q(company_name__icontains=search_term)
#             )
            
#         # Prefetch location data with rates
#         location_data = {
#             loc['location_id']: loc for loc in location_queryset.values(
#                 'location_id', 'location_name', 'company_name', 
#                 'inbound_rate', 'outbound_rate',
#                 'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio'
#             )
#         }
        
#         if not location_data:
#             return []

#         location_ids = list(location_data.keys())
        
#         # OPTIMIZATION 1: Get conversations for these locations first
#         conversation_filters = Q(location__location_id__in=location_ids, location__is_approved=True)
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             conversation_filters &= Q(messages__date_added__gte=date_range['start'], messages__date_added__lte=date_range['end'])
        
#         # Get SMS stats with proper joins
#         sms_stats = TextMessage.objects.select_related('conversation__location').filter(
#             conversation__location__location_id__in=location_ids,
#             conversation__location__is_approved=True,
#             **({'date_added__gte': filters['date_range']['start'], 'date_added__lte': filters['date_range']['end']} if filters.get('date_range') else {})
#         ).values(
#             'conversation__location__location_id'
#         ).annotate(
#             total_inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
#             total_outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
#             total_inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#             total_outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#         )
        
#         # OPTIMIZATION 2: Single aggregated Call query using location_id field directly
#         call_filters = Q(location_id__in=location_ids)
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             call_filters &= Q(date_added__gte=date_range['start'], date_added__lte=date_range['end'])
        
#         call_stats = CallReport.objects.filter(call_filters).values(
#             'location_id'
#         ).annotate(
#             total_inbound_call_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
#             total_outbound_call_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
#             total_inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#             total_outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#         )
        
#         # Convert to dictionaries for O(1) lookup
#         sms_stats_dict = {stat['conversation__location__location_id']: stat for stat in sms_stats}
#         call_stats_dict = {stat['location_id']: stat for stat in call_stats}
        
#         # OPTIMIZATION 3: Single loop with pre-calculated values
#         results = []
#         for location_id, location_info in location_data.items():
#             sms_data = sms_stats_dict.get(location_id, {
#                 'total_inbound_segments': 0, 'total_outbound_segments': 0,
#                 'total_inbound_messages': 0, 'total_outbound_messages': 0
#             })
            
#             call_data = call_stats_dict.get(location_id, {
#                 'total_inbound_call_duration': 0, 'total_outbound_call_duration': 0,
#                 'total_inbound_calls': 0, 'total_outbound_calls': 0
#             })
            
#             # Pre-calculate rates with null handling
#             sms_inbound_rate = Decimal(str(location_info.get('inbound_rate') or '0.00'))
#             sms_outbound_rate = Decimal(str(location_info.get('outbound_rate') or '0.00'))
            
#             call_inbound_rate = Decimal(str(location_info.get('inbound_call_rate') or '0.00'))
#             call_outbound_rate = Decimal(str(location_info.get('outbound_call_rate') or '0.00'))
#             call_price_ratio = Decimal(str(location_info.get('call_price_ratio') or '1.0'))
            
#             # Calculate usages
#             sms_inbound_usage = sms_inbound_rate * sms_data['total_inbound_messages']
#             sms_outbound_usage = sms_outbound_rate * sms_data['total_outbound_messages']
#             total_sms_usage = sms_inbound_usage + sms_outbound_usage
            
#             inbound_call_minutes = Decimal(str(call_data['total_inbound_call_duration'])) / Decimal('60')
#             outbound_call_minutes = Decimal(str(call_data['total_outbound_call_duration'])) / Decimal('60')
            
#             call_inbound_rate_effective = call_inbound_rate * call_price_ratio
#             call_outbound_rate_effective = call_outbound_rate * call_price_ratio
            
#             call_inbound_usage = call_inbound_rate_effective * inbound_call_minutes
#             call_outbound_usage = call_outbound_rate_effective * outbound_call_minutes
#             total_call_usage = call_inbound_usage + call_outbound_usage
            
#             total_usage = total_sms_usage + total_call_usage
            
#             results.append({
#                 'company_name': location_info.get('company_name'),
#                 'location_name': location_info.get('location_name'),
#                 'location_id': location_id,
#                 # SMS Data
#                 'total_inbound_segments': sms_data['total_inbound_segments'],
#                 'total_outbound_segments': sms_data['total_outbound_segments'],
#                 'total_inbound_messages': sms_data['total_inbound_messages'],
#                 'total_outbound_messages': sms_data['total_outbound_messages'],
#                 'sms_inbound_usage': sms_inbound_usage,
#                 'sms_outbound_usage': sms_outbound_usage,
#                 'sms_inbound_rate': sms_inbound_rate,
#                 'sms_outbound_rate': sms_outbound_rate,
#                 'total_sms_usage': total_sms_usage,
#                 # Call Data
#                 'total_inbound_calls': call_data['total_inbound_calls'],
#                 'total_outbound_calls': call_data['total_outbound_calls'],
#                 'total_inbound_call_duration': call_data['total_inbound_call_duration'],
#                 'total_outbound_call_duration': call_data['total_outbound_call_duration'],
#                 'inbound_call_minutes': inbound_call_minutes,
#                 'outbound_call_minutes': outbound_call_minutes,
#                 'call_inbound_usage': call_inbound_usage,
#                 'call_outbound_usage': call_outbound_usage,
#                 'call_inbound_rate': call_inbound_rate,
#                 'call_outbound_rate': call_outbound_rate,
#                 'total_call_usage': total_call_usage,
#                 # Combined Totals
#                 'total_inbound_usage': sms_inbound_usage + call_inbound_usage,
#                 'total_outbound_usage': sms_outbound_usage + call_outbound_usage,
#                 'total_usage': total_usage,
#             })
        
#         # Sort by company_name, location_name
#         return sorted(results, key=lambda x: (x['company_name'] or '', x['location_name'] or ''))

#     def get_company_view_data(self, filters):
#         """
#         OPTIMIZED: Company-level analytics with reduced database queries
#         """
#         # Get company filter
#         company_filter = Q()
#         if filters.get('category'):
#             company_filter &= Q(category_id=filters['category'])
#         if filters.get('company_id'):
#             company_filter &= Q(company_id=filters['company_id'])
        
#         # OPTIMIZATION 1: Get all company data in one query
#         company_data = {}
#         location_rates = GHLAuthCredentials.objects.filter(
#             company_filter & Q(is_approved=True)
#         ).values(
#             'company_id', 'company_name', 'location_id',
#             'inbound_rate', 'outbound_rate',
#             'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio'
#         )
        
#         for item in location_rates:
#             company_id = item['company_id']
#             if company_id not in company_data:
#                 company_data[company_id] = {
#                     'company_name': item['company_name'],
#                     'locations': [],
#                     'location_count': 0
#                 }
#             company_data[company_id]['locations'].append(item)
#             company_data[company_id]['location_count'] += 1
        
#         if not company_data:
#             return []
        
#         company_ids = list(company_data.keys())
        
#         # OPTIMIZATION 2: Aggregated SMS query by company
#         sms_filters = Q(conversation__location__company_id__in=company_ids)
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             sms_filters &= Q(date_added__gte=date_range['start'], date_added__lte=date_range['end'])
        
#         sms_company_stats = TextMessage.objects.filter(sms_filters).values(
#             'conversation__location__company_id',
#             'conversation__location__location_id',
#             'direction'
#         ).annotate(
#             message_count=Count('id'),
#             segment_count=Sum('segments')
#         )
        
#         # OPTIMIZATION 3: Aggregated Call query by company
#         call_filters = Q(location_id__in=[loc['location_id'] for company_info in company_data.values() for loc in company_info['locations']])
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             call_filters &= Q(date_added__gte=date_range['start'], date_added__lte=date_range['end'])
        
#         call_company_stats = CallReport.objects.filter(call_filters).values(
#             'location_id', 
#             'direction'
#         ).annotate(
#             call_count=Count('id'),
#             call_duration=Sum('duration')
#         )
        
#         # OPTIMIZATION 4: Process data in memory instead of multiple DB queries
#         results = []
#         for company_id, company_info in company_data.items():
#             # Initialize counters
#             totals = {
#                 'sms': {'inbound_messages': 0, 'outbound_messages': 0, 'inbound_segments': 0, 'outbound_segments': 0},
#                 'calls': {'inbound_calls': 0, 'outbound_calls': 0, 'inbound_duration': 0, 'outbound_duration': 0},
#                 'usage': {'sms_inbound': Decimal('0'), 'sms_outbound': Decimal('0'), 'call_inbound': Decimal('0'), 'call_outbound': Decimal('0')}
#             }
            
#             # Create location lookup for rates
#             location_rates_dict = {loc['location_id']: loc for loc in company_info['locations']}
            
#             # Process SMS data
#             for sms_stat in sms_company_stats:                
#                 if sms_stat['conversation__location__company_id'] == company_id:
#                     location_id = sms_stat['conversation__location__location_id']
#                     direction = sms_stat['direction']
                    
#                     if direction == 'inbound':
#                         totals['sms']['inbound_messages'] += sms_stat['message_count']
#                         totals['sms']['inbound_segments'] += sms_stat['segment_count'] or 0
                        
#                         # Calculate usage
#                         rate = Decimal(str(location_rates_dict.get(location_id, {}).get('inbound_rate') or '0.00'))
#                         totals['usage']['sms_inbound'] += rate * sms_stat['message_count']
#                     else:
#                         totals['sms']['outbound_messages'] += sms_stat['message_count']
#                         totals['sms']['outbound_segments'] += sms_stat['segment_count'] or 0
                        
#                         # Calculate usage
#                         rate = Decimal(str(location_rates_dict.get(location_id, {}).get('outbound_rate') or '0.00'))
#                         totals['usage']['sms_outbound'] += rate * sms_stat['message_count']
            
#             # Process Call data
#             for call_stat in call_company_stats:
#                 # Find which company this location belongs to
#                 for comp_id, comp_info in company_data.items():
#                     location_ids_in_company = [loc['location_id'] for loc in comp_info['locations']]
#                     if call_stat['location_id'] in location_ids_in_company and comp_id == company_id:
#                         location_id = call_stat['location_id']
#                         direction = call_stat['direction']
#                         duration_minutes = Decimal(str(call_stat['call_duration'] or 0)) / Decimal('60')
                        
#                         location_rates = location_rates_dict.get(location_id, {})
#                         call_price_ratio = Decimal(str(location_rates.get('call_price_ratio') or '1.0'))
                        
#                         if direction == 'inbound':
#                             totals['calls']['inbound_calls'] += call_stat['call_count']
#                             totals['calls']['inbound_duration'] += call_stat['call_duration'] or 0
                            
#                             # Calculate usage
#                             rate = Decimal(str(location_rates.get('inbound_call_rate') or '0.00'))
#                             totals['usage']['call_inbound'] += (rate * call_price_ratio) * duration_minutes
#                         else:
#                             totals['calls']['outbound_calls'] += call_stat['call_count']
#                             totals['calls']['outbound_duration'] += call_stat['call_duration'] or 0
                            
#                             # Calculate usage
#                             rate = Decimal(str(location_rates.get('outbound_call_rate') or '0.00'))
#                             totals['usage']['call_outbound'] += (rate * call_price_ratio) * duration_minutes
#                         break
            
#             # Calculate final totals
#             total_inbound_usage = totals['usage']['sms_inbound'] + totals['usage']['call_inbound']
#             total_outbound_usage = totals['usage']['sms_outbound'] + totals['usage']['call_outbound']
#             total_usage = total_inbound_usage + total_outbound_usage
            
#             results.append({
#                 'company_name': company_info['company_name'],
#                 'company_id': company_id,
#                 # SMS Data
#                 'total_inbound_segments': totals['sms']['inbound_segments'],
#                 'total_outbound_segments': totals['sms']['outbound_segments'],
#                 'total_inbound_messages': totals['sms']['inbound_messages'],
#                 'total_outbound_messages': totals['sms']['outbound_messages'],
#                 'sms_inbound_usage': totals['usage']['sms_inbound'],
#                 'sms_outbound_usage': totals['usage']['sms_outbound'],
#                 # Call Data
#                 'total_inbound_calls': totals['calls']['inbound_calls'],
#                 'total_outbound_calls': totals['calls']['outbound_calls'],
#                 'total_inbound_call_duration': totals['calls']['inbound_duration'],
#                 'total_outbound_call_duration': totals['calls']['outbound_duration'],
#                 'total_inbound_call_minutes': Decimal(str(totals['calls']['inbound_duration'])) / Decimal('60'),
#                 'total_outbound_call_minutes': Decimal(str(totals['calls']['outbound_duration'])) / Decimal('60'),
#                 'call_inbound_usage': totals['usage']['call_inbound'],
#                 'call_outbound_usage': totals['usage']['call_outbound'],
#                 # Combined Totals
#                 'total_inbound_usage': total_inbound_usage,
#                 'total_outbound_usage': total_outbound_usage,
#                 'total_usage': total_usage,
#                 'locations_count': company_info['location_count'],
#             })
        
#         return sorted(results, key=lambda x: x['company_name'] or '')

#     def _build_optimized_sms_queryset(self, filters, view_type):
#         """Optimized SMS queryset builder with proper indexing"""
#         base_filter = Q(conversation__location__is_approved=True)
        
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             base_filter &= Q(date_added__gte=date_range['start'], date_added__lte=date_range['end'])
        
#         category_id = filters.get("category_id")
#         if category_id:
#             base_filter &= Q(conversation__location__category__id=category_id)
        
#         if view_type == 'account' and filters.get('location_ids'):
#             base_filter &= Q(conversation__location__location_id__in=filters['location_ids'])
#         elif view_type == 'company' and filters.get('company_ids'):
#             base_filter &= Q(conversation__location__company_id__in=filters['company_ids'])
        
#         return TextMessage.objects.select_related('conversation__location').filter(base_filter)

#     def _build_optimized_calls_queryset(self, filters, view_type):
#         """Optimized calls queryset builder with proper indexing"""
#         base_filter = Q(ghl_credential__is_approved=True)
        
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             base_filter &= Q(date_added__gte=date_range['start'], date_added__lte=date_range['end'])
        
#         category_id = filters.get("category_id")
#         if category_id:
#             base_filter &= Q(ghl_credential__category_id=category_id)
        
#         if view_type == 'account' and filters.get('location_ids'):
#             base_filter &= Q(location_id__in=filters['location_ids'])
#         elif view_type == 'company' and filters.get('company_ids'):
#             base_filter &= Q(ghl_credential__company_id__in=filters['company_ids'])
        
#         return CallReport.objects.select_related('ghl_credential').filter(base_filter)

#     # Keep the rest of your methods (get_usage_analytics, etc.) but update them to use 
#     # the optimized methods above

#     @action(detail=False, methods=['post'], url_path='usage-analytics')
#     def get_usage_analytics(self, request):
#         """
#         Optimized usage analytics endpoint
#         """
#         request_serializer = AnalyticsRequestSerializer(data=request.data)
#         if not request_serializer.is_valid():
#             return Response(request_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#         validated_data = request_serializer.validated_data
#         view_type = validated_data.get('view_type', 'account')
#         filters = {
#             'date_range': validated_data.get('date_range'),
#             'category': validated_data.get('category'),
#             'company_id': validated_data.get('company_id'),
#             'search': validated_data.get('search'),
#         }

#         try:
#             # Use optimized methods
#             if view_type == 'account':
#                 data = self.get_account_view_data(filters)
#             else:
#                 data = self.get_company_view_data(filters)
            
#             serializer_class = AccountViewWithCallsSerializer if view_type == 'account' else CompanyViewWithCallsSerializer
            
#             request.custom_metadata = {
#                 'view_type': view_type,
#                 'filters_applied': {k: v for k, v in filters.items() if v is not None},
#                 'total_results_count': len(data),
#                 'cached': False,
#                 'optimized': True
#             }
            
#             page = self.paginate_queryset(data)
#             if page is not None:
#                 serializer = serializer_class(page, many=True)
#                 return self.get_paginated_response(serializer.data)
#             else:
#                 serializer = serializer_class(data, many=True)
#                 return Response({
#                     'view_type': view_type,
#                     'filters_applied': {k: v for k, v in filters.items() if v is not None},
#                     'results_count': len(data),
#                     'cached': False,
#                     'optimized': True,
#                     'data': serializer.data
#                 }, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to fetch analytics data: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     def _get_real_time_data(self, view_type, filters):
#         """Helper method to get real-time data (original logic)"""
#         if view_type == 'account':
#             return self.get_account_view_data(filters)
#         else:
#             return self.get_company_view_data(filters)
    
#     def _apply_additional_filters(self, data, filters):
#         """Apply additional filters to cached data"""
#         # Implement filtering logic based on your data structure
#         # This is a placeholder - adjust based on your actual data format
#         filtered_data = data
        
#         if filters.get('category'):
#             # Filter by category if your data includes category info
#             # Example: filtered_data = [item for item in data if item.get('category_id') == filters['category']]
#             pass
        
#         if filters.get('company_id'):
#             # Filter by company_id if your data includes company info
#             # Example: filtered_data = [item for item in data if item.get('company_id') == filters['company_id']]
#             pass
        
#         return filtered_data

#     @action(detail=False, methods=['get'], url_path='usage-summary')
#     def get_usage_summary(self, request):
#         """
#         Get overall usage summary statistics including SMS and Calls
#         Now uses cached data for faster responses
#         """
#         try:
#             cached_entry = AnalyticsCache.objects.filter(
#                 cache_type='usage_summary',
#                 is_active=True
#             ).order_by('-created_at').first()
            
#             if cached_entry:
#                 cached_data = cached_entry.cached_data
#                 return Response({
#                     'sms_summary': cached_data.get('sms_summary', {}),
#                     'call_summary': cached_data.get('call_summary', {}),
#                     'cached': True,
#                     'cache_generated_at': cached_entry.created_at.isoformat()
#                 }, status=status.HTTP_200_OK)
            
#             else:
#                 sms_stats = TextMessage.objects.aggregate(
#                     total_messages=Coalesce(Count('id'), 0),
#                     total_segments=Coalesce(Sum('segments'), 0),
#                     total_inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                     total_outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                     total_inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
#                     total_outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
#                 )

#                 call_stats = CallReport.objects.aggregate(
#                     total_calls=Coalesce(Count('id'), 0),
#                     total_call_duration=Coalesce(Sum('duration'), 0),
#                     total_inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                     total_outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                     total_inbound_call_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
#                     total_outbound_call_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
#                 )
                
#                 # Trigger cache generation for next time
#                 generate_analytics_cache.delay(['usage_summary'])
                
#                 return Response({
#                     'sms_summary': sms_stats,
#                     'call_summary': call_stats,
#                     'cached': False,
#                     'cache_generation_triggered': True
#                 }, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to fetch usage summary: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['post'], url_path='bar-graph-analytics')
#     def get_bar_graph_analytics(self, request):
#         """
#         Get SMS and Call analytics data formatted for bar graph visualization
#         Supports both Account View (location-based) and Company View (company-based)
#         Now uses cached data for faster responses
#         """
#         # Validate request payload
#         request_serializer = BarGraphAnalyticsRequestSerializer(data=request.data)
#         if not request_serializer.is_valid():
#             return Response(
#                 request_serializer.errors,
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         validated_data = request_serializer.validated_data
#         date_range = validated_data.get('date_range')
#         location_ids = validated_data.get('location_ids', [])
#         company_ids = validated_data.get('company_ids', [])  # Add company_ids support
#         graph_type = validated_data.get('graph_type', 'daily')  # daily, weekly, monthly
#         data_type = validated_data.get('data_type', 'both')  # sms, call, both
#         view_type = validated_data.get('view_type', 'account')  # account, company

#         category_id = validated_data.get('category_id',0)  # account, company
#         try:
#             cache_type = f'bar_graph_{graph_type}'
#             cached_entry = AnalyticsCache.objects.filter(
#                 cache_type=cache_type,
#                 is_active=True
#             ).order_by('-created_at').first()
            
#             # Check if cache exists and if the request is for default parameters
#             if cached_entry and not date_range and not location_ids and not company_ids and not category_id:
#                 # Use cached data for default requests
#                 cached_data = cached_entry.cached_data
#                 cache_key = f"{view_type}_{data_type}"
                
#                 if cache_key in cached_data:
#                     data = cached_data[cache_key].get('data', [])
                    
#                     return Response({
#                         'view_type': view_type,
#                         'graph_type': graph_type,
#                         'data_type': data_type,
#                         'date_range': cached_data.get('date_range'), # Use cached date range for context
#                         'location_ids': location_ids if view_type == 'account' else None,
#                         'company_ids': company_ids if view_type == 'company' else None,
#                         'cached': True,
#                         'cache_generated_at': cached_entry.created_at.isoformat(),
#                         'data': data
#                     }, status=status.HTTP_200_OK)
            
#             base_filters = {}
#             if category_id:
#                 base_filters["category_id"] = category_id
#             if date_range:
#                 base_filters['date_range'] = date_range
#             if view_type == 'account' and location_ids:
#                 base_filters['location_ids'] = location_ids
#             elif view_type == 'company' and company_ids:
#                 base_filters['company_ids'] = company_ids

#             # Get time-series data based on graph type
#             if graph_type == 'daily':
#                 data = self._get_daily_analytics(base_filters, data_type, view_type)
#             elif graph_type == 'weekly':
#                 data = self._get_weekly_analytics(base_filters, data_type, view_type)
#             elif graph_type == 'monthly':
#                 data = self._get_monthly_analytics(base_filters, data_type, view_type)
#             else:
#                 return Response(
#                     {'error': 'Invalid graph_type. Must be daily, weekly, or monthly'},
#                     status=status.HTTP_400_BAD_REQUEST
#                 )
            
#             # Trigger cache generation if using default parameters
#             if not date_range and not location_ids and not company_ids and not category_id:
#                 generate_analytics_cache.delay([cache_type])

#             return Response({
#                 'view_type': view_type,
#                 'graph_type': graph_type,
#                 'data_type': data_type,
#                 'date_range': date_range,
#                 'location_ids': location_ids if view_type == 'account' else None,
#                 'company_ids': company_ids if view_type == 'company' else None,
#                 'cached': False,
#                 'data': data
#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             import traceback
#             traceback.print_exc()
#             return Response(
#                 {'error': f'Failed to fetch bar graph analytics: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['post'], url_path='refresh-cache')
#     def refresh_cache(self, request):
#         """
#         Manually trigger cache refresh for all or specific cache types
#         """
#         cache_types = request.data.get('cache_types', None)
        
#         try:
#             result = generate_analytics_cache.delay(cache_types)
#             return Response({
#                 'message': 'Cache refresh triggered successfully',
#                 'task_id': result.id,
#                 'cache_types': cache_types or 'all'
#             }, status=status.HTTP_200_OK)
#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to trigger cache refresh: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['get'], url_path='cache-status')
#     def get_cache_status(self, request):
#         """
#         Get status of all cached data
#         """
#         try:
#             cache_entries = AnalyticsCache.objects.filter(is_active=True).order_by('cache_type', '-created_at')
#             recent_logs = AnalyticsCacheLog.objects.all()[:10]
            
#             cache_status = {}
#             for entry in cache_entries:
#                 if entry.cache_type not in cache_status:
#                     cache_status[entry.cache_type] = {
#                         'last_updated': entry.created_at.isoformat(),
#                         'computation_time': entry.computation_time_seconds,
#                         'record_count': entry.record_count,
#                         'age_hours': (timezone.now() - entry.created_at).total_seconds() / 3600
#                     }
            
#             logs_data = [{
#                 'cache_type': log.cache_type,
#                 'status': log.status,
#                 'started_at': log.started_at.isoformat(),
#                 'duration': log.duration_seconds,
#                 'records_processed': log.records_processed,
#                 'error': log.error_message
#             } for log in recent_logs]
            
#             return Response({
#                 'cache_status': cache_status,
#                 'recent_logs': logs_data
#             }, status=status.HTTP_200_OK)
            
#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to get cache status: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     def _get_daily_analytics(self, filters, data_type, view_type):
#         """Get daily analytics data for both account and company views"""
#         date_range = filters.get('date_range')
#         location_ids = filters.get('location_ids', [])
#         company_ids = filters.get('company_ids', [])

        
#         # Determine truncation function and date format
#         trunc_func = TruncDay('date_added')
#         date_format = '%Y-%m-%d'
        
#         data = []
        
#         if data_type in ['sms', 'both']:
#             # Get SMS data
#             sms_queryset = self._build_sms_queryset(filters, view_type)
#             sms_data = sms_queryset.annotate(
#                 period=trunc_func
#             ).values('period').annotate(
#                 total_messages=Coalesce(Count('id'), 0),
#                 total_segments=Coalesce(Sum('segments'), 0),
#                 inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                 outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                 inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
#                 outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
#             ).order_by('period')
            
#             # Calculate usage for SMS
#             if view_type == 'account':
#                 sms_usage_data = self._calculate_period_usage(sms_data, 'sms', location_ids, view_type)
#             else:  # company
#                 sms_usage_data = self._calculate_period_usage(sms_data, 'sms', company_ids, view_type)
            
#             if data_type == 'sms':
#                 data = sms_usage_data
#             else:
#                 data = sms_usage_data
        
#         if data_type in ['call', 'both']:
#             # Get Call data
#             calls_queryset = self._build_calls_queryset(filters, view_type)
#             call_data = calls_queryset.annotate(
#                 period=trunc_func
#             ).values('period').annotate(
#                 total_calls=Coalesce(Count('id'), 0),
#                 total_duration=Coalesce(Sum('duration'), 0),
#                 inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                 outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                 inbound_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
#                 outbound_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
#             ).order_by('period')
            
#             # Calculate usage for calls
#             if view_type == 'account':
#                 call_usage_data = self._calculate_period_usage(call_data, 'call', location_ids, view_type)
#             else:  # company
#                 call_usage_data = self._calculate_period_usage(call_data, 'call', company_ids, view_type)
            
#             if data_type == 'call':
#                 data = call_usage_data
#             elif data_type == 'both':
#                 # Merge SMS and Call data
#                 data = self._merge_sms_call_data(data, call_usage_data)
        
#         return self._fill_missing_periods(data, filters.get('date_range'), 'daily')

#     def _get_weekly_analytics(self, filters, data_type, view_type):
#         """Get weekly analytics data for both account and company views"""
#         trunc_func = TruncWeek('date_added')
        
#         data = []
        
#         if data_type in ['sms', 'both']:
#             sms_queryset = self._build_sms_queryset(filters, view_type)
#             sms_data = sms_queryset.annotate(
#                 period=trunc_func
#             ).values('period').annotate(
#                 total_messages=Coalesce(Count('id'), 0),
#                 total_segments=Coalesce(Sum('segments'), 0),
#                 inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                 outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                 inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
#                 outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
#             ).order_by('period')
            
#             filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
#             sms_usage_data = self._calculate_period_usage(sms_data, 'sms', filter_ids, view_type)
            
#             if data_type == 'sms':
#                 data = sms_usage_data
#             else:
#                 data = sms_usage_data
        
#         if data_type in ['call', 'both']:
#             calls_queryset = self._build_calls_queryset(filters, view_type)
#             call_data = calls_queryset.annotate(
#                 period=trunc_func
#             ).values('period').annotate(
#                 total_calls=Coalesce(Count('id'), 0),
#                 total_duration=Coalesce(Sum('duration'), 0),
#                 inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                 outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                 inbound_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
#                 outbound_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
#             ).order_by('period')
            
#             filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
#             call_usage_data = self._calculate_period_usage(call_data, 'call', filter_ids, view_type)
            
#             if data_type == 'call':
#                 data = call_usage_data
#             elif data_type == 'both':
#                 data = self._merge_sms_call_data(data, call_usage_data)
        
#         return self._fill_missing_periods(data, filters.get('date_range'), 'weekly')


#     def _get_monthly_analytics(self, filters, data_type, view_type):
#         """Get monthly analytics data for both account and company views"""
#         trunc_func = TruncMonth('date_added')
        
#         data = []
        
#         if data_type in ['sms', 'both']:
#             sms_queryset = self._build_sms_queryset(filters, view_type)
#             sms_data = sms_queryset.annotate(
#                 period=trunc_func
#             ).values('period').annotate(
#                 total_messages=Coalesce(Count('id'), 0),
#                 total_segments=Coalesce(Sum('segments'), 0),
#                 inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                 outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                 inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
#                 outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
#             ).order_by('period')
            
#             filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
#             sms_usage_data = self._calculate_period_usage(sms_data, 'sms', filter_ids, view_type)
            
#             if data_type == 'sms':
#                 data = sms_usage_data
#             else:
#                 data = sms_usage_data
        
#         if data_type in ['call', 'both']:
#             calls_queryset = self._build_calls_queryset(filters, view_type)
#             call_data = calls_queryset.annotate(
#                 period=trunc_func
#             ).values('period').annotate(
#                 total_calls=Coalesce(Count('id'), 0),
#                 total_duration=Coalesce(Sum('duration'), 0),
#                 inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
#                 outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
#                 inbound_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
#                 outbound_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
#             ).order_by('period')
            
#             filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
#             call_usage_data = self._calculate_period_usage(call_data, 'call', filter_ids, view_type)
            
#             if data_type == 'call':
#                 data = call_usage_data
#             elif data_type == 'both':
#                 data = self._merge_sms_call_data(data, call_usage_data)
        
#         return self._fill_missing_periods(data, filters.get('date_range'), 'monthly')

#     def _build_sms_queryset(self, filters, view_type):
#         """Build SMS queryset with filters for both account and company views"""
#         queryset = TextMessage.objects.select_related('conversation__location').filter(
#             conversation__location__is_approved=True
#         )

#         category_id = filters.get("category_id")
#         if category_id:
#             queryset = queryset.filter(conversation__location__category__id=category_id)
        
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             queryset = queryset.filter(
#                 date_added__gte=date_range['start'],
#                 date_added__lte=date_range['end']
#             )
        
#         if view_type == 'account' and filters.get('location_ids'):
#             queryset = queryset.filter(
#                 conversation__location__location_id__in=filters['location_ids']
#             )
#         elif view_type == 'company' and filters.get('company_ids'):
#             queryset = queryset.filter(
#                 conversation__location__company_id__in=filters['company_ids']
#             )
        
#         return queryset

#     def _build_calls_queryset(self, filters, view_type):
#         """Build calls queryset with filters for both account and company views"""
#         queryset = CallReport.objects.select_related('ghl_credential').filter(
#             ghl_credential__is_approved=True
#         )

#         category_id = filters.get("category_id")
#         if category_id:
#             # This filter seems incorrect as it references conversation.location.category__id
#             # but the queryset is for CallReport which relates to ghl_credential.
#             # Assuming it should filter based on ghl_credential's category.
#             queryset = queryset.filter(ghl_credential__category_id=category_id)
        
#         if filters.get('date_range'):
#             date_range = filters['date_range']
#             queryset = queryset.filter(
#                 date_added__gte=date_range['start'],
#                 date_added__lte=date_range['end']
#             )
        
#         if view_type == 'account' and filters.get('location_ids'):
#             queryset = queryset.filter(
#                 ghl_credential__location_id__in=filters['location_ids']
#             )
#         elif view_type == 'company' and filters.get('company_ids'):
#             queryset = queryset.filter(
#                 ghl_credential__company_id__in=filters['company_ids']
#             )
        
#         return queryset

#     def _calculate_period_usage(self, period_data, data_type, filter_ids, view_type):
#         """Calculate usage costs for each period supporting both account and company views"""
#         # Get location rates based on view type
#         if view_type == 'account':
#             # For account view, filter by location_ids
#             if data_type == 'sms':
#                 location_rates = GHLAuthCredentials.objects.filter(
#                     location_id__in=filter_ids if filter_ids else []
#                 ).values('location_id', 'inbound_rate', 'outbound_rate')
#             else:  # call
#                 location_rates = GHLAuthCredentials.objects.filter(
#                     location_id__in=filter_ids if filter_ids else []
#                 ).values('location_id', 'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio')
#         else:  # company view
#             # For company view, filter by company_ids
#             if data_type == 'sms':
#                 location_rates = GHLAuthCredentials.objects.filter(
#                     company_id__in=filter_ids if filter_ids else []
#                 ).values('location_id', 'inbound_rate', 'outbound_rate')
#             else:  # call
#                 location_rates = GHLAuthCredentials.objects.filter(
#                     company_id__in=filter_ids if filter_ids else []
#                 ).values('location_id', 'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio')
        
#         # Create rates dictionary
#         rates_dict = {}
#         for rate in location_rates:
#             location_id = rate['location_id']
#             if data_type == 'sms':
#                 rates_dict[location_id] = {
#                     'inbound_rate': rate['inbound_rate'] or Decimal('0.00'),
#                     'outbound_rate': rate['outbound_rate'] or Decimal('0.00')
#                 }
#             else:  # call
#                 call_price_ratio = rate['call_price_ratio'] or Decimal('1.0')
#                 rates_dict[location_id] = {
#                     'inbound_rate': (rate['inbound_call_rate'] or Decimal('0.00')) * call_price_ratio,
#                     'outbound_rate': (rate['outbound_call_rate'] or Decimal('0.00')) * call_price_ratio
#                 }
        
#         # Calculate average rates if multiple locations
#         if rates_dict:
#             avg_inbound_rate = sum(r['inbound_rate'] for r in rates_dict.values()) / len(rates_dict)
#             avg_outbound_rate = sum(r['outbound_rate'] for r in rates_dict.values()) / len(rates_dict)
#         else:
#             avg_inbound_rate = avg_outbound_rate = Decimal('0.00')
        
#         result = []
#         for item in period_data:
#             period_str = item['period'].strftime('%Y-%m-%d')
            
#             if data_type == 'sms':
#                 inbound_usage = avg_inbound_rate * item['inbound_messages']
#                 outbound_usage = avg_outbound_rate * item['outbound_messages']
                
#                 result.append({
#                     'period': period_str,
#                     'period_date': item['period'],
#                     'sms_data': {
#                         'total_messages': item['total_messages'],
#                         'total_segments': item['total_segments'],
#                         'inbound_messages': item['inbound_messages'],
#                         'outbound_messages': item['outbound_messages'],
#                         'inbound_segments': item['inbound_segments'],
#                         'outbound_segments': item['outbound_segments'],
#                         'inbound_usage': float(inbound_usage),
#                         'outbound_usage': float(outbound_usage),
#                         'total_usage': float(inbound_usage + outbound_usage)
#                     }
#                 })
#             else:  # call
#                 # Convert duration to minutes
#                 inbound_minutes = Decimal(str(item['inbound_duration'])) / Decimal('60')
#                 outbound_minutes = Decimal(str(item['outbound_duration'])) / Decimal('60')
                
#                 inbound_usage = avg_inbound_rate * inbound_minutes
#                 outbound_usage = avg_outbound_rate * outbound_minutes
                
#                 result.append({
#                     'period': period_str,
#                     'period_date': item['period'],
#                     'call_data': {
#                         'total_calls': item['total_calls'],
#                         'total_duration': item['total_duration'],
#                         'inbound_calls': item['inbound_calls'],
#                         'outbound_calls': item['outbound_calls'],
#                         'inbound_duration': item['inbound_duration'],
#                         'outbound_duration': item['outbound_duration'],
#                         'inbound_minutes': float(inbound_minutes),
#                         'outbound_minutes': float(outbound_minutes),
#                         'inbound_usage': float(inbound_usage),
#                         'outbound_usage': float(outbound_usage),
#                         'total_usage': float(inbound_usage + outbound_usage)
#                     }
#                 })
        
#         return result

#     def _merge_sms_call_data(self, sms_data, call_data):
#         """Merge SMS and call data for combined view"""
#         # Create dictionaries for quick lookup
#         sms_dict = {item['period']: item for item in sms_data}
#         call_dict = {item['period']: item for item in call_data}
        
#         # Get all unique periods
#         all_periods = set(sms_dict.keys()) | set(call_dict.keys())
        
#         merged_data = []
#         for period in sorted(all_periods):
#             sms_item = sms_dict.get(period, {})
#             call_item = call_dict.get(period, {})
            
#             # Get period_date from either SMS or call data
#             period_date = sms_item.get('period_date') or call_item.get('period_date')
            
#             merged_item = {
#                 'period': period,
#                 'period_date': period_date,
#             }
            
#             # Add SMS data if available
#             if 'sms_data' in sms_item:
#                 merged_item['sms_data'] = sms_item['sms_data']
#             else:
#                 merged_item['sms_data'] = {
#                     'total_messages': 0,
#                     'total_segments': 0,
#                     'inbound_messages': 0,
#                     'outbound_messages': 0,
#                     'inbound_segments': 0,
#                     'outbound_segments': 0,
#                     'inbound_usage': 0.0,
#                     'outbound_usage': 0.0,
#                     'total_usage': 0.0
#                 }
            
#             # Add call data if available
#             if 'call_data' in call_item:
#                 merged_item['call_data'] = call_item['call_data']
#             else:
#                 merged_item['call_data'] = {
#                     'total_calls': 0,
#                     'total_duration': 0,
#                     'inbound_calls': 0,
#                     'outbound_calls': 0,
#                     'inbound_duration': 0,
#                     'outbound_duration': 0,
#                     'inbound_minutes': 0.0,
#                     'outbound_minutes': 0.0,
#                     'inbound_usage': 0.0,
#                     'outbound_usage': 0.0,
#                     'total_usage': 0.0
#                 }
            
#             # Add combined usage
#             merged_item['combined_usage'] = {
#                 'total_inbound_usage': merged_item['sms_data']['inbound_usage'] + merged_item['call_data']['inbound_usage'],
#                 'total_outbound_usage': merged_item['sms_data']['outbound_usage'] + merged_item['call_data']['outbound_usage'],
#                 'total_usage': merged_item['sms_data']['total_usage'] + merged_item['call_data']['total_usage']
#             }
            
#             merged_data.append(merged_item)
        
#         return merged_data

#     def _fill_missing_periods(self, data, date_range, period_type):
#         """Fill missing periods with zero values"""
#         if not date_range or not data:
#             return data
        
#         start_date = date_range['start']
#         end_date = date_range['end']
        
#         # Create a set of existing periods
#         existing_periods = {item['period'] for item in data}
        
#         # Generate all periods in the range
#         all_periods = []
#         current_date = start_date
        
#         while current_date <= end_date:
#             if period_type == 'daily':
#                 period_str = current_date.strftime('%Y-%m-%d')
#                 next_date = current_date + timedelta(days=1)
#             elif period_type == 'weekly':
#                 # Get start of week (Monday)
#                 start_of_week = current_date - timedelta(days=current_date.weekday())
#                 period_str = start_of_week.strftime('%Y-%m-%d')
#                 next_date = start_of_week + timedelta(weeks=1)
#                 current_date = next_date
#             else:  # monthly
#                 period_str = current_date.strftime('%Y-%m-%d')
#                 next_date = current_date + relativedelta(months=1)
            
#             if period_str not in existing_periods:
#                 # Create empty period data
#                 empty_period = {
#                     'period': period_str,
#                     'period_date': current_date,
#                 }
                
#                 # Add appropriate empty data structure
#                 if any('sms_data' in item for item in data):
#                     empty_period['sms_data'] = {
#                         'total_messages': 0,
#                         'total_segments': 0,
#                         'inbound_messages': 0,
#                         'outbound_messages': 0,
#                         'inbound_segments': 0,
#                         'outbound_segments': 0,
#                         'inbound_usage': 0.0,
#                         'outbound_usage': 0.0,
#                         'total_usage': 0.0
#                     }
                
#                 if any('call_data' in item for item in data):
#                     empty_period['call_data'] = {
#                         'total_calls': 0,
#                         'total_duration': 0,
#                         'inbound_calls': 0,
#                         'outbound_calls': 0,
#                         'inbound_duration': 0,
#                         'outbound_duration': 0,
#                         'inbound_minutes': 0.0,
#                         'outbound_minutes': 0.0,
#                         'inbound_usage': 0.0,
#                         'outbound_usage': 0.0,
#                         'total_usage': 0.0
#                     }
                
#                 if any('combined_usage' in item for item in data):
#                     empty_period['combined_usage'] = {
#                         'total_inbound_usage': 0.0,
#                         'total_outbound_usage': 0.0,
#                         'total_usage': 0.0
#                     }
                
#                 all_periods.append(empty_period)
            
#             current_date = next_date
        
#         # Combine existing and empty periods, then sort
#         combined_data = data + all_periods
#         combined_data.sort(key=lambda x: x['period'])
        
#         return combined_data




# from django.db import connection



# class CustomPageNumberPagination(PageNumberPagination):
#     """
#     Custom pagination class to set page size and include additional metadata.
#     """
#     page_size = 10
#     page_size_query_param = 'page_size'
#     max_page_size = 1000

#     def get_paginated_response(self, data):
#         custom_metadata = getattr(self.request, 'custom_metadata', {})
#         return Response({
#             'count': self.page.paginator.count,
#             'next': self.get_next_link(),
#             'previous': self.get_previous_link(),
#             'view_type': custom_metadata.get('view_type'),
#             'filters_applied': custom_metadata.get('filters_applied'),
#             'graph_type': custom_metadata.get('graph_type'),
#             'data_type': custom_metadata.get('data_type'),
#             'date_range': custom_metadata.get('date_range'),
#             'location_ids': custom_metadata.get('location_ids'),
#             'company_ids': custom_metadata.get('company_ids'),
#             'total_results_count': custom_metadata.get('total_results_count'),
#             'data': data
#         })





from django.db.models import Count, Sum, Q
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from .models import AnalyticsCache, AnalyticsCacheLog
from .tasks import generate_analytics_cache
from .serializers import AnalyticsRequestSerializer, BarGraphAnalyticsRequestSerializer
from core.models import GHLTransaction, GHLAuthCredentials
from .utils import AnalyticsComputer
from dateutil.relativedelta import relativedelta


class CustomPageNumberPagination(PageNumberPagination):
    """
    Custom pagination class to set page size and include additional metadata.
    """
    page_size = 10  # Set the default page size to 15 records
    page_size_query_param = 'page_size'  # Allow client to override page size using ?page_size=X
    max_page_size = 1000  # Maximum page size allowed

    def get_paginated_response(self, data):
        """
        Overrides the default get_paginated_response to include custom metadata.
        The custom metadata (view_type, filters_applied, total_results_count, etc.)
        is expected to be set on the request object by the view.
        """
        custom_metadata = getattr(self.request, 'custom_metadata', {})

        return Response({
            'count': self.page.paginator.count,  # Total number of items across all pages
            'next': self.get_next_link(),
            'previous': self.get_previous_link(),
            # Include custom metadata from the view
            'view_type': custom_metadata.get('view_type'),
            'filters_applied': custom_metadata.get('filters_applied'),
            'graph_type': custom_metadata.get('graph_type'),
            'data_type': custom_metadata.get('data_type'),
            'date_range': custom_metadata.get('date_range'),
            'location_ids': custom_metadata.get('location_ids'),
            'company_ids': custom_metadata.get('company_ids'),
            'total_results_count': custom_metadata.get('total_results_count'), # Total count before pagination
            'cached': custom_metadata.get('cached', False),
            'cache_generated_at': custom_metadata.get('cache_generated_at'),
            'cache_generation_triggered': custom_metadata.get('cache_generation_triggered', False),
            'data': data  # The paginated list of results for the current page
        })


# class SMSAnalyticsViewSet(viewsets.GenericViewSet):
#     pagination_class = CustomPageNumberPagination

#     """
#     ViewSet for SMS and Call usage analytics with optimized queries using GHLTransaction model
#     """

#     @action(detail=False, methods=['post'], url_path='usage-analytics')
#     def get_usage_analytics(self, request):
#         """
#         Get SMS and Call usage analytics based on view type and filters
#         Now uses AnalyticsComputer with GHLTransaction model
#         """
#         # Validate request payload
#         request_serializer = AnalyticsRequestSerializer(data=request.data)
#         if not request_serializer.is_valid():
#             return Response(request_serializer.errors,
#                             status=status.HTTP_400_BAD_REQUEST)

#         validated_data = request_serializer.validated_data
#         view_type = validated_data.get('view_type', 'account')
        
#         filters = {
#             'start_date': validated_data.get('date_range', {}).get('start') if validated_data.get('date_range') else None,
#             'end_date': validated_data.get('date_range', {}).get('end') if validated_data.get('date_range') else None,
#             'category_id': validated_data.get('category'),
#             'company_id': validated_data.get('company_id'),
#             'search': validated_data.get('search'),
#         }

#         try:
#             if view_type == 'account':
#                 data = AnalyticsComputer.get_usage_analytics_data(**filters)
#             else:
#                 data = AnalyticsComputer.get_company_usage_analytics_data(**filters)
            
#             serializer_class = AccountViewWithCallsSerializer if view_type == 'account' else CompanyViewWithCallsSerializer
            
#             # Store custom metadata
#             request.custom_metadata = {
#                 'view_type': view_type,
#                 'filters_applied': {k: v for k, v in filters.items() if v is not None},
#                 'total_results_count': len(data),
#                 'cached': False,
#                 'cache_generation_triggered': False
#             }
            
#             # Apply pagination
#             page = self.paginate_queryset(data)
#             if page is not None:
#                 serializer = serializer_class(page, many=True)
#                 return self.get_paginated_response(serializer.data)
#             else:
#                 serializer = serializer_class(data, many=True)
#                 return Response({
#                     'view_type': view_type,
#                     'filters_applied': {k: v for k, v in filters.items() if v is not None},
#                     'results_count': len(data),
#                     'cached': False,
#                     'data': serializer.data
#                 }, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to fetch analytics data: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['get'], url_path='usage-summary')
#     def get_usage_summary(self, request):
#         """
#         Get overall usage summary statistics including SMS and Calls
#         Now uses AnalyticsComputer with GHLTransaction model
#         """
#         try:
#             summary_data = AnalyticsComputer.get_usage_summary_data()
            
#             return Response({
#                 'sms_summary': summary_data.get('sms_summary', {}),
#                 'call_summary': summary_data.get('call_summary', {}),
#                 'cached': False,
#                 'generated_at': summary_data.get('generated_at')
#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to fetch usage summary: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['post'], url_path='bar-graph-analytics')
#     def get_bar_graph_analytics(self, request):
#         """
#         Get SMS and Call analytics data formatted for bar graph visualization
#         Now uses AnalyticsComputer with GHLTransaction model
#         """
#         # Validate request payload
#         request_serializer = BarGraphAnalyticsRequestSerializer(data=request.data)
#         if not request_serializer.is_valid():
#             return Response(
#                 request_serializer.errors,
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         validated_data = request_serializer.validated_data
        
#         filters = {
#             'start_date': validated_data.get('date_range', {}).get('start') if validated_data.get('date_range') else None,
#             'end_date': validated_data.get('date_range', {}).get('end') if validated_data.get('date_range') else None,
#             'graph_type': validated_data.get('graph_type', 'daily'),
#             'data_type': validated_data.get('data_type', 'both'),
#             'view_type': validated_data.get('view_type', 'account'),
#             'location_ids': validated_data.get('location_ids', []),
#             'company_ids': validated_data.get('company_ids', []),
#             'category_id': validated_data.get('category_id'),
#         }

#         try:
#             data = AnalyticsComputer.get_bar_graph_analytics_data(**filters)

#             return Response({
#                 'view_type': filters['view_type'],
#                 'graph_type': filters['graph_type'],
#                 'data_type': filters['data_type'],
#                 'date_range': data.get('date_range'),
#                 'location_ids': filters['location_ids'] if filters['view_type'] == 'account' else None,
#                 'company_ids': filters['company_ids'] if filters['view_type'] == 'company' else None,
#                 'cached': False,
#                 'data': data.get('data', [])
#             }, status=status.HTTP_200_OK)

#         except Exception as e:
#             import traceback
#             traceback.print_exc()
#             return Response(
#                 {'error': f'Failed to fetch bar graph analytics: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['post'], url_path='refresh-cache')
#     def refresh_cache(self, request):
#         """
#         Manually trigger cache refresh for all or specific cache types
#         """
#         cache_types = request.data.get('cache_types', None)
        
#         try:
#             result = generate_analytics_cache.delay(cache_types)
#             return Response({
#                 'message': 'Cache refresh triggered successfully',
#                 'task_id': result.id,
#                 'cache_types': cache_types or 'all'
#             }, status=status.HTTP_200_OK)
#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to trigger cache refresh: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )

#     @action(detail=False, methods=['get'], url_path='cache-status')
#     def get_cache_status(self, request):
#         """
#         Get status of all cached data
#         """
#         try:
#             cache_entries = AnalyticsCache.objects.filter(is_active=True).order_by('cache_type', '-created_at')
#             recent_logs = AnalyticsCacheLog.objects.all()[:10]
            
#             cache_status = {}
#             for entry in cache_entries:
#                 if entry.cache_type not in cache_status:
#                     cache_status[entry.cache_type] = {
#                         'last_updated': entry.created_at.isoformat(),
#                         'computation_time': entry.computation_time_seconds,
#                         'record_count': entry.record_count,
#                         'age_hours': (timezone.now() - entry.created_at).total_seconds() / 3600
#                     }
            
#             logs_data = [{
#                 'cache_type': log.cache_type,
#                 'status': log.status,
#                 'started_at': log.started_at.isoformat(),
#                 'duration': log.duration_seconds,
#                 'records_processed': log.records_processed,
#                 'error': log.error_message
#             } for log in recent_logs]
            
#             return Response({
#                 'cache_status': cache_status,
#                 'recent_logs': logs_data
#             }, status=status.HTTP_200_OK)
            
#         except Exception as e:
#             return Response(
#                 {'error': f'Failed to get cache status: {str(e)}'},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )
        



from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django.db.models import Sum, Count, Q, F
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from collections import defaultdict
import calendar

from core.models import GHLTransaction, GHLAuthCredentials
from accounts_management_app.models import GHLWalletBalance


from django.db.models import Func, DateTimeField



class ToTimestamp(Func):
        
    function = "to_timestamp"
    template = "%(function)s(%(expressions)s, 'Mon DDth YYYY, HH12:MI:SS AM')"
    output_field = DateTimeField()

class AnalyticsPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class TransactionAnalyticsViewSet(viewsets.ViewSet):
    """
    ViewSet for handling transaction analytics endpoints
    """
    pagination_class = AnalyticsPagination

    def log(self, *args):
        """Helper logger for consistent debug prints"""
        print("[TransactionAnalytics]", *args)

    def get_paginator(self):
        """
        Return the paginator instance associated with the view, or None.
        """
        if not hasattr(self, '_paginator'):
            if self.pagination_class is None:
                self._paginator = None
            else:
                self._paginator = self.pagination_class()
        return self._paginator

    def paginate_queryset(self, data):
        """
        Return a single page of results, or None if pagination is disabled.
        """
        paginator = self.get_paginator()
        if paginator is None:
            return None
        return paginator.paginate_queryset(data, self.request, view=self)

    def get_paginated_response(self, data, extra_data=None):
        """
        Return a paginated style `Response` object for the given output data.
        """
        paginator = self.get_paginator()
        if paginator is None:
            response_data = extra_data or {}
            response_data['data'] = data
            return Response(response_data)
        
        paginated_data = paginator.get_paginated_response(data).data
        if extra_data:
            paginated_data.update(extra_data)
        return Response(paginated_data)

    def parse_date_range(self, date_range):
        """Parse and validate date range from request data"""
        self.log("Raw date_range from request:", date_range)

        if not date_range:
            raise ValueError("date_range is required")
        
        start_date = parse_date(date_range.get('start'))
        end_date = parse_date(date_range.get('end'))
        self.log("Parsed start_date:", start_date, "end_date:", end_date)
        
        if not start_date or not end_date:
            raise ValueError("Invalid date format. Use YYYY-MM-DD")
        
        # Convert to datetime with time components
        start_datetime = datetime.combine(start_date, datetime.min.time())
        end_datetime = datetime.combine(end_date, datetime.max.time())
        
        self.log("Final datetime range:", start_datetime, "to", end_datetime)
        return start_datetime, end_datetime

    def get_base_queryset(self, start_datetime, end_datetime):
        """Get base queryset filtered by date range and transaction types"""
        qs = GHLTransaction.objects.filter(
            parsed_date__range=[start_datetime, end_datetime],
            transaction_type__in=['sms_inbound', 'sms_outbound', 'call_inbound', 'call_outbound']
        ).select_related('ghl_credential')

        self.log("Base queryset count:", qs.count())
        return qs


    
    

    @action(detail=False, methods=['post'], url_path='usage-analytics')
    def usage_analytics(self, request):
        """
        POST /api/accounts/analytics/usage-analytics/
        """
        try:
            data = request.data
            self.log("Incoming usage_analytics request:", data)

            view_type = data.get('view_type')
            
            if view_type not in ['account', 'company']:
                return Response(
                    {'error': 'view_type must be either "account" or "company"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse date range
            start_datetime, end_datetime = self.parse_date_range(data.get('date_range'))
            
            # Get base queryset
            base_queryset = self.get_base_queryset(start_datetime, end_datetime)
            
            if view_type == 'account':
                self.log("Computing account-level analytics")
                results = self.get_account_analytics(base_queryset)
            else:
                self.log("Computing company-level analytics")
                results = self.get_company_analytics(base_queryset)
            
            self.log("Final analytics results count:", len(results))

            # Paginate results
            paginated_results = self.paginate_queryset(results)
            if paginated_results is not None:
                results = paginated_results
            
            response_data = {
                'view_type': view_type,
                'filters_applied': {
                    'date_range': {
                        'start': start_datetime.isoformat(),
                        'end': end_datetime.isoformat()
                    }
                },
                'results_count': len(results)
            }
            
            return self.get_paginated_response(results, response_data)
            
        except Exception as e:
            self.log("ERROR in usage_analytics:", str(e))
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get_account_analytics(self, base_queryset):
        """
        Get analytics per location (account level) - OPTIMIZED
        """
        self.log("Optimized: Computing account-level analytics")

        wallet_balance_subquery = GHLWalletBalance.objects.filter(
            ghl_credential_id=OuterRef('ghl_credential__id')
        ).values('current_balance')[:1]

        # Use a single query to get all aggregations at once, grouped by location
        location_analytics = base_queryset.values(
            'ghl_credential__location_id',
            'ghl_credential__company_name',
            'ghl_credential__location_name',
            'ghl_credential__company_id'
        ).annotate(
            total_inbound_messages=Count(Case(When(transaction_type='sms_inbound', then=1))),
            total_outbound_messages=Count(Case(When(transaction_type='sms_outbound', then=1))),
            total_inbound_calls=Count(Case(When(transaction_type='call_inbound', then=1))),
            total_outbound_calls=Count(Case(When(transaction_type='call_outbound', then=1))),
            sms_inbound_usage=Sum(Case(When(transaction_type='sms_inbound', then=F('amount')))),
            sms_outbound_usage=Sum(Case(When(transaction_type='sms_outbound', then=F('amount')))),
            call_inbound_usage=Sum(Case(When(transaction_type='call_inbound', then=F('amount')))),
            call_outbound_usage=Sum(Case(When(transaction_type='call_outbound', then=F('amount')))),
            total_inbound_call_duration=Sum(Case(When(transaction_type='call_inbound', then=F('duration')))),
            total_outbound_call_duration=Sum(Case(When(transaction_type='call_outbound', then=F('duration')))),
            wallet_balance=Subquery(wallet_balance_subquery, output_field=DecimalField())
        )
        
        results = []
        for row in location_analytics:
            sms_inbound_usage = float(row['sms_inbound_usage'] or 0)
            sms_outbound_usage = float(row['sms_outbound_usage'] or 0)
            call_inbound_usage = float(row['call_inbound_usage'] or 0)
            call_outbound_usage = float(row['call_outbound_usage'] or 0)

            inbound_duration = int(row['total_inbound_call_duration'] or 0)
            outbound_duration = int(row['total_outbound_call_duration'] or 0)



            result = {
                'company_name': row['ghl_credential__company_name'],
                'location_name': row['ghl_credential__location_name'],
                'location_id': row['ghl_credential__location_id'],
                'sms_data': {
                    'total_inbound_messages': row['total_inbound_messages'],
                    'total_outbound_messages': row['total_outbound_messages'],
                    'sms_inbound_usage': sms_inbound_usage,
                    'sms_outbound_usage': sms_outbound_usage,
                    'total_sms_usage': sms_inbound_usage + sms_outbound_usage
                },
                'call_data': {
                    'total_inbound_calls': row['total_inbound_calls'],
                    'total_outbound_calls': row['total_outbound_calls'],
                    'total_inbound_call_duration': inbound_duration,
                    'total_outbound_call_duration': outbound_duration,
                    'inbound_call_minutes': round(inbound_duration / 60, 2),
                    'outbound_call_minutes': round(outbound_duration / 60, 2),
                    'call_inbound_usage': call_inbound_usage,
                    'call_outbound_usage': call_outbound_usage
                },
                'combined_totals': {
                    'total_inbound_usage': sms_inbound_usage + call_inbound_usage,
                    'total_outbound_usage': sms_outbound_usage + call_outbound_usage,
                },
                'wallet_balance': int(row['wallet_balance'] or 0)
            }
            results.append(result)

        self.log("Optimized: Final account analytics results count:", len(results))
        return results

    def get_company_analytics(self, base_queryset):
        """
        Get aggregated analytics per company (company level) - OPTIMIZED
        """
        self.log("Optimized: Computing company-level analytics")

        # Use a single query to get all aggregations at once, grouped by company

        wallet_sum_subquery = GHLWalletBalance.objects.filter(
            ghl_credential__company_id=OuterRef('ghl_credential__company_id')
        ).values('ghl_credential__company_id').annotate(
            total_balance=Sum('current_balance')
        ).values('total_balance')
        company_analytics = base_queryset.values(
            'ghl_credential__company_id',
            'ghl_credential__company_name'
        ).annotate(
            total_inbound_messages=Count(Case(When(transaction_type='sms_inbound', then=1))),
            total_outbound_messages=Count(Case(When(transaction_type='sms_outbound', then=1))),
            total_inbound_calls=Count(Case(When(transaction_type='call_inbound', then=1))),
            total_outbound_calls=Count(Case(When(transaction_type='call_outbound', then=1))),
            sms_inbound_usage=Sum(Case(When(transaction_type='sms_inbound', then=F('amount')))),
            sms_outbound_usage=Sum(Case(When(transaction_type='sms_outbound', then=F('amount')))),
            call_inbound_usage=Sum(Case(When(transaction_type='call_inbound', then=F('amount')))),
            call_outbound_usage=Sum(Case(When(transaction_type='call_outbound', then=F('amount')))),
            total_inbound_call_duration=Sum(Case(When(transaction_type='call_inbound', then=F('duration')))),
            total_outbound_call_duration=Sum(Case(When(transaction_type='call_outbound', then=F('duration')))),
            locations_count=Count('ghl_credential__location_id', distinct=True),
            wallet_total_balance=Subquery(wallet_sum_subquery, output_field=DecimalField())

        )
        
        results = []
        for row in company_analytics:
            sms_inbound_usage = float(row['sms_inbound_usage'] or 0)
            sms_outbound_usage = float(row['sms_outbound_usage'] or 0)
            call_inbound_usage = float(row['call_inbound_usage'] or 0)
            call_outbound_usage = float(row['call_outbound_usage'] or 0)
            
            inbound_duration = int(row['total_inbound_call_duration'] or 0)
            outbound_duration = int(row['total_outbound_call_duration'] or 0)

            result = {
                'company_name': row['ghl_credential__company_name'],
                'company_id': row['ghl_credential__company_id'],
                'sms_data': {
                    'total_inbound_messages': row['total_inbound_messages'],
                    'total_outbound_messages': row['total_outbound_messages'],
                    'sms_inbound_usage': sms_inbound_usage,
                    'sms_outbound_usage': sms_outbound_usage,
                    'total_sms_usage': sms_inbound_usage + sms_outbound_usage
                },
                'call_data': {
                    'total_inbound_calls': row['total_inbound_calls'],
                    'total_outbound_calls': row['total_outbound_calls'],
                    'total_inbound_call_duration': inbound_duration,
                    'total_outbound_call_duration': outbound_duration,
                    'inbound_call_minutes': round(inbound_duration / 60, 2),
                    'outbound_call_minutes': round(outbound_duration / 60, 2),
                    'call_inbound_usage': call_inbound_usage,
                    'call_outbound_usage': call_outbound_usage
                },
                'combined_totals': {
                    'total_inbound_usage': sms_inbound_usage + call_inbound_usage,
                    'total_outbound_usage': sms_outbound_usage + call_outbound_usage,
                    'total_usage': sms_inbound_usage + sms_outbound_usage + call_inbound_usage + call_outbound_usage,
                    'locations_count': row['locations_count']
                },
                'wallet_balance': int(row['wallet_total_balance'] or 0)
            }
            results.append(result)
            
        self.log("Optimized: Returning", len(results), "company results")
        return results


    

    

    @action(detail=False, methods=['post'], url_path='bar-graph-analytics')
    def bar_graph_analytics(self, request):
        """
        POST /api/accounts/analytics/bar-graph-analytics/
        
        Returns time-series analytics data for bar graphs
        """
        try:
            data = request.data
            view_type = data.get('view_type')
            graph_type = data.get('graph_type')
            data_type = data.get('data_type')
            
            # Validate parameters
            if view_type not in ['account', 'company']:
                return Response(
                    {'error': 'view_type must be either "account" or "company"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if graph_type not in ['daily', 'weekly', 'monthly']:
                return Response(
                    {'error': 'graph_type must be "daily", "weekly", or "monthly"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if data_type not in ['sms', 'call', 'both']:
                return Response(
                    {'error': 'data_type must be "sms", "call", or "both"'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Parse date range
            start_datetime, end_datetime = self.parse_date_range(data.get('date_range'))
            
            # Get filtering IDs
            if view_type == 'account':
                location_ids = data.get('location_ids', [])
                if not location_ids:
                    return Response(
                        {'error': 'location_ids is required for account view'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                company_ids = data.get('company_ids', [])
                if not company_ids:
                    return Response(
                        {'error': 'company_ids is required for company view'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Get base queryset
            base_queryset = self.get_base_queryset(start_datetime, end_datetime)
            
            # Filter by location or company IDs
            if view_type == 'account':
                base_queryset = base_queryset.filter(ghl_credential__location_id__in=location_ids)
            else:
                base_queryset = base_queryset.filter(ghl_credential__company_id__in=company_ids)
            
            # Generate time series data
            time_series_data = self.generate_time_series_data(
                base_queryset, start_datetime, end_datetime, graph_type, data_type, view_type
            )
            
            response_data = {
                'view_type': view_type,
                'graph_type': graph_type,
                'data_type': data_type,
                'date_range': {
                    'start': start_datetime.date().isoformat(),
                    'end': end_datetime.date().isoformat()
                }
            }
            
            if view_type == 'account':
                response_data['location_ids'] = location_ids
            else:
                response_data['company_ids'] = company_ids
            
            response_data['data'] = time_series_data
            
            return Response(response_data)
            
        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'An error occurred: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def generate_time_series_data(self, base_queryset, start_datetime, end_datetime, graph_type, data_type, view_type):
        """Generate time series data buckets based on graph_type"""
        results = []
        current_date = start_datetime.date()
        end_date = end_datetime.date()
        
        while current_date <= end_date:
            # Determine period boundaries
            if graph_type == 'daily':
                period_start = datetime.combine(current_date, datetime.min.time())
                period_end = datetime.combine(current_date, datetime.max.time())
                period_label = current_date.isoformat()
                next_date = current_date + timedelta(days=1)
            elif graph_type == 'weekly':
                # Start of week (Monday)
                start_of_week = current_date - timedelta(days=current_date.weekday())
                end_of_week = start_of_week + timedelta(days=6)
                period_start = datetime.combine(start_of_week, datetime.min.time())
                period_end = datetime.combine(end_of_week, datetime.max.time())
                period_label = start_of_week.isoformat()
                next_date = end_of_week + timedelta(days=1)
            else:  # monthly
                # First day of month
                start_of_month = current_date.replace(day=1)
                # Last day of month
                if start_of_month.month == 12:
                    next_month = start_of_month.replace(year=start_of_month.year + 1, month=1)
                else:
                    next_month = start_of_month.replace(month=start_of_month.month + 1)
                end_of_month = next_month - timedelta(days=1)
                period_start = datetime.combine(start_of_month, datetime.min.time())
                period_end = datetime.combine(end_of_month, datetime.max.time())
                period_label = start_of_month.isoformat()
                next_date = next_month
            
            # Don't process periods beyond our end date
            if period_start.date() > end_date:
                break
            
            # Get transactions for this period using the same date logic as base queryset
            period_transactions = base_queryset.filter(
                Q(parsed_date__range=[period_start, period_end]) |
                Q(parsed_date__isnull=True, created_at__range=[period_start, period_end])
            )
            
            # Calculate metrics for this period
            period_data = {
                'period': period_label,
                'period_date': period_start.isoformat()
            }
            
            # Add SMS data if requested
            if data_type in ['sms', 'both']:
                sms_metrics = self.calculate_period_sms_metrics(period_transactions)
                period_data['sms_data'] = sms_metrics
            
            # Add call data if requested
            if data_type in ['call', 'both']:
                call_metrics = self.calculate_period_call_metrics(period_transactions)
                period_data['call_data'] = call_metrics
            
            # Add combined usage if both types requested
            if data_type == 'both':
                sms_inbound_usage = period_data['sms_data']['inbound_usage']
                sms_outbound_usage = period_data['sms_data']['outbound_usage']
                call_inbound_usage = period_data['call_data']['inbound_usage']
                call_outbound_usage = period_data['call_data']['outbound_usage']
                
                period_data['combined_usage'] = {
                    'total_inbound_usage': sms_inbound_usage + call_inbound_usage,
                    'total_outbound_usage': sms_outbound_usage + call_outbound_usage,
                    'total_usage': sms_inbound_usage + sms_outbound_usage + call_inbound_usage + call_outbound_usage
                }
            
            results.append(period_data)
            current_date = next_date
        
        return results

    def calculate_period_sms_metrics(self, transactions):
        """Calculate SMS metrics for a specific time period"""
        sms_transactions = transactions.filter(transaction_type__in=['sms_inbound', 'sms_outbound'])
        sms_inbound = sms_transactions.filter(transaction_type='sms_inbound')
        sms_outbound = sms_transactions.filter(transaction_type='sms_outbound')
        
        inbound_count = sms_inbound.count()
        outbound_count = sms_outbound.count()
        
        # Calculate segments (assuming each message can have multiple segments)
        # For now, using message count as segment count - adjust if you have segment data
        
        inbound_usage = float(sms_inbound.aggregate(total=Sum('amount'))['total'] or 0)
        outbound_usage = float(sms_outbound.aggregate(total=Sum('amount'))['total'] or 0)
        
        return {
            'inbound_messages': inbound_count,
            'outbound_messages': outbound_count,
            'inbound_usage': inbound_usage,
            'outbound_usage': outbound_usage,
            'total_usage': inbound_usage + outbound_usage
        }

    def calculate_period_call_metrics(self, transactions):
        """Calculate call metrics for a specific time period"""
        call_transactions = transactions.filter(transaction_type__in=['call_inbound', 'call_outbound'])
        call_inbound = call_transactions.filter(transaction_type='call_inbound')
        call_outbound = call_transactions.filter(transaction_type='call_outbound')
        
        inbound_count = call_inbound.count()
        outbound_count = call_outbound.count()
        total_count = inbound_count + outbound_count
        
        inbound_duration = call_inbound.aggregate(total=Sum('duration'))['total'] or 0
        outbound_duration = call_outbound.aggregate(total=Sum('duration'))['total'] or 0
        total_duration = inbound_duration + outbound_duration
        
        inbound_minutes = round(inbound_duration / 60, 2) if inbound_duration > 0 else 0
        outbound_minutes = round(outbound_duration / 60, 2) if outbound_duration > 0 else 0
        
        inbound_usage = float(call_inbound.aggregate(total=Sum('amount'))['total'] or 0)
        outbound_usage = float(call_outbound.aggregate(total=Sum('amount'))['total'] or 0)
        
        return {
            'total_calls': total_count,
            'total_duration': total_duration,
            'inbound_calls': inbound_count,
            'outbound_calls': outbound_count,
            'inbound_duration': inbound_duration,
            'outbound_duration': outbound_duration,
            'inbound_minutes': inbound_minutes,
            'outbound_minutes': outbound_minutes,
            'inbound_usage': inbound_usage,
            'outbound_usage': outbound_usage,
            'total_usage': inbound_usage + outbound_usage
        }

class SMSConfigurationViewSet(viewsets.GenericViewSet):
    """
    ViewSet for managing SMS default configuration
    """
    
    def get_queryset(self):
        return SMSDefaultConfiguration.objects.all()
    
    @action(detail=False, methods=['get'], url_path='default-config')
    def get_default_config(self, request):
        """Get current default SMS configuration"""
        try:
            config = SMSDefaultConfiguration.get_instance()
            serializer = SMSDefaultConfigurationSerializer(config)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': f'Failed to fetch default configuration: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['put', 'patch'], url_path='update-default-config')
    def update_default_config(self, request):
        """Update default SMS configuration"""
        try:
            config = SMSDefaultConfiguration.get_instance()
            serializer = SMSDefaultConfigurationSerializer(
                config, 
                data=request.data, 
                partial=request.method == 'PATCH'
            )
            
            if serializer.is_valid():
                with transaction.atomic():
                    updated_config = serializer.save()
                    
                    # Check if user wants to apply new defaults to existing records
                    apply_to_existing = request.data.get('apply_to_existing', False)
                    
                    if apply_to_existing:
                        self._apply_defaults_to_existing_records(updated_config)
                    
                    return Response({
                        'message': 'Default configuration updated successfully',
                        'applied_to_existing': apply_to_existing,
                        'config': SMSDefaultConfigurationSerializer(updated_config).data
                    }, status=status.HTTP_200_OK)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response(
                {'error': f'Failed to update default configuration: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    def _apply_defaults_to_existing_records(self, config):
        """Apply new default values to existing GHL credentials that have default values"""
        # Get current default rates before the update
        credentials_to_update = GHLAuthCredentials.objects.all()
        
        # Update records with new defaults
        update_count = 0
        for credential in credentials_to_update:
            updated = False
            # if not credential.inbound_rate:
            credential.inbound_rate = config.default_inbound_rate
            updated = True
            # if not credential.outbound_rate:
            credential.outbound_rate = config.default_outbound_rate
                # updated = True
            # if not credential.inbound_call_rate:
            credential.inbound_call_rate = config.default_call_inbound_rate
                # updated = True
            # if not credential.outbound_call_rate:
            credential.outbound_call_rate = config.default_call_outbound_rate
                # updated = True
            # if not credential.currency:
            credential.currency = config.default_currency
                # updated = True
            
            if updated:
                credential.save()
                update_count += 1
        
        return update_count
    
    @action(detail=False, methods=['post'], url_path='bulk-apply-defaults')
    def bulk_apply_defaults(self, request):
        """Manually apply current default values to selected or all GHL credentials"""
        try:
            config = SMSDefaultConfiguration.get_instance()
            location_ids = request.data.get('location_ids', [])
            force_update = request.data.get('force_update', False)  # Force update even if values exist
            
            with transaction.atomic():
                # Build queryset
                queryset = GHLAuthCredentials.objects.all()
                
                if location_ids:
                    queryset = queryset.filter(location_id__in=location_ids)
                
                if not force_update:
                    # Only update records with missing values
                    queryset = queryset.filter(
                        models.Q(inbound_rate__isnull=True) | 
                        models.Q(outbound_rate__isnull=True) | 
                        models.Q(currency__isnull=True) |
                        models.Q(currency='')
                    )
                
                # Perform bulk update
                update_data = {}
                if force_update or True:  # Always update if force or if missing
                    update_data.update({
                        'inbound_rate': config.default_inbound_rate,
                        'outbound_rate': config.default_outbound_rate,
                        'inbound_call_rate': config.default_inbound_rate,
                        'outbound_call_rate': config.default_outbound_rate,
                        'currency': config.default_currency
                    })
                
                updated_count = queryset.update(**update_data)
                
                return Response({
                    'message': f'Successfully updated {updated_count} records',
                    'updated_count': updated_count,
                    'applied_config': SMSDefaultConfigurationSerializer(config).data
                }, status=status.HTTP_200_OK)
                
        except Exception as e:
            return Response(
                {'error': f'Failed to apply defaults: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get'], url_path='locations-with-defaults')
    def get_locations_with_defaults(self, request):
        """Get locations that are using default values"""
        try:
            config = SMSDefaultConfiguration.get_instance()
            
            # Find locations using default values
            locations_with_defaults = GHLAuthCredentials.objects.filter(
                models.Q(inbound_rate=config.default_inbound_rate) | 
                models.Q(outbound_rate=config.default_outbound_rate) |
                models.Q(currency=config.default_currency)
            ).values(
                'location_id', 'location_name', 'company_name',
                'inbound_rate', 'outbound_rate', 'currency','inbound_call_rate','outbound_call_rate'
            )
            
            return Response({
                'default_config': SMSDefaultConfigurationSerializer(config).data,
                'locations_count': len(locations_with_defaults),
                'locations': list(locations_with_defaults)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to fetch locations with defaults: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        


@csrf_exempt
def webhook_handler(request):
    if request.method != "POST":
        return JsonResponse({"message": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        print("date:----- ", data)
        WebhookLog.objects.create(data=data)
        event_type = data.get("type")
        handle_webhook_event.delay(data, event_type)
        return JsonResponse({"message":"Webhook received"}, status=200)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    



class WalletSyncView(APIView):

    permission_classes = [permissions.IsAuthenticated]
    """
    API endpoint to sync GHL wallet balances.
    Accepts an optional 'location_id' query parameter.
    """
    def get(self, request, *args, **kwargs):
        location_id = request.query_params.get('location_id')
        company_id = request.query_params.get('company_id')

        # Pass the location_id to your sync function
        sync_result = sync_wallet_balance(location_id=location_id, company_id=company_id)

        # Determine HTTP status based on overall sync status
        http_status = status.HTTP_200_OK
        if sync_result.get("status") == "error":
            http_status = status.HTTP_400_BAD_REQUEST # Or 500 if it's a server-side error
        elif sync_result.get("status") == "info":
             http_status = status.HTTP_200_OK # No credentials found, but not an error

        return Response(sync_result, status=http_status)
    


class CallSyncView(APIView):


    permission_classes = [permissions.IsAuthenticated]
    """
    API endpoint to sync GHL call reports.
    Requires either 'location_id' or 'company_id' as a query parameter.
    Optional: 'days_to_fetch' (integer, defaults to 365)
    """
    def get(self, request, *args, **kwargs):
        location_id = request.query_params.get('location_id')
        company_id = request.query_params.get('company_id')

        # Validate input parameters
        if not location_id and not company_id:
            return Response(
                {"status": "error", "message": "Either 'location_id' or 'company_id' must be provided."},
                status=status.HTTP_400_BAD_REQUEST
            )



        credentials = []

        if location_id:
            try:
                credential = GHLAuthCredentials.objects.get(location_id=location_id)
                credentials.append(credential)
            except ObjectDoesNotExist:
                return Response(
                    {"status": "error", "message": "No credentials found for the given location_id."},
                    status=status.HTTP_404_NOT_FOUND
                )
        elif company_id:
            credentials = list(GHLAuthCredentials.objects.filter(company_id=company_id))
            if not credentials:
                return Response(
                    {"status": "error", "message": "No credentials found for the given company_id."},
                    status=status.HTTP_404_NOT_FOUND
                )
        for credential in credentials:
            fetch_calls_task.delay(credential.id)

        return Response({"status": "success", "message": "Call fetching initiated."})






class CompanyAccountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        viewtype = request.query_params.get("type")  # Use query_params for GET
        # company_id = request.query_params.get("company_id")

        if not viewtype:
            return Response(
                {"error": "Missing 'type' in query parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if viewtype == "account":
            # Return all location accounts for the company
            accounts = GHLAuthCredentials.objects.all()
            serializer = GHLAuthCredentialsShortSerializer(accounts, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        elif viewtype == "company":
            companies = (
                            GHLAuthCredentials.objects
                            .values('company_id', 'company_name')
                            .distinct("company_id")
                        )
            return Response(companies, status=status.HTTP_200_OK)

        else:
            return Response(
                {"error": "Invalid 'type'. Must be 'account' or 'company'."},
                status=status.HTTP_400_BAD_REQUEST
            )
        





class AccountDataForCompanyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        company_id = request.query_params.get("company_id")  # Use query_params for GET
        # company_id = request.query_params.get("company_id")

        if not company_id:
            return Response(
                {"error": "Missing 'company_id' in query parameters."},
                status=status.HTTP_400_BAD_REQUEST
            )

        accounts = GHLAuthCredentials.objects.filter(company_id=company_id)
        serializer = GHLAuthCredentialsShortSerializer(accounts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


from rest_framework.decorators import api_view
from core.tasks import async_sync_conversations_with_messages

from accounts_management_app.tasks import refresh_all_sync_call_for_last_750_day
@api_view(['POST'])
def trigger_refresh_calls_task(request):
    """
    POST /api/refresh-calls/
    Trigger the Celery task to refresh calls for all GHL locations (last 750 days).
    """
    print("=== [DEBUG] trigger_refresh_calls_task called ===")
    print("Request data:", request.data)

    try:
        task = refresh_all_sync_call_for_last_750_day.delay()
        print(f"=== [DEBUG] Celery task triggered. Task ID: {task.id} ===")
    except Exception as e:
        print("=== [ERROR] Failed to trigger Celery task ===")
        print("Error:", str(e))
        return Response(
            {"error": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )

    return Response(
        {
            "message": "Task to refresh calls for the last 750 days has been triggered.",
            "task_id": task.id
        },
        status=status.HTTP_202_ACCEPTED
    )


@api_view(['POST'])
def trigger_refresh_conversations_task(request):
    """
    POST /api/refresh-calls/
    Trigger the Celery task to refresh calls for all GHL locations (last 750 days).
    If location_id is provided, refresh only that location.
    """
    location_id = request.GET.get("location_id")
    print("locationID: ", location_id)

    if location_id:
        try:
            token = GHLAuthCredentials.objects.get(location_id=location_id)
            async_sync_conversations_with_messages.delay(location_id, token.access_token)
        except GHLAuthCredentials.DoesNotExist:
            return Response(
                {"error": f"No credentials found for location_id {location_id}"},
                status=status.HTTP_404_NOT_FOUND
            )
    else:
        # Loop through all locations
        credentials = GHLAuthCredentials.objects.all()
        if not credentials.exists():
            return Response(
                {"error": "No GHL credentials found."},
                status=status.HTTP_404_NOT_FOUND
            )
        for cred in credentials:
            async_sync_conversations_with_messages.delay(cred.location_id, cred.access_token)

    return Response(
        {"message": "Task to refresh calls for the last 750 days has been triggered."},
        status=status.HTTP_202_ACCEPTED
    )


from core.tasks import make_api_call
@api_view(['GET'])
def make_api_call_view(request):
    """
    POST /api/refresh-calls/
    Trigger the Celery task to refresh calls for all GHL locations (last 750 days).
    """
    make_api_call.delay()  # run in background
    
    return Response(
        {"message": "Api refresh task initiated for last days"},
        status=status.HTTP_200_OK
    )


from django.views import View

class RefreshSyncCallView(View):
    def post(self, request, *args, **kwargs):
        # Trigger the Celery task
        task = refresh_all_sync_call_for_last_750_day.delay()
        return JsonResponse({
            "status": "Task triggered",
            "task_id": task.id
        })