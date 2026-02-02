from rest_framework import serializers
from .models import MapLayer
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password


# Quản lý layers
class MapLayerAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = MapLayer
        fields = ["id","key","name","is_enabled","icon"]
        read_only_fields = ["id","key","name"]

# Quản lý users account

User = get_user_model()

class AdminUserSerializer(serializers.ModelSerializer):
    # ✅ tạo mới: bắt buộc có password, min 6
    password = serializers.CharField(
        write_only=True,
        required=False,     # sẽ bắt buộc ở create()
        min_length=6,
        style={"input_type": "password"},
    )

    # ✅ role: dùng is_staff (Admin=True, User=False)
    is_staff = serializers.BooleanField(required=False)

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff", "password"]
        extra_kwargs = {
            "username": {"required": True},
            "email": {"required": False, "allow_blank": True},
        }

    def validate_username(self, value: str):
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("username không được rỗng")
        return value

    def validate_email(self, value: str):
        return (value or "").strip()

    def validate_password(self, value: str):
        # ✅ đảm bảo tối thiểu 6 (field đã min_length=6)
        # validate_password sẽ áp dụng nếu bạn cấu hình AUTH_PASSWORD_VALIDATORS
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password or len(password) < 6:
            raise serializers.ValidationError({"password": "Password tối thiểu 6 ký tự."})

        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        # ✅ không cập nhật password bằng PATCH thường (để an toàn)
        validated_data.pop("password", None)

        request = self.context.get("request")
        # ✅ chặn tự hạ quyền chính mình
        if request and request.user and instance.pk == request.user.pk:
            if "is_staff" in validated_data and validated_data["is_staff"] is False:
                raise serializers.ValidationError({"is_staff": "Không thể tự hạ quyền admin của chính bạn."})

        return super().update(instance, validated_data)
