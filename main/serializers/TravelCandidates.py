from rest_framework import serializers

class TravelCandidateSerializer(serializers.Serializer):
    place_id = serializers.CharField()
    place_name = serializers.CharField()
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    address = serializers.CharField()
    types = serializers.ListField(child=serializers.CharField(), required=False)
    searched_interest = serializers.CharField(required=False)
    searched_mood = serializers.CharField(required=False)
    wheelchair_details = serializers.JSONField(required=False)
    rating = serializers.FloatField(required=False)