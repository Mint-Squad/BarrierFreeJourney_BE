from rest_framework import serializers
from main.models.models import TravelRequest, TravelSchedule, ScheduleItem

class ScheduleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScheduleItem
        fields = ['id', 'place_name', 'place_id', 'date', 'start_time', 'end_time', 'lat', 'lng', 'transport_type', 'address']
        read_only_fields = fields

class TravelScheduleSerializer(serializers.ModelSerializer):
    items = ScheduleItemSerializer(many=True, read_only=True)
    class Meta:
        model = TravelSchedule
        fields = ['id', 'travel_request', 'version', 'created_at', 'items']
        read_only_fields = fields
