from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from main.models.models import TravelRequest
from django.shortcuts import get_object_or_404
import json, logging
from main.serializers.TravelCandidates import TravelCandidateSerializer
from main.services.gemini_api import generate_place

logger = logging.getLogger(__name__) # 로거 설정

class TravelCandidatesListView(APIView):
    """
    [GET] /travel/schedule/candidates/{request_id}/?interest=<관심사명>
    - interest 파라미터:
      - 없거나 '전체'인 경우: 모든 interest × mood 조합의 후보를 뿌립니다.
      - 특정 interest일 경우: 그 관심사에 대응하는 조합만 검색합니다.
    """
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request, *args, **kwargs):
        # 1) TravelRequest 객체 가져오기
        request_pk=int(kwargs.get('request_id'))
        tr=get_object_or_404(TravelRequest, pk=request_pk, user=request.user)
        # 2) 쿼리파라미터에서 필터링할 관심사 가져오기
        interest_filter = request.query_params.get('interest')
        # 3) places_api 기반 후보지 생성
        try:
            raw_json = generate_place(tr)  # JSON string
            all_places = json.loads(raw_json)  # list[dict]
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
    permission_classes = [permissions.IsAuthenticated]

    def _get_request(self, kwargs, user):
        request_pk = int(kwargs.get('request_id'))
        return get_object_or_404(TravelRequest, pk=request_pk, user=user)

    def _validate_list(self, lst):
        return isinstance(lst, list) and all(isinstance(item, str) for item in lst)
    def get(self, request, *args, **kwargs):
        tr=self._get_request(kwargs, request.user)
        return Response({"selected_place_ids":tr.selected_places})
    def post(self, request, *args, **kwargs):
        # 1) TravelRequest 객체 가져오기
        tr = self._get_request(kwargs, request.user)
        # 2) 선택된 장소들 받기
        selected_place_ids = request.data.get('selected_place_ids', [])
        if not self._validate_list(selected_place_ids):
            return Response(
                {"result": "error", "message": "Invalid selected_places format. Expected a list of dictionaries."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 3) 선택된 장소들을 TravelRequest에 저장
        tr.selected_places = selected_place_ids
        tr.save(update_fields=['selected_places'])

        return Response(
            {"result": "success", "message": "Selected place_ids saved successfully.",
                   "selected": tr.selected_places},
            status=status.HTTP_200_OK
        )
    put=post
    def patch(self, request, *args, **kwargs):
        tr = self._get_request(kwargs, request.user)
        current=set(tr.selected_places or [])

        to_add = request.data.get('add',[])
        to_remove = request.data.get('remove',[])
        if not self._validate_list(to_add) or not self._validate_list(to_remove):
            return Response(
                {"result": "error", "message": "Invalid add/remove"},
                 status=status.HTTP_400_BAD_REQUEST
            )
        current |= set(to_add)
        current -= set(to_remove)
        tr.selected_places = list(current)
        tr.save(update_fields=['selected_places'])
        return Response({"result": "success", "message": "Selected place_ids updated successfully.",
                         "selected": tr.selected_places})

    def delete(self, request, *args, **kwargs):
        tr = self._get_request(kwargs, request.user)
        tr.selected_places=[]
        tr.save(update_fields=['selected_places'])
        return Response({"result": "success", "message": "Selected place_ids deleted successfully."})