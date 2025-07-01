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
from .models import TextMessage
from .serializers import (
    AccountViewSerializer, CompanyViewSerializer, 
    AnalyticsRequestSerializer
)

from django.db import transaction
from .serializers import SMSDefaultConfigurationSerializer, GHLCredentialsUpdateSerializer
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
    ViewSet for SMS usage analytics with optimized queries
    """
    
    def get_base_queryset(self, filters):
        """
        Get base queryset with applied filters
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

    def get_account_view_data(self, filters):
        """
        Get per-location analytics data with optimized aggregation
        """
        base_queryset = self.get_base_queryset(filters)
        
        # Aggregate data per location using efficient single query
        location_stats = base_queryset.values(
            'conversation__location__location_id',
            'conversation__location__location_name',
            'conversation__location__company_name',
            'conversation__location__inbound_rate',
            'conversation__location__outbound_rate',
        ).annotate(
            # Segment aggregations
            total_inbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='inbound')), 0
            ),
            total_outbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='outbound')), 0
            ),
            # Message count aggregations
            total_inbound_messages=Coalesce(
                Count('id', filter=Q(direction='inbound')), 0
            ),
            total_outbound_messages=Coalesce(
                Count('id', filter=Q(direction='outbound')), 0
            ),
        ).order_by('conversation__location__company_name', 'conversation__location__location_name')

        # Calculate usage costs
        results = []
        for location in location_stats:
            inbound_rate = location['conversation__location__inbound_rate'] or Decimal('0.00')
            outbound_rate = location['conversation__location__outbound_rate'] or Decimal('0.00')
            
            inbound_usage = inbound_rate * location['total_inbound_messages']
            outbound_usage = outbound_rate * location['total_outbound_messages']
            
            results.append({
                'company_name': location['conversation__location__company_name'],
                'location_name': location['conversation__location__location_name'],
                'location_id': location['conversation__location__location_id'],
                'total_inbound_segments': location['total_inbound_segments'],
                'total_outbound_segments': location['total_outbound_segments'],
                'total_inbound_messages': location['total_inbound_messages'],
                'total_outbound_messages': location['total_outbound_messages'],
                'total_inbound_usage': inbound_usage,
                'total_outbound_usage': outbound_usage,
                'inbound_rate': inbound_rate,
                'outbound_rate': outbound_rate,
                'total_usage': inbound_usage + outbound_usage,  # ✅ Corrected line
            })


        return results

    def get_company_view_data(self, filters):
        """
        Get aggregated company-level analytics data
        """
        base_queryset = self.get_base_queryset(filters)
        
        # Group by company_id only (not company_name) to avoid duplicates
        company_stats = base_queryset.values(
            'conversation__location__company_id',
        ).annotate(
            # Get the first non-null company name for each company_id
            company_name=Coalesce(
                Min('conversation__location__company_name', 
                    filter=Q(conversation__location__company_name__isnull=False)),
                Value('Unknown Company')
            ),
            # Segment aggregations
            total_inbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='inbound')), 0
            ),
            total_outbound_segments=Coalesce(
                Sum('segments', filter=Q(direction='outbound')), 0
            ),
            # Message count aggregations
            total_inbound_messages=Coalesce(
                Count('id', filter=Q(direction='inbound')), 0
            ),
            total_outbound_messages=Coalesce(
                Count('id', filter=Q(direction='outbound')), 0
            ),
            # Location count
            locations_count=Count('conversation__location__location_id', distinct=True),
        ).order_by('company_name')

        # Calculate usage costs per company
        results = []
        for company in company_stats:
            company_id = company['conversation__location__company_id']
            
            # Get all locations for this company to calculate total usage
            company_locations = base_queryset.filter(
                conversation__location__company_id=company_id
            ).values(
                'conversation__location__location_id',
                'conversation__location__inbound_rate',
                'conversation__location__outbound_rate',
            ).annotate(
                location_inbound_messages=Coalesce(
                    Count('id', filter=Q(direction='inbound')), 0
                ),
                location_outbound_messages=Coalesce(
                    Count('id', filter=Q(direction='outbound')), 0
                ),
            ).distinct()
            
            # Calculate total usage for this company
            total_inbound_usage = Decimal('0.00')
            total_outbound_usage = Decimal('0.00')

            for location in company_locations:
                inbound_rate = location.get('conversation__location__inbound_rate') or Decimal('0.00')
                outbound_rate = location.get('conversation__location__outbound_rate') or Decimal('0.00')

                total_inbound_usage += inbound_rate * location.get('location_inbound_messages', 0)
                total_outbound_usage += outbound_rate * location.get('location_outbound_messages', 0)

            total_usage = total_inbound_usage + total_outbound_usage

            results.append({
                'company_name': company['company_name'],
                'company_id': company_id,
                'total_inbound_segments': company['total_inbound_segments'],
                'total_outbound_segments': company['total_outbound_segments'],
                'total_inbound_messages': company['total_inbound_messages'],
                'total_outbound_messages': company['total_outbound_messages'],
                'total_inbound_usage': total_inbound_usage,
                'total_outbound_usage': total_outbound_usage,
                'locations_count': company['locations_count'],
                'total_usage': total_usage
            })
            
        return results

    @action(detail=False, methods=['post'], url_path='usage-analytics')
    def get_usage_analytics(self, request):
        """
        Get SMS usage analytics based on view type and filters
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
                serializer = AccountViewSerializer(data, many=True)
            else:  # company view
                data = self.get_company_view_data(filters)
                serializer = CompanyViewSerializer(data, many=True)
            
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
        Get overall usage summary statistics
        """
        try:
            # Get overall statistics
            total_stats = TextMessage.objects.aggregate(
                total_messages=Count('id'),
                total_segments=Sum('segments'),
                total_inbound_messages=Count('id', filter=Q(direction='inbound')),
                total_outbound_messages=Count('id', filter=Q(direction='outbound')),
                total_inbound_segments=Sum('segments', filter=Q(direction='inbound')),
                total_outbound_segments=Sum('segments', filter=Q(direction='outbound')),
            )
            
            # Get company and location counts
            company_count = GHLAuthCredentials.objects.values('company_id').distinct().count()
            location_count = GHLAuthCredentials.objects.count()
            
            summary = {
                'total_companies': company_count,
                'total_locations': location_count,
                'total_messages': total_stats['total_messages'] or 0,
                'total_segments': total_stats['total_segments'] or 0,
                'total_inbound_messages': total_stats['total_inbound_messages'] or 0,
                'total_outbound_messages': total_stats['total_outbound_messages'] or 0,
                'total_inbound_segments': total_stats['total_inbound_segments'] or 0,
                'total_outbound_segments': total_stats['total_outbound_segments'] or 0,
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
        credentials_to_update = GHLAuthCredentials.objects.filter(
            models.Q(inbound_rate__isnull=True) | 
            models.Q(outbound_rate__isnull=True) | 
            models.Q(currency__isnull=True) |
            models.Q(currency='')
        )
        
        # Update records with new defaults
        update_count = 0
        for credential in credentials_to_update:
            updated = False
            if not credential.inbound_rate:
                credential.inbound_rate = config.default_inbound_rate
                updated = True
            if not credential.outbound_rate:
                credential.outbound_rate = config.default_outbound_rate
                updated = True
            if not credential.inbound_call_rate:
                credential.inbound_call_rate = config.default_call_inbound_rate
                updated = True
            if not credential.outbound_call_rate:
                credential.outbound_call_rate = config.default_call_outbound_rate
                updated = True
            if not credential.currency:
                credential.currency = config.default_currency
                updated = True
            
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