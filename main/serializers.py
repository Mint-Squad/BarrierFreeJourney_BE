from rest_framework import serializers
from .models import TravelRequest, TravelSchedule, ScheduleItem

class ScheduleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleItem
        fields = '__all__'

class TravelScheduleSerializer(serializers.ModelSerializer):
    items = ScheduleItemSerializer(many=True, read_only=True)

    class Meta:
        model = TravelSchedule
        fields = '__all__'

class TravelRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelRequest
        fields = '__all__'
