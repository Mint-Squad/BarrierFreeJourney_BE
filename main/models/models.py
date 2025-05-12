from email.policy import default

from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class TravelRequest(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)

    country=models.CharField(max_length=50)
    cities=models.JSONField(default=list)

    start_date=models.DateField()
    end_date=models.DateField()

    transportation=models.JSONField(default=list)
    max_distance=models.IntegerField(default=0)

    interests=models.JSONField(default=list)
    mood=models.JSONField(default=list)

    selected_places=models.JSONField(blank=True, null=True, default=list,
                          help_text="유저가 후보지 리스트에서 선택한 장소 정보를 JSON 형태로 저장")
    created_at=models.DateTimeField(auto_now_add=True)

class TravelSchedule(models.Model):
    travel_request=models.ForeignKey(TravelRequest,on_delete=models.CASCADE)
    version=models.PositiveIntegerField()
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together=('travel_request','version')

class ScheduleItem(models.Model):
    schedule=models.ForeignKey(TravelSchedule,on_delete=models.CASCADE, related_name='items')
    place_name=models.CharField(max_length=255)
    place_id=models.CharField(max_length=100, blank=True, null=True)
    date=models.DateField()
    start_time=models.TimeField()
    end_time=models.TimeField()
    lat=models.FloatField()
    lng=models.FloatField()
    transport_type=models.CharField(max_length=100)
    address=models.CharField(max_length=255)