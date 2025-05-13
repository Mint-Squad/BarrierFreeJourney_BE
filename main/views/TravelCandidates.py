from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from main.models.models import TravelRequest, Place
from django.shortcuts import get_object_or_404
import json, logging
from main.serializers.TravelCandidates import TravelCandidateSerializer
from main.services.gemini_api import generate_place
from main.services.places_api import get_place_details_with_wheelchair_info

logger = logging.getLogger(__name__) # 로거 설정

class TravelCandidatesListView(APIView):
    """
    [GET] /travel/schedule/candidates/{request_id}/?interest=<관심사명>
    - interest 파라미터:
      - 없거나 '전체'인 경우: 모든 interest × mood 조합의 후보를 뿌립니다.
      - 특정 interest일 경우: 그 관심사에 대응하는 조합만 검색합니다.
    """
    permission_classes = []
    def get(self, request, *args, **kwargs):
        # 1) TravelRequest 객체 가져오기
        request_pk=int(kwargs.get('request_id'))
        tr=get_object_or_404(TravelRequest, pk=request_pk)
        # 2) 쿼리파라미터에서 필터링할 관심사 가져오기
        interest_filter = request.query_params.get('interest')
        # 3) places_api 기반 후보지 생성
        try:
            raw_json = generate_place(tr)  # JSON string
            all_places = json.loads(raw_json)  # list[dict]
            for p in all_places:
                Place.objects.update_or_create(place_id=p['place_id'],
                                               defaults={
                                                   'name': p['name'],
                                                   'address': p['address'],
                                                   'lat': p['lat'],
                                                   'lng': p['lng'],
                                                   'wheelchair_entrance': p.get('wheelchair_details', {}).get('wheelchair_entrance')

                                               })
        except ValueError as e:
            logger.error(f"Error generating places for TR {tr.id}: {e}")
            return Response(
                {"result": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # 4) interest별로 candidate를 다시 뽑아내기
        # generate_place 에서는 interest×mood 전체를 섞어서 반환하기 때문에
        # 여기서 관심사별 필터링을 수행합니다.
        if interest_filter and interest_filter.lower() != '전체':
            filtered = [
                p for p in all_places
                if p.get('searched_interest', '').lower() == interest_filter.lower()
            ]
        else:
            filtered = all_places

        serializer=TravelCandidateSerializer(filtered, many=True)
        return Response(
            {"result": "success", "count": len(filtered), "candidates": serializer.data},
            status=status.HTTP_200_OK
        )

class TravelCandidatesSelectView(APIView):
    """
    [POST] /travel/schedule/candidates/{request_id}/
    [PATCH] /travel/schedule/candidates/{request_id}/
    [PATCH] /travel/schedule/candidates/{request_id}/
    """
    permission_classes = []

    def _get_request(self, kwargs, user):
        request_pk = int(kwargs.get('request_id'))
        return get_object_or_404(TravelRequest, pk=request_pk)

    def _ensure_place(self, place_id):
        """
        place_id로 Place 인스턴스를 반환.
        존재하지 않으면 API 호출로 상세 정보를 가져와 새로 생성.
        실패 시 None 반환.
        """
        try:
            return Place.objects.get(place_id=place_id)
        except Place.DoesNotExist:
            details = get_place_details_with_wheelchair_info(place_id)
            if not details:
                return None
            # 필드 이름은 Place 모델에 맞춰 조정
            wheelchair_flag = details.get("wheelchair_entrance")
            return Place.objects.create(
                place_id=details["place_id"],
                name=details["name"],
                address=details["address"],
                lat=details["lat"],
                lng=details["lng"],
                wheelchair_entrance=wheelchair_flag
            )
    def get(self, request, *args, **kwargs):
        tr=self._get_request(kwargs, request.user)
        selected=list(tr.selected_places.values_list('place_id', flat=True))
        return Response({"selected_place_ids":selected})

    def post(self, request, *args, **kwargs):
        tr = self._get_request(kwargs, request.user)
        ids = request.data.get('selected_place_ids', [])
        if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
            return Response(
                {"result": "error", "message": "Invalid selected_places format. Expected a list of dictionaries."},
                status=status.HTTP_400_BAD_REQUEST
            )
        place_objs = []
        for pid in ids:
            place = self._ensure_place(pid)
            if place:
                place_objs.append(place)
            else:
                logger.warning(f"Place details not found or not accessible for place_id {pid}")

        # M2M 전체 교체
        tr.selected_places.set(place_objs)
        return Response(
            {"result": "success",
             "selected_place_ids": [p.place_id for p in place_objs]},
            status=status.HTTP_200_OK
        )
    put=post

    def patch(self, request, *args, **kwargs):
        tr = self._get_request(kwargs, request.user)
        to_add = request.data.get('add',[])
        to_remove = request.data.get('remove',[])
        if not isinstance(to_add, list) or not isinstance(to_remove, list):
            return Response(
                {"result": "error", "message": "Invalid add/remove"},
                 status=status.HTTP_400_BAD_REQUEST
            )
        # add: Place 인스턴스 확보 후 M2M 추가
        for pid in to_add:
            place = self._ensure_place(pid)
            if place:
                tr.selected_places.add(place)

        # remove: 이미 DB에 존재하는 것만 제거
        existing = Place.objects.filter(place_id__in=to_remove)
        if existing:
            tr.selected_places.remove(*existing)

        current = list(tr.selected_places.values_list('place_id', flat=True))
        return Response(
            {"result": "success", "selected_place_ids": current},
            status=status.HTTP_200_OK
        )

    def delete(self, request, *args, **kwargs):
        tr = self._get_request(kwargs, request.user)
        tr.selected_places.clear()
        return Response(
            {"result": "success", "selected_place_ids": []},
            status=status.HTTP_200_OK
        )
