from rest_framework import serializers
from main.models.models import TravelRequest, TravelSchedule, ScheduleItem

# POST travel
class TravelRequestCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelRequest
        fields = [
            "country", "cities", "start_date", "end_date",
            "transportation", "max_distance", "interests", "mood",
        ]

# response of POST
class TravelRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelRequest
        fields = [
            "id", "country", "cities", "start_date", "end_date",
            "transportation", "max_distance", "interests", "mood",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

# GET
class TravelRequestDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelRequest
        fields = [
            "id", "user", "country", "cities", "start_date", "end_date",
            "transportation", "max_distance", "interests", "mood",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

# update PUT
class TravelRequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TravelRequest
        fields = [
            "country", "cities", "start_date", "end_date",
            "transportation", "max_distance", "interests", "mood",
        ]