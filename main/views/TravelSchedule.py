from rest_framework import viewsets, generics, permissions, status
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from django.db import transaction

from main.models.models import TravelRequest, TravelSchedule, ScheduleItem, Place
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
        travel_request_id_str = request.data.get("travel_request")
        if not travel_request_id_str:
            return Response({"result": "error", "message": "travel_request ID is required."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            travel_request_id = int(travel_request_id_str)
        except ValueError:
            return Response({"result": "error", "message": "Invalid travel_request ID format."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Gemini 호출 및 데이터 파싱 (이 부분은 트랜잭션 외부에서 수행해도 됨)
        try:
            # 이 부분은 트랜잭션 외부로 빼는 것이 좋습니다. API 호출은 시간이 오래 걸릴 수 있습니다.
            # 먼저 tr_obj를 가져오고, Gemini 호출 후, DB 작업을 트랜잭션으로 묶습니다.
            _tr_obj_for_gemini = get_object_or_404(TravelRequest, pk=travel_request_id, user=request.user)
            raw_json = generate_travel_schedule_from_gemini(_tr_obj_for_gemini)
            schedule_data = json.loads(raw_json)

            error_message_from_gemini = schedule_data.get("error_message")
            if error_message_from_gemini:
                logger.warning(
                    f"Gemini reported an error for TR ID {_tr_obj_for_gemini.id}: {error_message_from_gemini}")
                return Response(
                    {"result": "info", "message": error_message_from_gemini},
                    status=status.HTTP_200_OK
                )
            schedule_items = schedule_data.get('schedule_items', [])
            if not schedule_items and not error_message_from_gemini:  # 아이템이 없는데 에러 메시지도 없는 경우
                logger.info(
                    f"Gemini returned an empty schedule_items list for TR ID {_tr_obj_for_gemini.id} without an error message.")
                return Response(
                    {"result": "info",
                     "message": "AI could not generate any schedule items based on the available places."},
                    status=status.HTTP_200_OK
                )

        # Gemini API 호출 관련 예외 처리 (이전 답변의 예외 처리 블록 사용)
        except ValueError as e:  # API 키 설정 오류, 유효하지 않은 기간 등
            logger.error(f"Configuration or input error for TR ID {travel_request_id} before/during Gemini call: {e}")
            return Response({"result": "error", "message": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except ConnectionAbortedError as e:  # Places API 접근 거부
            logger.error(f"Places API access denied for TR ID {travel_request_id}: {e}")
            return Response({"result": "error",
                             "message": "There was an issue accessing place information. Please check API key and permissions."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except RuntimeError as e:  # API 클라이언트 초기화 실패 등
            logger.error(f"Runtime error during service initialization for TR ID {travel_request_id}: {e}")
            return Response({"result": "error", "message": "A service required for scheduling failed to initialize."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:  # 기타 예상치 못한 오류
            logger.exception(f"Unexpected error during Gemini schedule generation for TR ID {travel_request_id}: {e}")
            return Response(
                {"result": "error", "message": "An unexpected error occurred while generating the schedule."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # --- 데이터베이스 작업 시작 ---
        try:
            with transaction.atomic():
                # 트랜잭션 내에서 TravelRequest 객체를 다시 가져오면서 lock을 겁니다.
                # 이렇게 하면 다른 트랜잭션이 이 TravelRequest에 대한 TravelSchedule 생성을 시도할 때 대기하게 됩니다.
                tr_obj = TravelRequest.objects.select_for_update().get(pk=travel_request_id, user=request.user)

                # 버전 번호 결정 (이제 이 로직은 lock이 걸린 상태에서 실행됨)
                last_schedule = TravelSchedule.objects.filter(travel_request=tr_obj).order_by("-version").first()
                version = last_schedule.version + 1 if last_schedule else 1

                # TravelSchedule 생성
                new_schedule = TravelSchedule.objects.create(travel_request=tr_obj, version=version)

                items_to_create = []
                for item_data in schedule_items:
                    try:
                        place = Place.objects.get(place_id=item_data["place_id"])
                    except Place.DoesNotExist:
                        logger.warning(
                            f"Skipping schedule item, Place not found in DB for place_id={item_data.get('place_id')}"
                        )
                        continue

                    items_to_create.append(
                        ScheduleItem(
                            schedule=new_schedule,
                            place=place,
                            date=item_data.get("date"),
                            start_time=item_data.get("start_time"),
                            end_time=item_data.get("end_time"),
                            transport_type=item_data.get("transport_type", ""),
                            #description=item_data.get("description", "")\
                        )
                    )

                if items_to_create:
                    ScheduleItem.objects.bulk_create(items_to_create)
                else:
                    logger.info(
                        f"No valid schedule items to save for TR ID {tr_obj.id}, version {version}."
                    )


        except TravelRequest.DoesNotExist:  # select_for_update().get()에서 발생 가능
            return Response({"result": "error", "message": "Travel request not found or access denied."},
                            status=status.HTTP_404_NOT_FOUND)
        except Exception as e:  # 데이터베이스 저장 중 오류 (IntegrityError 포함)
            logger.exception(f"Database error while saving schedule for TR ID {travel_request_id}: {e}")
            # 트랜잭션은 자동으로 롤백됨
            return Response(
                {"result": "error", "message": "Failed to save the generated schedule due to a database issue."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 생성된 스케줄 응답
        serializer = self.get_serializer(new_schedule)  # new_schedule이 정의되었는지 확인 필요 (위 로직상 정의됨)
        return Response({"result": "success", "schedule": serializer.data}, status=status.HTTP_201_CREATED)


class TravelScheduleListView(generics.ListAPIView):
    """
    [GET] /travel/schedule/{request_id}/
    요청별 생성된 모든 여행 스케줄을 버전 순으로 조회합니다.
    """
    permission_classes = [permissions.IsAuthenticated]
    #renderer_classes   = [JSONRenderer]
    serializer_class = TravelScheduleSerializer
    lookup_url_kwarg = 'request_id'

    def get_queryset(self):
        tr = get_object_or_404(TravelRequest, pk=self.kwargs['request_id'], user=self.request.user)

        return TravelSchedule.objects.filter(travel_request=tr).order_by('version')

    def list(self, request, *args, **kwargs):
        schedules=self.get_queryset()
        result=[]
        for schedule in schedules:
            items = schedule.items.all().order_by('date', 'start_time')
            serialized_items = ScheduleItemSerializer(items, many=True).data
            result.append({
                'schedule_id': schedule.id,
                'request_id': schedule.travel_request.id,
                'version': schedule.version,
                'created_at': schedule.created_at.isoformat(),
                'items': serialized_items,
            })

        return Response({'result': 'success', 'schedules': result}, status=status.HTTP_200_OK)

class TravelScheduleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    [GET]    /travel/schedule/{request_id}/{version}/ — 특정 버전의 여행 스케줄 조회
    [PUT] [PATCH] /travel/schedule/{request_id}/{version}/ — 해당 버전의 스케줄 수정
    [DELETE] /travel/schedule/{request_id}/{version}/ — 해당 버전의 스케줄 삭제
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = TravelScheduleSerializer
    lookup_url_kwarg='version'
    lookup_field = 'version'

    def get_queryset(self):
        tr = get_object_or_404(TravelRequest,
                               pk=self.kwargs['request_id'],
                               user=self.request.user)
        return TravelSchedule.objects.filter(travel_request=tr)

    def delete(self, request, *args, **kwargs):
        schedule=self.get_object()
        schedule.delete()
        return Response(
            {'result': 'success', 'message': 'Schedule deleted'},
            status=status.HTTP_204_NO_CONTENT
        )
    def put(self, request, *args, **kwargs):
        schedule=self.get_object()
        items_data=request.data.get('items')
        if not isinstance(items_data, list):
            return Response(
                {'result': 'error', 'message': 'Invalid items data format'},
                status=HTTP_400_BAD_REQUEST
            )
        try:
            with transaction.atomic():
                schedule.items.all().delete()
                new_schedule_items=[]
                for item in items_data:
                    place_id=item.get('place_id')
                    try:
                        place_instance=Place.objects.get(place_id=place_id)
                    except Place.DoesNotExist:
                        logger.warning(
                            f"Place with place_id {place_id} not found in DB for schedule {schedule.id} during PUT. Skipping item.")
                        continue
                    # ScheduleItem 생성
                    new_schedule_items.append(
                        ScheduleItem(
                            schedule=schedule,
                            place=place_instance,  # ForeignKey로 조회된 Place 객체 연결
                            date=item.get('date'),
                            start_time=item.get('start_time'),
                            end_time=item.get('end_time'),
                            transport_type=item.get('transport_type', "")
                        )
                    )
                if new_schedule_items:
                    ScheduleItem.objects.bulk_create(new_schedule_items)
                else:
                    # 모든 아이템이 place_id가 없거나 Place 정보를 가져올 수 없는 경우
                    logger.info(f"No valid schedule items to create for schedule {schedule.id} during PUT.")

        except Exception as e:  # 데이터베이스 오류 또는 기타 예외 처리
            logger.exception(f"Error during PUT operation for schedule {schedule.id}: {e}")
            return Response(
                {'result': 'error', 'message': f'An error occurred while updating the schedule: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        updated_schedule = self.get_object()  # 변경사항이 반영된 객체를 다시 가져옴
        serializer = self.get_serializer(updated_schedule)
        return Response(
            {'result': 'success', 'schedule': serializer.data},
            status=status.HTTP_200_OK
        )

    def patch(self, request, *args, **kwargs):
        return self.put(request, *args, **kwargs)
