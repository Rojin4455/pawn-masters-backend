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
from .serializers import SMSDefaultConfigurationSerializer, GHLCredentialsUpdateSerializer, CompanyViewWithCallsSerializer, AccountViewWithCallsSerializer
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







class SMSAnalyticsViewSet(viewsets.GenericViewSet):
    """
    ViewSet for SMS and Call usage analytics with optimized queries
    """
    def get_base_sms_queryset(self, filters):
        """
        Get base SMS queryset with applied filters
        """
        # queryset = TextMessage.objects.select_related('conversation__location')
        queryset = TextMessage.objects.select_related('conversation__location').filter(
            conversation__location__is_approved=True
        )

        # Apply date range filter
        if filters.get('date_range'):
            date_range = filters['date_range']
            queryset = queryset.filter(
                date_added__gte=date_range['start'],
                date_added__lte=date_range['end']
            )

        # Apply category filter
        if filters.get('category'):
            queryset = queryset.filter(
                conversation__location__category_id=filters['category']
            )

        # Apply company filter
        if filters.get('company_id'):
            queryset = queryset.filter(
                conversation__location__company_id=filters['company_id']
            )

        return queryset

    def get_base_calls_queryset(self, filters):
        """
        Get base Calls queryset with applied filters - Updated to use CallReport
        """
        # Updated to use CallReport instead of CallRecord
        # queryset = CallReport.objects.select_related('ghl_credential')
        queryset = CallReport.objects.select_related('ghl_credential').filter(
            ghl_credential__is_approved=True
        )


        # Apply date range filter
        if filters.get('date_range'):
            date_range = filters['date_range']
            queryset = queryset.filter(
                date_added__gte=date_range['start'],
                date_added__lte=date_range['end']
            )

        # Apply category filter
        if filters.get('category'):
            queryset = queryset.filter(
                ghl_credential__category_id=filters['category']
            )

        # Apply company filter
        if filters.get('company_id'):
            queryset = queryset.filter(
                ghl_credential__company_id=filters['company_id']
            )

        return queryset

    def get_account_view_data(self, filters):
        """
        Get per-location analytics data with SMS and Call data
        """
        sms_queryset = self.get_base_sms_queryset(filters)
        calls_queryset = self.get_base_calls_queryset(filters)

        # Get SMS stats per location
        sms_stats = sms_queryset.values(
            'conversation__location__location_id',
            'conversation__location__location_name',
            'conversation__location__company_name',
            'conversation__location__inbound_rate',
            'conversation__location__outbound_rate',
        ).annotate(
            # SMS Segment aggregations
            total_inbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='inbound')), 0
            ),
            total_outbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='outbound')), 0
            ),
            # SMS Message count aggregations
            total_inbound_messages=Coalesce(
                Count('id', filter=Q(direction='inbound')), 0
            ),
            total_outbound_messages=Coalesce(
                Count('id', filter=Q(direction='outbound')), 0
            ),
        ).order_by('conversation__location__company_name', 'conversation__location__location_name')

        # Get Call stats per location - Updated to use CallReport
        call_stats = calls_queryset.values(
            'ghl_credential__location_id',
            'ghl_credential__inbound_call_rate',
            'ghl_credential__outbound_call_rate',
            'ghl_credential__call_price_ratio',
        ).annotate(
            # Call aggregations - duration in seconds
            total_inbound_call_duration=Coalesce(
                Sum('duration', filter=Q(direction='inbound')), 0
            ),
            total_outbound_call_duration=Coalesce(
                Sum('duration', filter=Q(direction='outbound')), 0
            ),
            # Call count aggregations
            total_inbound_calls=Coalesce(
                Count('id', filter=Q(direction='inbound')), 0
            ),
            total_outbound_calls=Coalesce(
                Count('id', filter=Q(direction='outbound')), 0
            ),
        ).order_by('ghl_credential__location_id')

        # Create a dictionary for quick call stats lookup, also store rates and ratio
        call_stats_dict = {}
        for stat in call_stats:
            location_id = stat['ghl_credential__location_id']
            call_stats_dict[location_id] = {
                'total_inbound_call_duration': stat['total_inbound_call_duration'],
                'total_outbound_call_duration': stat['total_outbound_call_duration'],
                'total_inbound_calls': stat['total_inbound_calls'],
                'total_outbound_calls': stat['total_outbound_calls'],
                'inbound_call_rate': stat['ghl_credential__inbound_call_rate'],
                'outbound_call_rate': stat['ghl_credential__outbound_call_rate'],
                'call_price_ratio': stat['ghl_credential__call_price_ratio'],
            }

        results = []
        for location_sms_data in sms_stats:
            location_id = location_sms_data['conversation__location__location_id']
            location_call_data = call_stats_dict.get(location_id, {
                'total_inbound_call_duration': 0,
                'total_outbound_call_duration': 0,
                'total_inbound_calls': 0,
                'total_outbound_calls': 0,
                'inbound_call_rate': Decimal('0.00'),
                'outbound_call_rate': Decimal('0.00'),
                'call_price_ratio': Decimal('1.0'), # Default to 1.0 if not found
            })

            # SMS Calculations
            sms_inbound_rate = location_sms_data['conversation__location__inbound_rate'] or Decimal('0.00')
            sms_outbound_rate = location_sms_data['conversation__location__outbound_rate'] or Decimal('0.00')

            sms_inbound_usage = sms_inbound_rate * location_sms_data['total_inbound_messages']
            sms_outbound_usage = sms_outbound_rate * location_sms_data['total_outbound_messages']
            total_sms_usage = sms_inbound_usage + sms_outbound_usage

            # Call Calculations
            inbound_call_minutes = Decimal(str(location_call_data['total_inbound_call_duration'])) / Decimal('60')
            outbound_call_minutes = Decimal(str(location_call_data['total_outbound_call_duration'])) / Decimal('60')

            # Ensure call_price_ratio is correctly handled (0 if explicitly 0, 1.0 if None)
            call_price_ratio = location_call_data['call_price_ratio']
            if call_price_ratio is None:
                call_price_ratio = Decimal('1.0') # Default for None, adjust if different logic needed

            call_inbound_rate_effective = (location_call_data['inbound_call_rate'] or Decimal('0.00')) * call_price_ratio
            call_outbound_rate_effective = (location_call_data['outbound_call_rate'] or Decimal('0.00')) * call_price_ratio

            call_inbound_usage = call_inbound_rate_effective * inbound_call_minutes
            call_outbound_usage = call_outbound_rate_effective * outbound_call_minutes
            total_call_usage = call_inbound_usage + call_outbound_usage

            # Combined Totals
            total_inbound_usage = sms_inbound_usage + call_inbound_usage
            total_outbound_usage = sms_outbound_usage + call_outbound_usage
            total_usage = total_sms_usage + total_call_usage

            results.append({
                'company_name': location_sms_data['conversation__location__company_name'],
                'location_name': location_sms_data['conversation__location__location_name'],
                'location_id': location_id,
                # SMS Data
                'total_inbound_segments': location_sms_data['total_inbound_segments'],
                'total_outbound_segments': location_sms_data['total_outbound_segments'],
                'total_inbound_messages': location_sms_data['total_inbound_messages'],
                'total_outbound_messages': location_sms_data['total_outbound_messages'],
                'sms_inbound_usage': sms_inbound_usage,
                'sms_outbound_usage': sms_outbound_usage,
                'sms_inbound_rate': sms_inbound_rate,
                'sms_outbound_rate': sms_outbound_rate,
                "total_sms_usage": total_sms_usage,
                # Call Data
                'total_inbound_calls': location_call_data['total_inbound_calls'],
                'total_outbound_calls': location_call_data['total_outbound_calls'],
                'total_inbound_call_duration': location_call_data['total_inbound_call_duration'],
                'total_outbound_call_duration': location_call_data['total_outbound_call_duration'],
                'inbound_call_minutes': inbound_call_minutes,
                'outbound_call_minutes': outbound_call_minutes,
                'call_inbound_usage': call_inbound_usage,
                'call_outbound_usage': call_outbound_usage,
                'call_inbound_rate': location_call_data['inbound_call_rate'],
                'call_outbound_rate': location_call_data['outbound_call_rate'],
                "total_call_usage": total_call_usage,
                # Combined Totals
                'total_inbound_usage': total_inbound_usage,
                'total_outbound_usage': total_outbound_usage,
                'total_usage': total_usage,
            })
        return results

    def get_company_view_data(self, filters):
        """
        Get aggregated company-level analytics data with SMS and Call data
        """
        sms_queryset = self.get_base_sms_queryset(filters)
        calls_queryset = self.get_base_calls_queryset(filters)

        # Group SMS data by company
        sms_company_stats = sms_queryset.values(
            'conversation__location__company_id',
        ).annotate(
            # Get the first non-null company name for each company_id
            company_name=Coalesce(
                Min('conversation__location__company_name',
                     filter=Q(conversation__location__company_name__isnull=False)),
                Value('Unknown Company')
            ),
            # SMS Segment aggregations
            total_inbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='inbound')), 0
            ),
            total_outbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='outbound')), 0
            ),
            # SMS Message count aggregations
            total_inbound_messages=Coalesce(
                Count('id', filter=Q(direction='inbound')), 0
            ),
            total_outbound_messages=Coalesce(
                Count('id', filter=Q(direction='outbound')), 0
            ),
            # Location count
            locations_count=Count('conversation__location__location_id', distinct=True),
        ).order_by('company_name')

        # Group Call data by company - Updated to use CallReport
        call_company_stats = calls_queryset.values(
            'ghl_credential__company_id',
        ).annotate(
            # Call aggregations
            total_inbound_call_duration=Coalesce(
                Sum('duration', filter=Q(direction='inbound')), 0
            ),
            total_outbound_call_duration=Coalesce(
                Sum('duration', filter=Q(direction='outbound')), 0
            ),
            # Call count aggregations
            total_inbound_calls=Coalesce(
                Count('id', filter=Q(direction='inbound')), 0
            ),
            total_outbound_calls=Coalesce(
                Count('id', filter=Q(direction='outbound')), 0
            ),
        )

        # Create a dictionary for quick call stats lookup
        call_company_stats_dict = {
            stat['ghl_credential__company_id']: stat
            for stat in call_company_stats
        }

        # Calculate usage costs per company
        results = []
        for company in sms_company_stats:
            company_id = company['conversation__location__company_id']

            # Get call stats for this company
            company_call_stats = call_company_stats_dict.get(company_id, {
                'total_inbound_call_duration': 0,
                'total_outbound_call_duration': 0,
                'total_inbound_calls': 0,
                'total_outbound_calls': 0,
            })

            # Get all locations for this company to calculate total usage and rates
            company_locations_data = GHLAuthCredentials.objects.filter(
                company_id=company_id
            ).values(
                'location_id',
                'inbound_rate',
                'outbound_rate',
                'inbound_call_rate',
                'outbound_call_rate',
                'call_price_ratio',
            )

            # Pre-fetch SMS data for all relevant locations within this company
            sms_data_for_company = sms_queryset.filter(
                conversation__location__company_id=company_id
            ).values(
                'conversation__location__location_id',
                'direction'
            ).annotate(
                message_count=Coalesce(Count('id'), 0),
                segment_count=Coalesce(Sum('segments'), 0)
            )

            # Pre-fetch Call data for all relevant locations within this company - Updated to use CallReport
            call_data_for_company = calls_queryset.filter(
                ghl_credential__company_id=company_id
            ).values(
                'ghl_credential__location_id',
                'direction'
            ).annotate(
                call_duration=Coalesce(Sum('duration'), 0)
            )

            # Organize pre-fetched data
            sms_location_summary = {}
            for item in sms_data_for_company:
                loc_id = item['conversation__location__location_id']
                if loc_id not in sms_location_summary:
                    sms_location_summary[loc_id] = {
                        'inbound_messages': 0, 'outbound_messages': 0,
                        'inbound_segments': 0, 'outbound_segments': 0
                    }
                if item['direction'] == 'inbound':
                    sms_location_summary[loc_id]['inbound_messages'] += item['message_count']
                    sms_location_summary[loc_id]['inbound_segments'] += item['segment_count']
                else:
                    sms_location_summary[loc_id]['outbound_messages'] += item['message_count']
                    sms_location_summary[loc_id]['outbound_segments'] += item['segment_count']

            call_location_summary = {}
            for item in call_data_for_company:
                loc_id = item['ghl_credential__location_id']
                if loc_id not in call_location_summary:
                    call_location_summary[loc_id] = {
                        'inbound_duration': 0, 'outbound_duration': 0
                    }
                if item['direction'] == 'inbound':
                    call_location_summary[loc_id]['inbound_duration'] += item['call_duration']
                else:
                    call_location_summary[loc_id]['outbound_duration'] += item['call_duration']

            # Calculate total usage for this company
            total_sms_inbound_usage = Decimal('0.00')
            total_sms_outbound_usage = Decimal('0.00')
            total_call_inbound_usage = Decimal('0.00')
            total_call_outbound_usage = Decimal('0.00')

            for location_config in company_locations_data:
                location_id = location_config['location_id']

                # SMS calculations
                sms_inbound_rate = location_config.get('inbound_rate') or Decimal('0.00')
                sms_outbound_rate = location_config.get('outbound_rate') or Decimal('0.00')

                loc_sms_data = sms_location_summary.get(location_id, {'inbound_messages': 0, 'outbound_messages': 0})
                total_sms_inbound_usage += sms_inbound_rate * Decimal(loc_sms_data['inbound_messages'])
                total_sms_outbound_usage += sms_outbound_rate * Decimal(loc_sms_data['outbound_messages'])

                # Call calculations
                call_inbound_rate = location_config.get('inbound_call_rate') or Decimal('0.00')
                call_outbound_rate = location_config.get('outbound_call_rate') or Decimal('0.00')

                # Handle call_price_ratio: if None, default to 1.0; otherwise use its value (including 0)
                call_price_ratio = location_config.get('call_price_ratio')
                if call_price_ratio is None:
                    call_price_ratio = Decimal('1.0') # Default for None

                loc_call_data = call_location_summary.get(location_id, {'inbound_duration': 0, 'outbound_duration': 0})

                inbound_call_minutes = Decimal(str(loc_call_data['inbound_duration'])) / Decimal('60')
                outbound_call_minutes = Decimal(str(loc_call_data['outbound_duration'])) / Decimal('60')

                total_call_inbound_usage += (call_inbound_rate * call_price_ratio) * inbound_call_minutes
                total_call_outbound_usage += (call_outbound_rate * call_price_ratio) * outbound_call_minutes

            # Combined totals
            total_inbound_usage = total_sms_inbound_usage + total_call_inbound_usage
            total_outbound_usage = total_sms_outbound_usage + total_call_outbound_usage
            total_usage = total_inbound_usage + total_outbound_usage

            # Convert call durations to minutes for display
            total_inbound_call_minutes = Decimal(str(company_call_stats['total_inbound_call_duration'])) / Decimal('60')
            total_outbound_call_minutes = Decimal(str(company_call_stats['total_outbound_call_duration'])) / Decimal('60')

            results.append({
                'company_name': company['company_name'],
                'company_id': company_id,
                # SMS Data
                'total_inbound_segments': company['total_inbound_segments'],
                'total_outbound_segments': company['total_outbound_segments'],
                'total_inbound_messages': company['total_inbound_messages'],
                'total_outbound_messages': company['total_outbound_messages'],
                'sms_inbound_usage': total_sms_inbound_usage,
                'sms_outbound_usage': total_sms_outbound_usage,
                # Call Data
                'total_inbound_calls': company_call_stats['total_inbound_calls'],
                'total_outbound_calls': company_call_stats['total_outbound_calls'],
                'total_inbound_call_duration': company_call_stats['total_inbound_call_duration'],
                'total_outbound_call_duration': company_call_stats['total_outbound_call_duration'],
                'total_inbound_call_minutes': total_inbound_call_minutes,
                'total_outbound_call_minutes': total_outbound_call_minutes,
                'call_inbound_usage': total_call_inbound_usage,
                'call_outbound_usage': total_call_outbound_usage,
                # Combined Totals
                'total_inbound_usage': total_inbound_usage,
                'total_outbound_usage': total_outbound_usage,
                'total_usage': total_usage,
                'locations_count': company['locations_count'],
            })
        return results

    @action(detail=False, methods=['post'], url_path='usage-analytics')
    def get_usage_analytics(self, request):
        """
        Get SMS and Call usage analytics based on view type and filters
        """
        # Validate request payload
        request_serializer = AnalyticsRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                request_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = request_serializer.validated_data
        view_type = validated_data.get('view_type', 'account')
        filters = {
            'date_range': validated_data.get('date_range'),
            'category': validated_data.get('category'),
            'company_id': validated_data.get('company_id'),
        }

        try:
            if view_type == 'account':
                data = self.get_account_view_data(filters)
                serializer = AccountViewWithCallsSerializer(data, many=True)
            else:  # company view
                data = self.get_company_view_data(filters)
                serializer = CompanyViewWithCallsSerializer(data, many=True)

            return Response({
                'view_type': view_type,
                'filters_applied': {k: v for k, v in filters.items() if v is not None},
                'results_count': len(data),
                'data': serializer.data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            # It's good practice to log the full traceback in a real application
            import traceback
            traceback.print_exc() # Print traceback for debugging
            return Response(
                {'error': f'Failed to fetch analytics data: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get'], url_path='usage-summary')
    def get_usage_summary(self, request):
        """
        Get overall usage summary statistics including SMS and Calls
        """
        try:
            # Get SMS statistics
            sms_stats = TextMessage.objects.aggregate(
                total_messages=Coalesce(Count('id'), 0),
                total_segments=Coalesce(Sum('segments'), 0),
                total_inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                total_outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                total_inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
                total_outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
            )

            # Get Call statistics - Updated to use CallReport
            call_stats = CallReport.objects.aggregate(
                total_calls=Coalesce(Count('id'), 0),
                total_call_duration=Coalesce(Sum('duration'), 0),
                total_inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                total_outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                total_inbound_call_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
                total_outbound_call_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
            )

            # Note: Calculating total usage for get_usage_summary is complex
            # as rates are per-location. This endpoint currently returns raw counts.
            # If you need aggregated usage costs here, it would require a similar
            # aggregation logic as get_company_view_data.

            return Response({
                'sms_summary': sms_stats,
                'call_summary': call_stats,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {'error': f'Failed to fetch usage summary: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        



    @action(detail=False, methods=['post'], url_path='bar-graph-analytics')
    def get_bar_graph_analytics(self, request):
        """
        Get SMS and Call analytics data formatted for bar graph visualization
        Supports both Account View (location-based) and Company View (company-based)
        """
        # Validate request payload
        request_serializer = BarGraphAnalyticsRequestSerializer(data=request.data)
        if not request_serializer.is_valid():
            return Response(
                request_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        validated_data = request_serializer.validated_data
        date_range = validated_data.get('date_range')
        location_ids = validated_data.get('location_ids', [])
        company_ids = validated_data.get('company_ids', [])  # Add company_ids support
        graph_type = validated_data.get('graph_type', 'daily')  # daily, weekly, monthly
        data_type = validated_data.get('data_type', 'both')  # sms, call, both
        view_type = validated_data.get('view_type', 'account')  # account, company

        try:
            # Build base filters
            base_filters = {}
            if date_range:
                base_filters['date_range'] = date_range
            if view_type == 'account' and location_ids:
                base_filters['location_ids'] = location_ids
            elif view_type == 'company' and company_ids:
                base_filters['company_ids'] = company_ids

            # Get time-series data based on graph type
            if graph_type == 'daily':
                data = self._get_daily_analytics(base_filters, data_type, view_type)
            elif graph_type == 'weekly':
                data = self._get_weekly_analytics(base_filters, data_type, view_type)
            elif graph_type == 'monthly':
                data = self._get_monthly_analytics(base_filters, data_type, view_type)
            else:
                return Response(
                    {'error': 'Invalid graph_type. Must be daily, weekly, or monthly'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response({
                'view_type': view_type,
                'graph_type': graph_type,
                'data_type': data_type,
                'date_range': date_range,
                'location_ids': location_ids if view_type == 'account' else None,
                'company_ids': company_ids if view_type == 'company' else None,
                'data': data
            }, status=status.HTTP_200_OK)

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {'error': f'Failed to fetch bar graph analytics: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_daily_analytics(self, filters, data_type, view_type):
        """Get daily analytics data for both account and company views"""
        date_range = filters.get('date_range')
        location_ids = filters.get('location_ids', [])
        company_ids = filters.get('company_ids', [])
        
        # Determine truncation function and date format
        trunc_func = TruncDay('date_added')
        date_format = '%Y-%m-%d'
        
        data = []
        
        if data_type in ['sms', 'both']:
            # Get SMS data
            sms_queryset = self._build_sms_queryset(filters, view_type)
            sms_data = sms_queryset.annotate(
                period=trunc_func
            ).values('period').annotate(
                total_messages=Coalesce(Count('id'), 0),
                total_segments=Coalesce(Sum('segments'), 0),
                inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
                outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
            ).order_by('period')
            
            # Calculate usage for SMS
            if view_type == 'account':
                sms_usage_data = self._calculate_period_usage(sms_data, 'sms', location_ids, view_type)
            else:  # company
                sms_usage_data = self._calculate_period_usage(sms_data, 'sms', company_ids, view_type)
            
            if data_type == 'sms':
                data = sms_usage_data
            else:
                data = sms_usage_data
        
        if data_type in ['call', 'both']:
            # Get Call data
            calls_queryset = self._build_calls_queryset(filters, view_type)
            call_data = calls_queryset.annotate(
                period=trunc_func
            ).values('period').annotate(
                total_calls=Coalesce(Count('id'), 0),
                total_duration=Coalesce(Sum('duration'), 0),
                inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                inbound_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
                outbound_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
            ).order_by('period')
            
            # Calculate usage for calls
            if view_type == 'account':
                call_usage_data = self._calculate_period_usage(call_data, 'call', location_ids, view_type)
            else:  # company
                call_usage_data = self._calculate_period_usage(call_data, 'call', company_ids, view_type)
            
            if data_type == 'call':
                data = call_usage_data
            elif data_type == 'both':
                # Merge SMS and Call data
                data = self._merge_sms_call_data(data, call_usage_data)
        
        return self._fill_missing_periods(data, filters.get('date_range'), 'daily')

    def _get_weekly_analytics(self, filters, data_type, view_type):
        """Get weekly analytics data for both account and company views"""
        trunc_func = TruncWeek('date_added')
        
        data = []
        
        if data_type in ['sms', 'both']:
            sms_queryset = self._build_sms_queryset(filters, view_type)
            sms_data = sms_queryset.annotate(
                period=trunc_func
            ).values('period').annotate(
                total_messages=Coalesce(Count('id'), 0),
                total_segments=Coalesce(Sum('segments'), 0),
                inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
                outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
            ).order_by('period')
            
            filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
            sms_usage_data = self._calculate_period_usage(sms_data, 'sms', filter_ids, view_type)
            
            if data_type == 'sms':
                data = sms_usage_data
            else:
                data = sms_usage_data
        
        if data_type in ['call', 'both']:
            calls_queryset = self._build_calls_queryset(filters, view_type)
            call_data = calls_queryset.annotate(
                period=trunc_func
            ).values('period').annotate(
                total_calls=Coalesce(Count('id'), 0),
                total_duration=Coalesce(Sum('duration'), 0),
                inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                inbound_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
                outbound_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
            ).order_by('period')
            
            filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
            call_usage_data = self._calculate_period_usage(call_data, 'call', filter_ids, view_type)
            
            if data_type == 'call':
                data = call_usage_data
            elif data_type == 'both':
                data = self._merge_sms_call_data(data, call_usage_data)
        
        return self._fill_missing_periods(data, filters.get('date_range'), 'weekly')


    def _get_monthly_analytics(self, filters, data_type, view_type):
        """Get monthly analytics data for both account and company views"""
        trunc_func = TruncMonth('date_added')
        
        data = []
        
        if data_type in ['sms', 'both']:
            sms_queryset = self._build_sms_queryset(filters, view_type)
            sms_data = sms_queryset.annotate(
                period=trunc_func
            ).values('period').annotate(
                total_messages=Coalesce(Count('id'), 0),
                total_segments=Coalesce(Sum('segments'), 0),
                inbound_messages=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                outbound_messages=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                inbound_segments=Coalesce(Sum('segments', filter=Q(direction='inbound')), 0),
                outbound_segments=Coalesce(Sum('segments', filter=Q(direction='outbound')), 0),
            ).order_by('period')
            
            filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
            sms_usage_data = self._calculate_period_usage(sms_data, 'sms', filter_ids, view_type)
            
            if data_type == 'sms':
                data = sms_usage_data
            else:
                data = sms_usage_data
        
        if data_type in ['call', 'both']:
            calls_queryset = self._build_calls_queryset(filters, view_type)
            call_data = calls_queryset.annotate(
                period=trunc_func
            ).values('period').annotate(
                total_calls=Coalesce(Count('id'), 0),
                total_duration=Coalesce(Sum('duration'), 0),
                inbound_calls=Coalesce(Count('id', filter=Q(direction='inbound')), 0),
                outbound_calls=Coalesce(Count('id', filter=Q(direction='outbound')), 0),
                inbound_duration=Coalesce(Sum('duration', filter=Q(direction='inbound')), 0),
                outbound_duration=Coalesce(Sum('duration', filter=Q(direction='outbound')), 0),
            ).order_by('period')
            
            filter_ids = filters.get('location_ids', []) if view_type == 'account' else filters.get('company_ids', [])
            call_usage_data = self._calculate_period_usage(call_data, 'call', filter_ids, view_type)
            
            if data_type == 'call':
                data = call_usage_data
            elif data_type == 'both':
                data = self._merge_sms_call_data(data, call_usage_data)
        
        return self._fill_missing_periods(data, filters.get('date_range'), 'monthly')

    def _build_sms_queryset(self, filters, view_type):
        """Build SMS queryset with filters for both account and company views"""
        queryset = TextMessage.objects.select_related('conversation__location').filter(
            conversation__location__is_approved=True
        )
        
        if filters.get('date_range'):
            date_range = filters['date_range']
            queryset = queryset.filter(
                date_added__gte=date_range['start'],
                date_added__lte=date_range['end']
            )
        
        if view_type == 'account' and filters.get('location_ids'):
            queryset = queryset.filter(
                conversation__location__location_id__in=filters['location_ids']
            )
        elif view_type == 'company' and filters.get('company_ids'):
            queryset = queryset.filter(
                conversation__location__company_id__in=filters['company_ids']
            )
        
        return queryset

    def _build_calls_queryset(self, filters, view_type):
        """Build calls queryset with filters for both account and company views"""
        queryset = CallReport.objects.select_related('ghl_credential').filter(
            ghl_credential__is_approved=True
        )
        
        if filters.get('date_range'):
            date_range = filters['date_range']
            queryset = queryset.filter(
                date_added__gte=date_range['start'],
                date_added__lte=date_range['end']
            )
        
        if view_type == 'account' and filters.get('location_ids'):
            queryset = queryset.filter(
                ghl_credential__location_id__in=filters['location_ids']
            )
        elif view_type == 'company' and filters.get('company_ids'):
            queryset = queryset.filter(
                ghl_credential__company_id__in=filters['company_ids']
            )
        
        return queryset

    def _calculate_period_usage(self, period_data, data_type, filter_ids, view_type):
        """Calculate usage costs for each period supporting both account and company views"""
        # Get location rates based on view type
        if view_type == 'account':
            # For account view, filter by location_ids
            if data_type == 'sms':
                location_rates = GHLAuthCredentials.objects.filter(
                    location_id__in=filter_ids if filter_ids else []
                ).values('location_id', 'inbound_rate', 'outbound_rate')
            else:  # call
                location_rates = GHLAuthCredentials.objects.filter(
                    location_id__in=filter_ids if filter_ids else []
                ).values('location_id', 'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio')
        else:  # company view
            # For company view, filter by company_ids
            if data_type == 'sms':
                location_rates = GHLAuthCredentials.objects.filter(
                    company_id__in=filter_ids if filter_ids else []
                ).values('location_id', 'inbound_rate', 'outbound_rate')
            else:  # call
                location_rates = GHLAuthCredentials.objects.filter(
                    company_id__in=filter_ids if filter_ids else []
                ).values('location_id', 'inbound_call_rate', 'outbound_call_rate', 'call_price_ratio')
        
        # Create rates dictionary
        rates_dict = {}
        for rate in location_rates:
            location_id = rate['location_id']
            if data_type == 'sms':
                rates_dict[location_id] = {
                    'inbound_rate': rate['inbound_rate'] or Decimal('0.00'),
                    'outbound_rate': rate['outbound_rate'] or Decimal('0.00')
                }
            else:  # call
                call_price_ratio = rate['call_price_ratio'] or Decimal('1.0')
                rates_dict[location_id] = {
                    'inbound_rate': (rate['inbound_call_rate'] or Decimal('0.00')) * call_price_ratio,
                    'outbound_rate': (rate['outbound_call_rate'] or Decimal('0.00')) * call_price_ratio
                }
        
        # Calculate average rates if multiple locations
        if rates_dict:
            avg_inbound_rate = sum(r['inbound_rate'] for r in rates_dict.values()) / len(rates_dict)
            avg_outbound_rate = sum(r['outbound_rate'] for r in rates_dict.values()) / len(rates_dict)
        else:
            avg_inbound_rate = avg_outbound_rate = Decimal('0.00')
        
        result = []
        for item in period_data:
            period_str = item['period'].strftime('%Y-%m-%d')
            
            if data_type == 'sms':
                inbound_usage = avg_inbound_rate * item['inbound_messages']
                outbound_usage = avg_outbound_rate * item['outbound_messages']
                
                result.append({
                    'period': period_str,
                    'period_date': item['period'],
                    'sms_data': {
                        'total_messages': item['total_messages'],
                        'total_segments': item['total_segments'],
                        'inbound_messages': item['inbound_messages'],
                        'outbound_messages': item['outbound_messages'],
                        'inbound_segments': item['inbound_segments'],
                        'outbound_segments': item['outbound_segments'],
                        'inbound_usage': float(inbound_usage),
                        'outbound_usage': float(outbound_usage),
                        'total_usage': float(inbound_usage + outbound_usage)
                    }
                })
            else:  # call
                # Convert duration to minutes
                inbound_minutes = Decimal(str(item['inbound_duration'])) / Decimal('60')
                outbound_minutes = Decimal(str(item['outbound_duration'])) / Decimal('60')
                
                inbound_usage = avg_inbound_rate * inbound_minutes
                outbound_usage = avg_outbound_rate * outbound_minutes
                
                result.append({
                    'period': period_str,
                    'period_date': item['period'],
                    'call_data': {
                        'total_calls': item['total_calls'],
                        'total_duration': item['total_duration'],
                        'inbound_calls': item['inbound_calls'],
                        'outbound_calls': item['outbound_calls'],
                        'inbound_duration': item['inbound_duration'],
                        'outbound_duration': item['outbound_duration'],
                        'inbound_minutes': float(inbound_minutes),
                        'outbound_minutes': float(outbound_minutes),
                        'inbound_usage': float(inbound_usage),
                        'outbound_usage': float(outbound_usage),
                        'total_usage': float(inbound_usage + outbound_usage)
                    }
                })
        
        return result

    def _merge_sms_call_data(self, sms_data, call_data):
        """Merge SMS and call data for combined view"""
        # Create dictionaries for quick lookup
        sms_dict = {item['period']: item for item in sms_data}
        call_dict = {item['period']: item for item in call_data}
        
        # Get all unique periods
        all_periods = set(sms_dict.keys()) | set(call_dict.keys())
        
        merged_data = []
        for period in sorted(all_periods):
            sms_item = sms_dict.get(period, {})
            call_item = call_dict.get(period, {})
            
            # Get period_date from either SMS or call data
            period_date = sms_item.get('period_date') or call_item.get('period_date')
            
            merged_item = {
                'period': period,
                'period_date': period_date,
            }
            
            # Add SMS data if available
            if 'sms_data' in sms_item:
                merged_item['sms_data'] = sms_item['sms_data']
            else:
                merged_item['sms_data'] = {
                    'total_messages': 0,
                    'total_segments': 0,
                    'inbound_messages': 0,
                    'outbound_messages': 0,
                    'inbound_segments': 0,
                    'outbound_segments': 0,
                    'inbound_usage': 0.0,
                    'outbound_usage': 0.0,
                    'total_usage': 0.0
                }
            
            # Add call data if available
            if 'call_data' in call_item:
                merged_item['call_data'] = call_item['call_data']
            else:
                merged_item['call_data'] = {
                    'total_calls': 0,
                    'total_duration': 0,
                    'inbound_calls': 0,
                    'outbound_calls': 0,
                    'inbound_duration': 0,
                    'outbound_duration': 0,
                    'inbound_minutes': 0.0,
                    'outbound_minutes': 0.0,
                    'inbound_usage': 0.0,
                    'outbound_usage': 0.0,
                    'total_usage': 0.0
                }
            
            # Add combined usage
            merged_item['combined_usage'] = {
                'total_inbound_usage': merged_item['sms_data']['inbound_usage'] + merged_item['call_data']['inbound_usage'],
                'total_outbound_usage': merged_item['sms_data']['outbound_usage'] + merged_item['call_data']['outbound_usage'],
                'total_usage': merged_item['sms_data']['total_usage'] + merged_item['call_data']['total_usage']
            }
            
            merged_data.append(merged_item)
        
        return merged_data

    def _fill_missing_periods(self, data, date_range, period_type):
        """Fill missing periods with zero values"""
        if not date_range or not data:
            return data
        
        start_date = date_range['start']
        end_date = date_range['end']
        
        # Create a set of existing periods
        existing_periods = {item['period'] for item in data}
        
        # Generate all periods in the range
        all_periods = []
        current_date = start_date
        
        while current_date <= end_date:
            if period_type == 'daily':
                period_str = current_date.strftime('%Y-%m-%d')
                next_date = current_date + timedelta(days=1)
            elif period_type == 'weekly':
                # Get start of week (Monday)
                start_of_week = current_date - timedelta(days=current_date.weekday())
                period_str = start_of_week.strftime('%Y-%m-%d')
                next_date = start_of_week + timedelta(weeks=1)
                current_date = next_date
            else:  # monthly
                period_str = current_date.strftime('%Y-%m-%d')
                next_date = current_date + relativedelta(months=1)
            
            if period_str not in existing_periods:
                # Create empty period data
                empty_period = {
                    'period': period_str,
                    'period_date': current_date,
                }
                
                # Add appropriate empty data structure
                if any('sms_data' in item for item in data):
                    empty_period['sms_data'] = {
                        'total_messages': 0,
                        'total_segments': 0,
                        'inbound_messages': 0,
                        'outbound_messages': 0,
                        'inbound_segments': 0,
                        'outbound_segments': 0,
                        'inbound_usage': 0.0,
                        'outbound_usage': 0.0,
                        'total_usage': 0.0
                    }
                
                if any('call_data' in item for item in data):
                    empty_period['call_data'] = {
                        'total_calls': 0,
                        'total_duration': 0,
                        'inbound_calls': 0,
                        'outbound_calls': 0,
                        'inbound_duration': 0,
                        'outbound_duration': 0,
                        'inbound_minutes': 0.0,
                        'outbound_minutes': 0.0,
                        'inbound_usage': 0.0,
                        'outbound_usage': 0.0,
                        'total_usage': 0.0
                    }
                
                if any('combined_usage' in item for item in data):
                    empty_period['combined_usage'] = {
                        'total_inbound_usage': 0.0,
                        'total_outbound_usage': 0.0,
                        'total_usage': 0.0
                    }
                
                all_periods.append(empty_period)
            
            current_date = next_date
        
        # Combine existing and empty periods, then sort
        combined_data = data + all_periods
        combined_data.sort(key=lambda x: x['period'])
        
        return combined_data


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

        # Pass the location_id to your sync function
        sync_result = sync_wallet_balance(location_id=location_id)

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