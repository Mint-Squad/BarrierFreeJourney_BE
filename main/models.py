from django.db import models
from django.contrib.auth.models import User
# Create your models here.

class TravelRequest(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE)
    country=models.CharField(max_length=50)
    cities=models.JSONField(default=dict)
    start_date=models.DateField()
    end_date=models.DateField()
    transportation=models.JSONField(default=dict)
    max_distance=models.IntegerField()
    interests=models.JSONField(default=dict)
    mood=models.JSONField(default=dict)
    created_at=models.DateTimeField(auto_now_add=True)

class TravelSchedule(models.Model):
    request=models.ForeignKey(TravelRequest,on_delete=models.CASCADE)
    version=models.PositiveIntegerField()
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together=('request','version')

class ScheduleItem(models.Model):
    schedule=models.ForeignKey(TravelSchedule,on_delete=models.CASCADE)
    place_name=models.CharField(max_length=100)
    place_id=models.IntegerField()
    date=models.DateField()
    start_time=models.TimeField()
    end_time=models.TimeField()
    lat=models.FloatField()
    lng=models.FloatField()
    transport_type=models.CharField(max_length=100)
    address=models.CharField(max_length=100)