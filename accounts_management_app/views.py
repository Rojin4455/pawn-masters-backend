from rest_framework import generics, permissions
from core.models import GHLAuthCredentials,SMSDefaultConfiguration
from .serializers import GHLAuthCredentialsSerializer, CompanyNameSearchSerializer

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
    AnalyticsRequestSerializer
)

from django.db import transaction
from .serializers import SMSDefaultConfigurationSerializer, GHLCredentialsUpdateSerializer, CompanyViewWithCallsSerializer, AccountViewWithCallsSerializer
from django.db import models

import json
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from accounts_management_app.models import WebhookLog
from accounts_management_app.tasks import handle_webhook_event






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
        queryset = TextMessage.objects.select_related('conversation__location')
        
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
        Get base Calls queryset with applied filters
        """
        queryset = CallRecord.objects.select_related('conversation__location')
        
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
            'conversation__location__inbound_call_rate',
            'conversation__location__outbound_call_rate',
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

        # Get Call stats per location
        call_stats = calls_queryset.values(
            'conversation__location__location_id',
        ).annotate(
            # Call aggregations - duration in seconds, convert to minutes for cost calculation
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
        call_stats_dict = {
            stat['conversation__location__location_id']: stat 
            for stat in call_stats
        }

        # Combine SMS and Call data
        results = []
        for location in sms_stats:
            location_id = location['conversation__location__location_id']
            
            # Get call stats for this location
            location_call_stats = call_stats_dict.get(location_id, {
                'total_inbound_call_duration': 0,
                'total_outbound_call_duration': 0,
                'total_inbound_calls': 0,
                'total_outbound_calls': 0,
            })
            
            # SMS rates and calculations
            sms_inbound_rate = location['conversation__location__inbound_rate'] or Decimal('0.00')
            sms_outbound_rate = location['conversation__location__outbound_rate'] or Decimal('0.00')
            
            sms_inbound_usage = sms_inbound_rate * location['total_inbound_messages']
            sms_outbound_usage = sms_outbound_rate * location['total_outbound_messages']
            
            # Call rates and calculations (per minute)
            call_inbound_rate = location['conversation__location__inbound_call_rate'] or Decimal('0.00')
            call_outbound_rate = location['conversation__location__outbound_call_rate'] or Decimal('0.00')
            
            # Convert duration from seconds to minutes for cost calculation
            inbound_call_minutes = Decimal(str(location_call_stats['total_inbound_call_duration'])) / Decimal('60')
            outbound_call_minutes = Decimal(str(location_call_stats['total_outbound_call_duration'])) / Decimal('60')
            
            # Calculate call usage costs
            call_inbound_usage = call_inbound_rate * inbound_call_minutes
            call_outbound_usage = call_outbound_rate * outbound_call_minutes
            
            # Total usage combining SMS and Calls
            total_inbound_usage = sms_inbound_usage + call_inbound_usage
            total_outbound_usage = sms_outbound_usage + call_outbound_usage
            
            results.append({
                'company_name': location['conversation__location__company_name'],
                'location_name': location['conversation__location__location_name'],
                'location_id': location_id,
                
                # SMS Data
                'total_inbound_segments': location['total_inbound_segments'],
                'total_outbound_segments': location['total_outbound_segments'],
                'total_inbound_messages': location['total_inbound_messages'],
                'total_outbound_messages': location['total_outbound_messages'],
                'sms_inbound_usage': sms_inbound_usage,
                'sms_outbound_usage': sms_outbound_usage,
                'sms_inbound_rate': sms_inbound_rate,
                'sms_outbound_rate': sms_outbound_rate,
                
                # Call Data
                'total_inbound_calls': location_call_stats['total_inbound_calls'],
                'total_outbound_calls': location_call_stats['total_outbound_calls'],
                'total_inbound_call_duration': location_call_stats['total_inbound_call_duration'],
                'total_outbound_call_duration': location_call_stats['total_outbound_call_duration'],
                'inbound_call_minutes': float(inbound_call_minutes),
                'outbound_call_minutes': float(outbound_call_minutes),
                'call_inbound_usage': call_inbound_usage,
                'call_outbound_usage': call_outbound_usage,
                'call_inbound_rate': call_inbound_rate,
                'call_outbound_rate': call_outbound_rate,
                
                # Combined Totals
                'total_inbound_usage': total_inbound_usage,
                'total_outbound_usage': total_outbound_usage,
                'total_usage': total_inbound_usage + total_outbound_usage,
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

        # Group Call data by company
        call_company_stats = calls_queryset.values(
            'conversation__location__company_id',
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
            stat['conversation__location__company_id']: stat 
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
            
            # Get all locations for this company to calculate total usage
            company_locations = sms_queryset.filter(
                conversation__location__company_id=company_id
            ).values(
                'conversation__location__location_id',
                'conversation__location__inbound_rate',
                'conversation__location__outbound_rate',
                'conversation__location__inbound_call_rate',
                'conversation__location__outbound_call_rate',
            ).annotate(
                location_inbound_messages=Coalesce(
                    Count('id', filter=Q(direction='inbound')), 0
                ),
                location_outbound_messages=Coalesce(
                    Count('id', filter=Q(direction='outbound')), 0
                ),
            ).distinct()

            # Get call data for each location in this company
            company_call_locations = calls_queryset.filter(
                conversation__location__company_id=company_id
            ).values(
                'conversation__location__location_id',
            ).annotate(
                location_inbound_call_duration=Coalesce(
                    Sum('duration', filter=Q(direction='inbound')), 0
                ),
                location_outbound_call_duration=Coalesce(
                    Sum('duration', filter=Q(direction='outbound')), 0
                ),
            )

            # Create call location lookup
            call_location_dict = {
                loc['conversation__location__location_id']: loc 
                for loc in company_call_locations
            }
            
            # Calculate total usage for this company
            total_sms_inbound_usage = Decimal('0.00')
            total_sms_outbound_usage = Decimal('0.00')
            total_call_inbound_usage = Decimal('0.00')
            total_call_outbound_usage = Decimal('0.00')

            for location in company_locations:
                location_id = location['conversation__location__location_id']
                
                # SMS calculations
                sms_inbound_rate = location.get('conversation__location__inbound_rate') or Decimal('0.00')
                sms_outbound_rate = location.get('conversation__location__outbound_rate') or Decimal('0.00')

                total_sms_inbound_usage += sms_inbound_rate * location.get('location_inbound_messages', 0)
                total_sms_outbound_usage += sms_outbound_rate * location.get('location_outbound_messages', 0)

                # Call calculations
                call_inbound_rate = location.get('conversation__location__inbound_call_rate') or Decimal('0.00')
                call_outbound_rate = location.get('conversation__location__outbound_call_rate') or Decimal('0.00')
                
                location_call_data = call_location_dict.get(location_id, {
                    'location_inbound_call_duration': 0,
                    'location_outbound_call_duration': 0,
                })
                
                # Convert duration from seconds to minutes
                inbound_call_minutes = Decimal(str(location_call_data['location_inbound_call_duration'])) / Decimal('60')
                outbound_call_minutes = Decimal(str(location_call_data['location_outbound_call_duration'])) / Decimal('60')
                
                total_call_inbound_usage += call_inbound_rate * inbound_call_minutes
                total_call_outbound_usage += call_outbound_rate * outbound_call_minutes

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
                'total_inbound_call_minutes': float(total_inbound_call_minutes),
                'total_outbound_call_minutes': float(total_outbound_call_minutes),
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
                total_messages=Count('id'),
                total_segments=Sum('segments'),
                total_inbound_messages=Count('id', filter=Q(direction='inbound')),
                total_outbound_messages=Count('id', filter=Q(direction='outbound')),
                total_inbound_segments=Sum('segments', filter=Q(direction='inbound')),
                total_outbound_segments=Sum('segments', filter=Q(direction='outbound')),
            )
            
            # Get Call statistics
            call_stats = CallRecord.objects.aggregate(
                total_calls=Count('id'),
                total_call_duration=Sum('duration'),
                total_inbound_calls=Count('id', filter=Q(direction='inbound')),
                total_outbound_calls=Count('id', filter=Q(direction='outbound')),
                total_inbound_call_duration=Sum('duration', filter=Q(direction='inbound')),
                total_outbound_call_duration=Sum('duration', filter=Q(direction='outbound')),
            )
            
            # Get company and location counts
            company_count = GHLAuthCredentials.objects.values('company_id').distinct().count()
            location_count = GHLAuthCredentials.objects.count()
            
            # Convert call durations to minutes
            total_call_minutes = (call_stats['total_call_duration'] or 0) / 60
            total_inbound_call_minutes = (call_stats['total_inbound_call_duration'] or 0) / 60
            total_outbound_call_minutes = (call_stats['total_outbound_call_duration'] or 0) / 60
            
            summary = {
                'total_companies': company_count,
                'total_locations': location_count,
                
                # SMS Summary
                'total_messages': sms_stats['total_messages'] or 0,
                'total_segments': sms_stats['total_segments'] or 0,
                'total_inbound_messages': sms_stats['total_inbound_messages'] or 0,
                'total_outbound_messages': sms_stats['total_outbound_messages'] or 0,
                'total_inbound_segments': sms_stats['total_inbound_segments'] or 0,
                'total_outbound_segments': sms_stats['total_outbound_segments'] or 0,
                
                # Call Summary
                'total_calls': call_stats['total_calls'] or 0,
                'total_call_duration': call_stats['total_call_duration'] or 0,
                'total_call_minutes': round(total_call_minutes, 2),
                'total_inbound_calls': call_stats['total_inbound_calls'] or 0,
                'total_outbound_calls': call_stats['total_outbound_calls'] or 0,
                'total_inbound_call_duration': call_stats['total_inbound_call_duration'] or 0,
                'total_outbound_call_duration': call_stats['total_outbound_call_duration'] or 0,
                'total_inbound_call_minutes': round(total_inbound_call_minutes, 2),
                'total_outbound_call_minutes': round(total_outbound_call_minutes, 2),
            }
            
            return Response(summary, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to fetch summary: {str(e)}'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



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