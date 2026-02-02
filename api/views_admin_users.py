from django.contrib.auth import get_user_model
from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAdminUser
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework import serializers

from api.serializers import AdminUserSerializer

User = get_user_model()

class SetPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(min_length=6, write_only=True)

class AdminUserViewSet(ModelViewSet):
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminUser]
    queryset = User.objects.all().order_by("-id")

    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, pk=None):
        user = self.get_object()
        ser = SetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user.set_password(ser.validated_data["password"])
        user.save()
        return Response({"ok": True}, status=status.HTTP_200_OK)
