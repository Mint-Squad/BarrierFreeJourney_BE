from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from main.models.models import TravelRequest
from main.serializers.request import (
    TravelRequestSerializer,
    TravelRequestCreateSerializer,
    TravelRequestUpdateSerializer,
    TravelRequestDetailSerializer)

class TravelRequestCreateView(generics.CreateAPIView):
    """
    [POST] /travel/request/ — 여행 요청 생성
    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = TravelRequestCreateSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # user 할당 후 저장
        travel_request = serializer.save(user=request.user)
        # 응답 포맷
        output = TravelRequestSerializer(travel_request).data
        return Response(
            {"result": "success", "travel_request": output},
            status=status.HTTP_201_CREATED
        )

class TravelRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    [GET]    /travel/request/{request_id}/  상세 조회
    [PUT]    /travel/request/{request_id}/  수정
    [DELETE] /travel/request/{request_id}/  삭제
    """
    permission_classes = [permissions.IsAuthenticated]
    queryset = TravelRequest.objects.all()
    lookup_field = 'pk'
    lookup_url_kwarg = 'request_id'

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return TravelRequestDetailSerializer
        if self.request.method in ['PUT', 'PATCH']:
            return TravelRequestUpdateSerializer
        return TravelRequestDetailSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        # 작성자 체크
        if instance.user != request.user:
            raise PermissionDenied("작성자만 수정할 수 있습니다.")
        serializer = self.get_serializer(instance, data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({"result": "success"},
                        status=status.HTTP_200_OK)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # 작성자 체크
        if instance.user != request.user:
            raise PermissionDenied("작성자만 삭제할 수 있습니다.")
        self.perform_destroy(instance)
        return Response({"result": "success"},
                        status=status.HTTP_200_OK)