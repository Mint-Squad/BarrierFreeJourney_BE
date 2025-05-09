from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from main.models.models import TravelRequest, TravelSchedule, ScheduleItem
from django.shortcuts import get_object_or_404
import json, logging
from main.serializers.TravelSchedule import TravelScheduleSerializer, ScheduleItemSerializer
from main.services.gemini_api import generate_travel_schedule_from_gemini

logger = logging.getLogger(__name__) # 로거 설정

class TravelScheduleCreateView(generics.CreateAPIView):
    """
    [POST] /travel/schedule/ — TravelRequest ID에 기반하여 새로운 버전의 여행 스케줄을 생성합니다.
    Request body: { "travel_request": <request_id> }
    """
    serializer_class = TravelScheduleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def create(self, request, *args, **kwargs):
        tr = get_object_or_404(TravelRequest, pk=request.data.get("travel_request"), user=request.user)
        last_schedule = TravelSchedule.objects.filter(travel_request=tr).order_by("-version").first()
        version = last_schedule.version + 1 if last_schedule else 1

        # Gemini 호출
        raw_json = generate_travel_schedule_from_gemini(tr)
        schedule_data = json.loads(raw_json)
        items = schedule_data.get('schedule_items', [])

        # TravelSchedule 및 ScheduleItem 생성
        schedule = TravelSchedule.objects.create(travel_request=tr, version=version)
        for item in items:
            ScheduleItem.objects.create(
                schedule=schedule,
                place_name=item["place_name"],
                place_id=item["place_id_from_ai"],
                date=item["date"],
                start_time=item["start_time"],
                end_time=item["end_time"],
                lat=item["lat"],
                lng=item["lng"],
                transport_type=item["transport_type"],
                address=item["address"],
            )
        # 생성된 ScheduleItem을 시리얼라이즈
        serialized_items = ScheduleItemSerializer(schedule.scheduleitem_set.all().all(), many=True).data

        schedule_data = {
            'schedule_id': schedule.id,
            'request_id': tr.id,
            'version': schedule.version,
            'created_at': schedule.created_at.isoformat(),
            'items': serialized_items,
        }
        return Response({"result": "success", "schedule": schedule_data}, status=status.HTTP_201_CREATED)

class TravelScheduleListView(generics.ListAPIView):
    """
    [GET] /travel/schedule/{request_id}/ — 요청별 생성된 모든 여행 스케줄을 버전 순으로 조회합니다.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, request_id, *args, **kwargs):
        tr = get_object_or_404(TravelRequest, pk=request_id, user=request.user)
        schedules = TravelSchedule.objects.filter(travel_request=tr).order_by('version')

        result = []
        for schedule in schedules:
            items = schedule.scheduleitem_set.all().order_by('date', 'start_time')
            serialized_items = ScheduleItemSerializer(items, many=True).data
            result.append({
                'schedule_id': schedule.id,
                'request_id': tr.id,
                'version': schedule.version,
                'created_at': schedule.created_at.isoformat(),
                'items': serialized_items,
            })

        return Response({'result': 'success', 'schedules': result}, status=status.HTTP_200_OK)

class TravelScheduleDetailView(generics.RetrieveAPIView):
    """
    [GET] /travel/schedule/{request_id}/{version}/ — 특정 버전의 여행 스케줄 조회
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, request_id, version, *args, **kwargs):
        tr = get_object_or_404(TravelRequest, pk=request_id, user=request.user)
        schedule = get_object_or_404(TravelSchedule, travel_request=tr, version=version)
        items = schedule.scheduleitem_set.all().order_by('date','start_time')
        serialized_items = ScheduleItemSerializer(items, many=True).data

        schedule_data = {
            'schedule_id': schedule.id,
            'request_id': tr.id,
            'version': schedule.version,
            'created_at': schedule.created_at.isoformat(),
            'items': serialized_items,
        }
        return Response({'result': 'success', 'schedule': schedule_data}, status=status.HTTP_200_OK)


class ScheduleItemViewSet(viewsets.ModelViewSet):
    queryset = ScheduleItem.objects.all()
    serializer_class = ScheduleItemSerializer
