from rest_framework import serializers
from main.models.models import TravelSchedule, ScheduleItem, Place


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "place_id", "name", "address", "lat", "lng",
            "wheelchair_entrance", "updated_at",
        ]
        read_only_fields = fields
class ScheduleItemSerializer(serializers.ModelSerializer):
    place=PlaceSerializer(read_only=True)
    class Meta:
        model = ScheduleItem
        fields = ['id', 'place', 'date',
                  'start_time', 'end_time',
                  'transport_type']
        read_only_fields = fields

class TravelScheduleSerializer(serializers.ModelSerializer):
    items = ScheduleItemSerializer(many=True, read_only=True)
    class Meta:
        model = TravelSchedule
        fields = ['id', 'travel_request', 'version', 'created_at', 'items']
        extra_kwargs={
            'id':{'source' : 'pk' },
        }
        read_only_fields = fields
