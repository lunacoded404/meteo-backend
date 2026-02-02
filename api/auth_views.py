# api/auth_views.py
from django.contrib.auth import authenticate
from django.contrib.auth.models import User

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken

from django.db import transaction
from .models import UserRole


@api_view(["POST"])
@permission_classes([AllowAny])
def register(request):
    email = (request.data.get("email") or "").strip().lower()
    password = (request.data.get("password") or "").strip()
    username = (request.data.get("username") or "").strip() or email

    if not email or not password:
        return Response({"detail": "Missing email/password"}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(username=username).exists():
        return Response({"detail": "Username already exists"}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists():
        return Response({"detail": "Email already exists"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        with transaction.atomic():
            user = User.objects.create_user(username=username, email=email, password=password)

            # ✅ auto gán role mặc định = user
            UserRole.objects.create(user=user, role="user")

        return Response({"id": user.id, "username": user.username, "email": user.email}, status=status.HTTP_201_CREATED)

    except Exception as e:
        # nếu insert role fail thì rollback cả user
        return Response({"detail": f"Register failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def login(request):
    username = (request.data.get("username") or "").strip()
    password = (request.data.get("password") or "").strip()

    if not username or not password:
        return Response({"detail": "Missing username/password"}, status=status.HTTP_400_BAD_REQUEST)

    user = authenticate(username=username, password=password)
    if not user:
        return Response({"detail": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "username": user.username,
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        },
        status=status.HTTP_200_OK
    )



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    u = request.user
    role = "user"
    r = UserRole.objects.filter(user=u).first()
    if r:
        role = r.role
    return Response({"id": u.id, "username": u.username, "email": u.email, "role": role}, status=status.HTTP_200_OK)

