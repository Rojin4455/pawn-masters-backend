from django.urls import path, include
from .views import (
    GHLAuthCredentialsListView,
    GHLAuthCredentialsDetailUpdateDeleteView,
    SMSConfigurationViewSet,SMSAnalyticsViewSet, webhook_handler,
    WalletSyncView,CallSyncView
)

from rest_framework.routers import DefaultRouter

router = DefaultRouter()
router.register(r'analytics', SMSAnalyticsViewSet, basename='sms-analytics')
router.register(r'sms-config', SMSConfigurationViewSet, basename='sms-config')


urlpatterns = [
    path('ghl-auth/', GHLAuthCredentialsListView.as_view(), name='ghlauth-list'),
    path('ghl-auth/<str:location_id>/', GHLAuthCredentialsDetailUpdateDeleteView.as_view(), name='ghlauth-detail'),
    path('', include(router.urls)),
    path("webhook",webhook_handler),
    path('sync-wallets/', WalletSyncView.as_view(), name='sync-wallets'),
    path('sync-calls/', CallSyncView.as_view(), name='sync-calls'),
]