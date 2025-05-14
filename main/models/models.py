from email.policy import default

from django.db import models
from django.contrib.auth.models import User
# Create your models here.
class Place(models.Model):
    place_id = models.CharField(max_length=255, primary_key=True)
    name     = models.CharField(max_length=200)
    address  = models.TextField(blank=True)
    lat      = models.FloatField()
    lng      = models.FloatField()
    # 휠체어 접근성 세부 정보
    wheelchair_entrance = models.BooleanField(null=True)

    updated_at = models.DateTimeField(auto_now=True)

class TravelRequest(models.Model):
    user=models.ForeignKey(User,on_delete=models.CASCADE, null=True, blank=True)

    country=models.CharField(max_length=50)
    cities=models.JSONField(default=list)

    start_date=models.DateField()
    end_date=models.DateField()

    transportation=models.JSONField(default=list)
    max_distance=models.IntegerField(default=0)

    interests=models.JSONField(default=list)
    mood=models.JSONField(default=list)

    selected_places=models.ManyToManyField(
        Place,
        blank=True,
        related_name="requested_by",
        help_text="사용자가 여행에 포함하기로 선택한 장소(Place 객체 참조)"
       )
    created_at=models.DateTimeField(auto_now_add=True)

class TravelSchedule(models.Model):
    travel_request=models.ForeignKey(TravelRequest,on_delete=models.CASCADE)
    version=models.PositiveIntegerField()
    created_at=models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together=('travel_request','version')

class ScheduleItem(models.Model):
    schedule=models.ForeignKey(TravelSchedule,on_delete=models.CASCADE, related_name='items')
    place=models.ForeignKey(Place,on_delete=models.PROTECT, related_name='schedule_items')
    date=models.DateField()
    start_time=models.TimeField()
    end_time=models.TimeField()
    transport_type=models.CharField(max_length=100)


