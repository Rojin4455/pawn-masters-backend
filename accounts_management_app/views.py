from rest_framework import generics, permissions
from core.models import GHLAuthCredentials
from .serializers import GHLAuthCredentialsSerializer


class GHLAuthCredentialsListView(generics.ListAPIView):
    queryset = GHLAuthCredentials.objects.all()
    serializer_class = GHLAuthCredentialsSerializer
    permission_classes = [permissions.IsAuthenticated]


class GHLAuthCredentialsDetailUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = GHLAuthCredentials.objects.all()
    serializer_class = GHLAuthCredentialsSerializer
    lookup_field = 'location_id'
    permission_classes = [permissions.IsAuthenticated]