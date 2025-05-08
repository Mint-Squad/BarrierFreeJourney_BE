from django.shortcuts import render

from rest_framework import viewsets
from .models import TravelRequest, TravelSchedule, ScheduleItem
from .serializers import TravelRequestSerializer, TravelScheduleSerializer, ScheduleItemSerializer

class TravelRequestViewSet(viewsets.ModelViewSet):
    queryset = TravelRequest.objects.all()
    serializer_class = TravelRequestSerializer

class TravelScheduleViewSet(viewsets.ModelViewSet):
    queryset = TravelSchedule.objects.all()
    serializer_class = TravelScheduleSerializer

class ScheduleItemViewSet(viewsets.ModelViewSet):
    queryset = ScheduleItem.objects.all()
    serializer_class = ScheduleItemSerializer
