from django.urls import path, include
from .views import (
    GHLAuthCredentialsListView,
    GHLAuthCredentialsDetailUpdateDeleteView,
    SMSConfigurationViewSet,SMSAnalyticsViewSet, webhook_handler,
    WalletSyncView,CallSyncView,CompanyAccountView,
    AccountDataForCompanyView,trigger_refresh_calls_task,trigger_refresh_conversations_task,make_api_call_view
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
    path('get-company-account/', CompanyAccountView.as_view()),
    path('get-company-account-only/', AccountDataForCompanyView.as_view()),
    path('refresh-calls/', trigger_refresh_calls_task, name='trigger-refresh-calls'),
    path('refresh-messages/', trigger_refresh_conversations_task, name='trigger-refresh-calls'),
    path('refresh-token/', make_api_call_view, name='trigger-refresh-calls'),
]