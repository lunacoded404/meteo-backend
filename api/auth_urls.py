# api/auth_urls.py
from django.urls import path
from .auth_views import register, login, me

urlpatterns = [
    path("register/", register),
    path("login/", login),
    path("me/", me),
]
