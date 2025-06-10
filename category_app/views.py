from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from .models import Category
from .serializers import CategorySerializer, CategoryCreateUpdateSerializer

class CategoryListCreateView(generics.ListCreateAPIView):
    """
    GET: List all categories
    POST: Create a new category
    """
    queryset = Category.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return CategoryCreateUpdateSerializer
        return CategorySerializer
    
    def get_queryset(self):
        queryset = Category.objects.all()
        
        # Filter by active status if requested
        is_active = self.request.query_params.get('is_active', None)
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == 'true')
        
        # Search by category name
        search = self.request.query_params.get('search', None)
        if search:
            queryset = queryset.filter(category_name__icontains=search)
            
        return queryset
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            category = serializer.save()
            response_serializer = CategorySerializer(category)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class CategoryRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET: Retrieve a specific category
    PUT/PATCH: Update a specific category
    DELETE: Delete a specific category
    """
    queryset = Category.objects.all()
    permission_classes = [IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return CategoryCreateUpdateSerializer
        return CategorySerializer
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if serializer.is_valid():
            category = serializer.save()
            response_serializer = CategorySerializer(category)
            return Response(response_serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        
        # Check if category has associated locations
        if instance.locations.exists():
            return Response(
                {"error": "Cannot delete category with associated locations. Please reassign or remove locations first."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
