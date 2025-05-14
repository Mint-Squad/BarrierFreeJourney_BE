from rest_framework import serializers
from main.models.models import TravelRequest, Place


# POST travel
class TravelRequestCreateSerializer(serializers.ModelSerializer):
    transportation = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    interests      = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    mood           = serializers.ListField(child=serializers.CharField(), required=False, default=list)
    max_distance   = serializers.IntegerField(required=False, default=0)

    class Meta:
        model = TravelRequest
        fields = [
            "country", "cities", "start_date", "end_date",
            "transportation", "max_distance", "interests", "mood",
        ]

# GET
class TravelRequestDetailSerializer(serializers.ModelSerializer):
    selected_places=serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Place.objects.all()
    )
    class Meta:
        model = TravelRequest
        fields = [
            "id", "country", "cities", "start_date", "end_date",
            "transportation", "max_distance", "interests", "mood",
            "selected_places", "created_at",
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