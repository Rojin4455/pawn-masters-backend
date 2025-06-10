from django.urls import path
from .views import (
    GHLAuthCredentialsListView,
    GHLAuthCredentialsDetailUpdateDeleteView
)

urlpatterns = [
    path('ghl-auth/', GHLAuthCredentialsListView.as_view(), name='ghlauth-list'),
    path('ghl-auth/<str:location_id>/', GHLAuthCredentialsDetailUpdateDeleteView.as_view(), name='ghlauth-detail'),
]