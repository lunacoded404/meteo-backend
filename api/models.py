# backend/api/models.py
from django.db import models
from django.contrib.auth.models import User


class Province(models.Model):
    id = models.IntegerField(primary_key=True)
    code = models.CharField(max_length=50, null=True, blank=True, unique=True)
    name = models.CharField(max_length=255, null=True, blank=True)
    level = models.CharField(max_length=50, null=True, blank=True)
    lon = models.FloatField(null=True, blank=True, db_column="long")
    lat = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = "provinces"
        managed = False  # bảng đã có sẵn trên Supabase


class WeatherForecastHourly(models.Model):
    """
    Bảng lưu thời tiết theo giờ cho từng tỉnh.
    Được đổ dữ liệu bởi fetch_open_meteo.py.
    """

    id = models.BigAutoField(primary_key=True)
    province = models.ForeignKey(
        Province,
        on_delete=models.DO_NOTHING,
        db_column="province_id",
        related_name="hourly_forecasts",
    )
    forecast_time = models.DateTimeField()

    temp_c = models.FloatField(null=True, blank=True)
    humidity_percent = models.FloatField(null=True, blank=True)
    pressure_hpa = models.FloatField(null=True, blank=True)
    wind_speed_ms = models.FloatField(null=True, blank=True)
    wind_dir_deg = models.FloatField(null=True, blank=True)
    cloud_cover_percent = models.FloatField(null=True, blank=True)
    precip_mm = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "weather_forecast_hourly"
        managed = False
        indexes = [
            models.Index(fields=["province", "forecast_time"]),
        ]

    def __str__(self):
        return f"{self.province_id} @ {self.forecast_time}"


class ForecastCache(models.Model):
    cache_key = models.TextField(unique=True)
    lat = models.FloatField()
    lon = models.FloatField()
    forecast_days = models.IntegerField(default=10)
    timezone = models.TextField(null=True, blank=True)
    payload = models.JSONField()
    fetched_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "forecast_cache"

    




# Role of user (admin/user)


class UserRole(models.Model):
    ROLE_CHOICES = [
        ("user", "User"),
        ("admin", "Admin"),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="role")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default="user")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username}:{self.role}"
    

# Admin

# Layers management


class MapLayer(models.Model):
    key = models.CharField(max_length=40, unique=True)      # temp|wind|rain|humidity|cloud
    name = models.CharField(max_length=80)                  # label hiển thị (Nhiệt Độ, Gió...)
    is_enabled = models.BooleanField(default=True)
    icon = models.CharField(max_length=60, default="Thermometer")  # tên icon lucide

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key

# Phường xã

class Place(models.Model):
    code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    kind = models.CharField(max_length=64, default="hcm_district")
    lat = models.FloatField()
    lon = models.FloatField()
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "places"

    def __str__(self):
        return f"{self.code} - {self.name}"

