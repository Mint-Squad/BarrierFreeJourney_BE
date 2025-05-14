from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from main.models.models import TravelRequest
from main.serializers.TravelRequest import (
    TravelRequestCreateSerializer,
    TravelRequestUpdateSerializer,
    TravelRequestDetailSerializer)

class TravelRequestCreateView(generics.CreateAPIView):
    """
    [POST] /travel/request/ — 여행 요청 생성
    """
    permission_classes = [permissions.AllowAny]
    serializer_class = TravelRequestCreateSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # user 할당 후 저장
        travel_request = serializer.save()
        # 응답 포맷
        output = TravelRequestCreateSerializer(travel_request).data
        return Response(
            {"result": "success", "travel_request": output},
            status=status.HTTP_201_CREATED
        )

class TravelRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    [GET]    /travel/request/{request_id}/
    [PUT]    /travel/request/{request_id}/
    [PATCH]  /travel/request/{request_id}/
    [DELETE] /travel/request/{request_id}/
    """
    permission_classes = [permissions.AllowAny]
    queryset = TravelRequest.objects.all()
    lookup_field = 'pk'
    lookup_url_kwarg = 'request_id'

    def get_serializer_class(self):
        if self.request.method in ['PUT', 'PATCH']:
            return TravelRequestUpdateSerializer
        return TravelRequestDetailSerializer

    # 수정 후 success만 보낼 때
    # def get_serializer_class(self):
    #     if self.request.method == 'GET':
    #         return TravelRequestDetailSerializer
    #     if self.request.method in ['PUT', 'PATCH']:
    #         return TravelRequestUpdateSerializer
    #     return TravelRequestDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        data = TravelRequestDetailSerializer(instance).data
        return Response(
            {"result": "success", "travel_request": data},
            status=status.HTTP_200_OK
        )

    def update(self, request, *args, **kwargs):
        # PUT / PATCH 둘 다 여기로 들어오므로 partial 플래그에 따라 처리
        partial = kwargs.pop('partial', False)

        instance = self.get_object()

        # 작성자 체크
        #if instance.user != request.user:
        #    raise PermissionDenied("작성자만 수정할 수 있습니다.")

        serializer = self.get_serializer(
            instance, data=request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        # 최신화된 인스턴스로 다시 상세 직렬화
        data = TravelRequestDetailSerializer(instance).data
        return Response(
            {"result": "success", "travel_request": data},
            status=status.HTTP_200_OK
        )

    def partial_update(self, request, *args, **kwargs):
        # DRF가 PATCH 요청 시 호출하도록 연결
        return self.update(request, *args, **kwargs, partial=True)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        #if instance.user != request.user:
        #    raise PermissionDenied("작성자만 삭제할 수 있습니다.")
        self.perform_destroy(instance)
        return Response(
            {"result": "success"},
            status=status.HTTP_200_OK
        )