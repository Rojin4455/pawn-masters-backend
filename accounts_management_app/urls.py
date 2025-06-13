from django.urls import path, include
from .views import (
    GHLAuthCredentialsListView,
    GHLAuthCredentialsDetailUpdateDeleteView,
    SMSConfigurationViewSet
)

from rest_framework.routers import DefaultRouter
from .views import SMSAnalyticsViewSet

router = DefaultRouter()
router.register(r'analytics', SMSAnalyticsViewSet, basename='sms-analytics')
router.register(r'sms-config', SMSConfigurationViewSet, basename='sms-config')


urlpatterns = [
    path('ghl-auth/', GHLAuthCredentialsListView.as_view(), name='ghlauth-list'),
    path('ghl-auth/<str:location_id>/', GHLAuthCredentialsDetailUpdateDeleteView.as_view(), name='ghlauth-detail'),
    path('', include(router.urls)),   
]