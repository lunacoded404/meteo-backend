# # api/views.py
# from __future__ import annotations

# from datetime import date, datetime, timedelta
# import requests

# from django.db import connection
# from django.utils import timezone
# from django.core.cache import cache
# from django.http import Http404
# from rest_framework.response import Response
# from rest_framework import status
# from rest_framework.decorators import api_view
# from api.models import Place

# from rest_framework.decorators import api_view
# from .models import ForecastCache  # ✅ KHÔNG import Province vì model đang lệch schema

# OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"


# # =========================
# # Helpers
# # =========================
# def _om_get(lat: float, lon: float, params: dict):
#     base = {
#         "latitude": lat,
#         "longitude": lon,
#         "timezone": "auto",
#     }
#     base.update(params)
#     resp = requests.get(OPEN_METEO_BASE, params=base, timeout=15)
#     resp.raise_for_status()
#     return resp.json()


# def _parse_om_time(t_str: str):
#     # Open-Meteo thường trả kiểu "2025-12-11T23:00"
#     dt_naive = datetime.fromisoformat(t_str)
#     if dt_naive.tzinfo is None:
#         return timezone.make_aware(dt_naive, timezone.get_default_timezone())
#     return dt_naive


# def _latest_hour_value(om: dict, field: str):
#     """
#     Lấy giá trị hourly gần nhất tại/ trước 'now' (không lấy giờ tương lai).
#     """
#     hourly = om.get("hourly", {}) or {}
#     times = hourly.get("time", []) or []
#     values = hourly.get(field, []) or []
#     if not times or not values:
#         return None, None

#     n = min(len(times), len(values))
#     now = timezone.now()

#     for i in range(n - 1, -1, -1):
#         try:
#             dt = _parse_om_time(times[i])
#         except Exception:
#             continue
#         if dt <= now:
#             return times[i], values[i]

#     return times[n - 1], values[n - 1]


# def _deg_to_compass(deg: float | None) -> str | None:
#     if deg is None:
#         return None
#     dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
#     ix = int((deg % 360) / 22.5 + 0.5) % 16
#     return dirs[ix]


# def _build_cache_key(lat: float, lon: float, forecast_days: int, tz: str | None) -> str:
#     tz_part = tz or "auto"
#     return f"lat={lat:.6f}&lon={lon:.6f}&days={forecast_days}&tz={tz_part}"


# def _get_province_coord(code: str):
#     """
#     Lấy (province_dict, lat, lon) từ bảng provinces (Supabase) bằng centroid_lat/lon.
#     provinces columns: id, code, name, centroid_lat, centroid_lon
#     """
#     with connection.cursor() as cur:
#         cur.execute(
#             """
#             SELECT id, code, name, centroid_lat, centroid_lon
#             FROM provinces
#             WHERE code = %s
#             LIMIT 1
#             """,
#             [code],
#         )
#         row = cur.fetchone()

#     if not row:
#         raise Http404(f"Province with code={code} not found")

#     id_, code_db, name, lat, lon = row

#     province = {"id": int(id_), "code": str(code_db), "name": str(name)}

#     if lat is None or lon is None:
#         return province, None, None

#     return province, float(lat), float(lon)


# def _normalize_bundle(raw: dict) -> dict:
#     """
#     Convert Open-Meteo arrays => list objects, and reshape to frontend-friendly schema.

#     Output schema:
#     {
#       "location": {...},
#       "current": {...},
#       "hourly": [ ... ],
#       "daily": [ ... ],
#       "meta": {...}
#     }
#     """
#     tz_name = raw.get("timezone")
#     lat = raw.get("latitude")
#     lon = raw.get("longitude")

#     current = (raw.get("current") or raw.get("current_weather") or {}).copy()

#     def _fill_current_if_missing(cur_key: str, hourly_key: str):
#         if current.get(cur_key) is not None:
#             return
#         t, v = _latest_hour_value(raw, hourly_key)
#         if v is not None:
#             current[cur_key] = v
#             current["time"] = current.get("time") or t

#     _fill_current_if_missing("temperature_2m", "temperature_2m")
#     _fill_current_if_missing("apparent_temperature", "apparent_temperature")
#     _fill_current_if_missing("relative_humidity_2m", "relative_humidity_2m")
#     _fill_current_if_missing("precipitation", "precipitation")
#     _fill_current_if_missing("precipitation_probability", "precipitation_probability")
#     _fill_current_if_missing("cloud_cover", "cloud_cover")
#     _fill_current_if_missing("wind_speed_10m", "wind_speed_10m")
#     _fill_current_if_missing("wind_direction_10m", "wind_direction_10m")

#     cur = {
#         "time": current.get("time"),
#         "temperature_c": current.get("temperature_2m", current.get("temperature")),
#         "feels_like_c": current.get("apparent_temperature"),
#         "humidity_percent": current.get("relative_humidity_2m"),
#         "rain_mm": current.get("precipitation"),
#         "rain_prob_percent": current.get("precipitation_probability"),
#         "cloud_percent": current.get("cloud_cover"),
#         "wind_speed": current.get("wind_speed_10m", current.get("windspeed")),
#         "wind_direction_deg": current.get("wind_direction_10m", current.get("winddirection")),
#         "wind_direction_label": _deg_to_compass(
#             current.get("wind_direction_10m", current.get("winddirection"))
#         ),
#     }

#     # -------------------------
#     # Hourly
#     # -------------------------
#     hourly = raw.get("hourly") or {}
#     h_time = hourly.get("time") or []

#     def _h(name: str):
#         arr = hourly.get(name)
#         if arr is None:
#             return [None] * len(h_time)
#         if len(arr) < len(h_time):
#             return arr + [None] * (len(h_time) - len(arr))
#         return arr[: len(h_time)]

#     t = _h("temperature_2m")
#     at = _h("apparent_temperature")
#     rh = _h("relative_humidity_2m")
#     pr = _h("precipitation")
#     pp = _h("precipitation_probability")
#     cc = _h("cloud_cover")
#     ws = _h("wind_speed_10m")
#     wd = _h("wind_direction_10m")

#     hourly_points = []
#     for i in range(len(h_time)):
#         wd_label = _deg_to_compass(wd[i]) if wd[i] is not None else None
#         hourly_points.append(
#             {
#                 "time": h_time[i],
#                 "temperature_c": t[i],
#                 "feels_like_c": at[i],
#                 "humidity_percent": rh[i],
#                 "rain_mm": pr[i],
#                 "rain_prob_percent": pp[i],
#                 "cloud_percent": cc[i],
#                 "wind_speed": ws[i],
#                 "wind_direction_deg": wd[i],
#                 "wind_direction_label": wd_label,
#             }
#         )

#     def _hourly_group_by_date(field: str) -> dict[str, list[float]]:
#         buckets: dict[str, list[float]] = {}
#         for p in hourly_points:
#             v = p.get(field)
#             if v is None:
#                 continue
#             day = str(p.get("time", ""))[:10]
#             if not day:
#                 continue
#             try:
#                 buckets.setdefault(day, []).append(float(v))
#             except Exception:
#                 continue
#         return buckets

#     def _mean(xs: list[float]) -> float | None:
#         return (sum(xs) / len(xs)) if xs else None

#     def _max(xs: list[float]) -> float | None:
#         return max(xs) if xs else None

#     def _dominant_wind_dir_deg(xs_deg: list[float]) -> float | None:
#         if not xs_deg:
#             return None
#         counts = [0] * 16
#         for deg in xs_deg:
#             try:
#                 d = float(deg) % 360.0
#             except Exception:
#                 continue
#             idx = int((d / 22.5) + 0.5) % 16
#             counts[idx] += 1
#         best = max(range(16), key=lambda i: counts[i])
#         return best * 22.5

#     # -------------------------
#     # Daily
#     # -------------------------
#     daily = raw.get("daily") or {}
#     d_time = daily.get("time") or []

#     def _d(name: str):
#         arr = daily.get(name)
#         if arr is None:
#             return [None] * len(d_time)
#         if len(arr) < len(d_time):
#             return arr + [None] * (len(d_time) - len(arr))
#         return arr[: len(d_time)]

#     tmax = _d("temperature_2m_max")
#     tmin = _d("temperature_2m_min")
#     prsum = _d("precipitation_sum")
#     ppmax = _d("precipitation_probability_max")
#     wsmax = _d("wind_speed_10m_max")
#     wddom = _d("wind_direction_10m_dominant")

#     rh_mean_arr = _d("relative_humidity_2m_mean")
#     cc_mean_arr = _d("cloud_cover_mean")

#     rh_by_day = _hourly_group_by_date("humidity_percent")
#     cc_by_day = _hourly_group_by_date("cloud_percent")
#     ws_by_day = _hourly_group_by_date("wind_speed")
#     wd_by_day = _hourly_group_by_date("wind_direction_deg")

#     daily_points = []
#     for i in range(len(d_time)):
#         day = d_time[i]

#         rh_mean = rh_mean_arr[i]
#         cc_mean = cc_mean_arr[i]
#         ws_max = wsmax[i]
#         wd_dom = wddom[i]

#         if rh_mean is None:
#             rh_mean = _mean(rh_by_day.get(day, []))
#         if cc_mean is None:
#             cc_mean = _mean(cc_by_day.get(day, []))
#         if ws_max is None:
#             ws_max = _max(ws_by_day.get(day, []))
#         if wd_dom is None:
#             wd_dom = _dominant_wind_dir_deg(wd_by_day.get(day, []))

#         daily_points.append(
#             {
#                 "date": day,
#                 "tmax_c": tmax[i],
#                 "tmin_c": tmin[i],
#                 "humidity_mean_percent": rh_mean,
#                 "cloud_mean_percent": cc_mean,
#                 "wind_speed_max_kmh": ws_max,
#                 "wind_direction_dominant_deg": wd_dom,
#                 "wind_direction_dominant_label": _deg_to_compass(wd_dom) if wd_dom is not None else None,
#                 "rain_sum_mm": prsum[i],
#                 "rain_prob_max_percent": ppmax[i],
#             }
#         )

#     return {
#         "location": {"lat": lat, "lon": lon, "timezone": tz_name},
#         "current": cur,
#         "hourly": hourly_points,
#         "daily": daily_points,
#         "meta": {"source": "open-meteo", "generated_at": timezone.now().isoformat()},
#     }


# def _open_meteo_fetch(lat: float, lon: float, forecast_days: int = 10, tz: str | None = None) -> dict:
#     params = {
#         "latitude": lat,
#         "longitude": lon,
#         "timezone": tz or "auto",
#         "forecast_days": forecast_days,
#         "wind_speed_unit": "kmh",
#         "precipitation_unit": "mm",
#         "current": ",".join(
#             [
#                 "temperature_2m",
#                 "apparent_temperature",
#                 "relative_humidity_2m",
#                 "precipitation",
#                 "cloud_cover",
#                 "wind_speed_10m",
#                 "wind_direction_10m",
#             ]
#         ),
#         "hourly": ",".join(
#             [
#                 "temperature_2m",
#                 "apparent_temperature",
#                 "relative_humidity_2m",
#                 "precipitation",
#                 "precipitation_probability",
#                 "cloud_cover",
#                 "wind_speed_10m",
#                 "wind_direction_10m",
#             ]
#         ),
#         "daily": ",".join(
#             [
#                 "temperature_2m_max",
#                 "temperature_2m_min",
#                 "precipitation_sum",
#                 "precipitation_probability_max",
#                 "wind_speed_10m_max",
#                 "wind_direction_10m_dominant",
#                 "relative_humidity_2m_mean",
#                 "cloud_cover_mean",
#             ]
#         ),
#     }

#     resp = requests.get(OPEN_METEO_BASE, params=params, timeout=20)
#     resp.raise_for_status()
#     return resp.json()


# # =========================
# # Endpoints
# # =========================

# @api_view(["GET"])
# def province_weather(request, code: str):
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

#     om = _om_get(
#         lat,
#         lon,
#         {
#             "current_weather": True,
#             "daily": "temperature_2m_max,temperature_2m_min",
#             "past_days": 7,
#             "forecast_days": 7,
#         },
#     )

#     current = om.get("current_weather", {})
#     daily = om.get("daily", {})

#     today = date.today().isoformat()
#     past, future = [], []

#     for i, t in enumerate(daily.get("time", [])):
#         item = {"time": t, "tmax": daily["temperature_2m_max"][i], "tmin": daily["temperature_2m_min"][i]}
#         (past if t < today else future).append(item)

#     return Response(
#         {
#             "province": province,
#             "coord": {"lat": lat, "lon": lon},
#             "current": {"temperature": current.get("temperature"), "time": current.get("time")},
#             "daily_past_7": past[-7:],
#             "daily_future_7": future[:7],
#         }
#     )


# @api_view(["GET"])
# def province_rain(request, code: str):
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

#     om = _om_get(
#         lat,
#         lon,
#         {
#             "current": "precipitation,precipitation_probability",
#             "hourly": "precipitation,precipitation_probability",
#             "daily": "precipitation_sum,precipitation_probability_max",
#             "forecast_days": 7,
#             "past_days": 1,
#             "precipitation_unit": "mm",
#         },
#     )

#     cur = om.get("current", {}) or {}
#     t = cur.get("time")
#     precip = cur.get("precipitation")
#     prob = cur.get("precipitation_probability")

#     if precip is None:
#         t2, precip = _latest_hour_value(om, "precipitation")
#         t = t or t2
#     if prob is None:
#         t3, prob = _latest_hour_value(om, "precipitation_probability")
#         t = t or t3

#     daily = om.get("daily", {}) or {}
#     d_times = daily.get("time", []) or []
#     d_sum = daily.get("precipitation_sum", []) or []
#     d_pmax = daily.get("precipitation_probability_max", []) or []

#     n = min(len(d_times), 7)
#     points = []
#     for i in range(n):
#         points.append(
#             {
#                 "date": d_times[i],
#                 "precipitation_sum_mm": d_sum[i] if i < len(d_sum) else None,
#                 "precipitation_probability_max": d_pmax[i] if i < len(d_pmax) else None,
#             }
#         )

#     return Response(
#         {
#             "province": province,
#             "coord": {"lat": lat, "lon": lon},
#             "timezone": om.get("timezone"),
#             "current": {"precipitation_mm": precip, "precipitation_probability": prob, "time": t},
#             "daily": {"points": points},
#         }
#     )


# @api_view(["GET"])
# def province_wind(request, code: str):
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

#     om = _om_get(
#         lat,
#         lon,
#         {
#             "hourly": "wind_speed_10m,wind_direction_10m",
#             "past_days": 1,
#             "forecast_days": 0,
#             "windspeed_unit": "ms",  # giữ như bạn đang dùng
#         },
#     )

#     hourly = om.get("hourly", {}) or {}
#     times = hourly.get("time", []) or []
#     wspd = hourly.get("wind_speed_10m", []) or []
#     wdir = hourly.get("wind_direction_10m", []) or []

#     if not times or not wdir:
#         return Response({"detail": "No wind data"}, status=204)

#     speed_kmh = (wspd[-1] * 3.6) if (wspd and wspd[-1] is not None) else None
#     direction_deg = wdir[-1] if wdir else None
#     time_str = times[-1] if times else None

#     labels = [
#         "Bắc", "BĐB", "ĐB", "ĐĐB",
#         "Đ", "ĐĐN", "ĐN", "NĐN",
#         "Nam", "NTN", "TN", "TTN",
#         "T", "TTB", "TB", "BTB",
#     ]
#     counts = [0] * 16
#     for deg in wdir[-24:]:
#         if deg is None:
#             continue
#         idx = int(round((deg % 360) / 22.5)) % 16
#         counts[idx] += 1

#     rose = [{"dir_label": labels[i], "angle_deg": i * 22.5, "count": counts[i]} for i in range(16)]

#     return Response(
#         {
#             "province": province,
#             "coord": {"lat": lat, "lon": lon},
#             "current": {"wind_speed_kmh": speed_kmh, "wind_direction_deg": direction_deg, "time": time_str},
#             "rose_period_hours": 24,
#             "rose": rose,
#         }
#     )


# @api_view(["GET"])
# def province_humidity(request, code: str):
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

#     om = _om_get(
#         lat,
#         lon,
#         {
#             "current": "relative_humidity_2m",
#             "hourly": "relative_humidity_2m",
#             "past_days": 1,
#             "forecast_days": 1,
#         },
#     )

#     cur = om.get("current") or {}
#     t = cur.get("time")
#     v = cur.get("relative_humidity_2m")

#     return Response(
#         {
#             "province": province,
#             "coord": {"lat": lat, "lon": lon},
#             "current": {"time": t, "humidity_percent": v},
#         }
#     )


# @api_view(["GET"])
# def province_cloud(request, code: str):
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

#     om = _om_get(
#         lat,
#         lon,
#         {
#             "current": "cloud_cover",
#             "hourly": "cloud_cover",
#             "past_days": 1,
#             "forecast_days": 1,
#         },
#     )

#     cur = om.get("current", {}) or {}
#     t = cur.get("time")
#     cloud = cur.get("cloud_cover")

#     if cloud is None:
#         t2, cloud = _latest_hour_value(om, "cloud_cover")
#         t = t or t2

#     return Response(
#         {
#             "province": province,
#             "coord": {"lat": lat, "lon": lon},
#             "timezone": om.get("timezone"),
#             "current": {"time": t, "cloud_cover_percent": cloud, "visibility_m": None},
#         }
#     )


# @api_view(["GET"])
# def province_current(request, code: str):
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": f"Province {code} missing centroid_lat/centroid_lon"}, status=status.HTTP_400_BAD_REQUEST)

#     try:
#         resp = requests.get(
#             OPEN_METEO_BASE,
#             params={
#                 "latitude": lat,
#                 "longitude": lon,
#                 "timezone": "auto",
#                 "windspeed_unit": "kmh",
#                 "precipitation_unit": "mm",
#                 "current": ",".join(
#                     [
#                         "temperature_2m",
#                         "relative_humidity_2m",
#                         "precipitation",
#                         "cloud_cover",
#                         "wind_speed_10m",
#                         "wind_direction_10m",
#                     ]
#                 ),
#             },
#             timeout=15,
#         )
#         resp.raise_for_status()
#         om = resp.json()
#     except Exception as e:
#         return Response({"detail": f"Open-Meteo error: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

#     curw = om.get("current") or {}

#     return Response(
#         {
#             "region": {"code": province["code"], "name": province["name"]},
#             "time": curw.get("time"),
#             "temperature_c": curw.get("temperature_2m"),
#             "feels_like_c": None,
#             "wind_kmh": curw.get("wind_speed_10m"),
#             "wind_dir_deg": curw.get("wind_direction_10m"),
#             "humidity_percent": curw.get("relative_humidity_2m"),
#             "cloud_percent": curw.get("cloud_cover"),
#             "precipitation_mm": curw.get("precipitation"),
#             "meta": {
#                 "source": "open-meteo",
#                 "timezone": om.get("timezone"),
#                 "lat": lat,
#                 "lon": lon,
#             },
#         }
#     )


# @api_view(["GET"])
# def province_bundle(request, code: str):
#     """
#     Trả bundle current + hourly + daily để frontend vẽ HourlySection.
#     """
#     province, lat, lon = _get_province_coord(code)
#     if lat is None or lon is None:
#         return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=status.HTTP_400_BAD_REQUEST)

#     forecast_days = int(request.query_params.get("days", 10))
#     forecast_days = max(1, min(forecast_days, 16))

#     tz = request.query_params.get("tz")

#     cache_key = _build_cache_key(lat, lon, forecast_days, tz or "auto")

#     try:
#         fc = ForecastCache.objects.filter(key=cache_key).first()
#         if fc:
#             payload = getattr(fc, "payload", None) or getattr(fc, "data", None)
#             expires_at = getattr(fc, "expires_at", None)
#             if payload and (expires_at is None or expires_at > timezone.now()):
#                 return Response(payload)
#     except Exception:
#         fc = None

#     try:
#         raw = _open_meteo_fetch(lat, lon, forecast_days=forecast_days, tz=tz)
#         payload = _normalize_bundle(raw)
#         payload["region"] = {"code": province["code"], "name": province["name"]}
#     except Exception as e:
#         return Response({"detail": f"Open-Meteo error: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

#     try:
#         if fc is None:
#             fc = ForecastCache(key=cache_key)
#         if hasattr(fc, "payload"):
#             fc.payload = payload
#         elif hasattr(fc, "data"):
#             fc.data = payload
#         if hasattr(fc, "expires_at"):
#             fc.expires_at = timezone.now() + timedelta(minutes=10)
#         fc.save()
#     except Exception:
#         pass

#     return Response(payload)


# @api_view(["GET"])
# def province_index(request):
#     """
#     Trả danh sách tỉnh/thành siêu nhẹ cho search bar:
#     {
#       items: [
#         { id, code, name, centroid: { lat, lon } }
#       ]
#     }
#     """
#     cache_key = "meteo:province_index:v2"
#     cached = cache.get(cache_key)
#     if cached is not None:
#         resp = Response(cached)
#         resp["Cache-Control"] = "public, max-age=604800"
#         return resp

#     items = []
#     with connection.cursor() as cur:
#         cur.execute(
#             """
#             SELECT id, code, name, centroid_lat, centroid_lon
#             FROM provinces
#             WHERE code IS NOT NULL AND name IS NOT NULL
#             ORDER BY name ASC;
#             """
#         )
#         for id_, code, name, lat, lon in cur.fetchall():
#             if lat is None or lon is None:
#                 continue
#             items.append(
#                 {
#                     "id": int(id_),
#                     "code": str(code),
#                     "name": str(name),
#                     "centroid": {"lat": float(lat), "lon": float(lon)},
#                 }
#             )

#     payload = {"items": items}
#     cache.set(cache_key, payload, 60 * 60 * 24 * 7)

#     resp = Response(payload)
#     resp["Cache-Control"] = "public, max-age=604800"
#     return resp


# # Phường xã

# @api_view(["GET"])
# def hcm_districts(request):
#     qs = Place.objects.filter(kind="hcm_district").order_by("name")
#     return Response([
#         {
#             "id": x.id,
#             "code": x.code,
#             "name": x.name,
#             "centroid": {"lat": x.lat, "lon": x.lon},
#         }
#         for x in qs
#     ])


# api/views.py
from __future__ import annotations

from datetime import date, datetime, timedelta
import requests

from django.db import connection
from django.utils import timezone
from django.core.cache import cache
from django.http import Http404

from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view

from api.models import Place
from .models import ForecastCache  # ✅ KHÔNG import Province vì model đang lệch schema

OPEN_METEO_BASE = "https://api.open-meteo.com/v1/forecast"


# =========================
# Helpers
# =========================
def _om_get(lat: float, lon: float, params: dict):
    base = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
    }
    base.update(params)
    resp = requests.get(OPEN_METEO_BASE, params=base, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _parse_om_time(t_str: str):
    # Open-Meteo thường trả kiểu "2025-12-11T23:00"
    dt_naive = datetime.fromisoformat(t_str)
    if dt_naive.tzinfo is None:
        return timezone.make_aware(dt_naive, timezone.get_default_timezone())
    return dt_naive


def _latest_hour_value(om: dict, field: str):
    """
    Lấy giá trị hourly gần nhất tại/ trước 'now' (không lấy giờ tương lai).
    """
    hourly = om.get("hourly", {}) or {}
    times = hourly.get("time", []) or []
    values = hourly.get(field, []) or []
    if not times or not values:
        return None, None

    n = min(len(times), len(values))
    now = timezone.now()

    for i in range(n - 1, -1, -1):
        try:
            dt = _parse_om_time(times[i])
        except Exception:
            continue
        if dt <= now:
            return times[i], values[i]

    return times[n - 1], values[n - 1]


def _deg_to_compass(deg: float | None) -> str | None:
    if deg is None:
        return None
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    ix = int((deg % 360) / 22.5 + 0.5) % 16
    return dirs[ix]


def _build_cache_key(lat: float, lon: float, forecast_days: int, tz: str | None) -> str:
    tz_part = tz or "auto"
    return f"lat={lat:.6f}&lon={lon:.6f}&days={forecast_days}&tz={tz_part}"


def _get_province_coord(code: str):
    """
    Lấy (province_dict, lat, lon) từ bảng provinces (Supabase) bằng centroid_lat/lon.
    provinces columns: id, code, name, centroid_lat, centroid_lon
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, code, name, centroid_lat, centroid_lon
            FROM provinces
            WHERE code = %s
            LIMIT 1
            """,
            [code],
        )
        row = cur.fetchone()

    if not row:
        raise Http404(f"Province with code={code} not found")

    id_, code_db, name, lat, lon = row
    province = {"id": int(id_), "code": str(code_db), "name": str(name), "kind": "province"}

    if lat is None or lon is None:
        return province, None, None

    return province, float(lat), float(lon)


def _get_region_coord(code: str):
    """
    Resolve (region_dict, lat, lon) theo code:
    - ưu tiên bảng provinces (Supabase) qua raw SQL
    - fallback sang bảng places (Django model Place)
    Trả về dict cùng shape "province" hiện tại để frontend khỏi đổi.
    """
    # 1) provinces (raw SQL)
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, code, name, centroid_lat, centroid_lon
            FROM provinces
            WHERE code = %s
            LIMIT 1
            """,
            [code],
        )
        row = cur.fetchone()

    if row:
        id_, code_db, name, lat, lon = row
        region = {"id": int(id_), "code": str(code_db), "name": str(name), "kind": "province"}
        if lat is None or lon is None:
            return region, None, None
        return region, float(lat), float(lon)

    # 2) places (Django ORM)
    place = Place.objects.filter(code=code).only("id", "code", "name", "kind", "lat", "lon").first()
    if place:
        region = {"id": int(place.id), "code": str(place.code), "name": str(place.name), "kind": str(place.kind)}
        if place.lat is None or place.lon is None:
            return region, None, None
        return region, float(place.lat), float(place.lon)

    raise Http404(f"Region with code={code} not found")


def _normalize_bundle(raw: dict) -> dict:
    """
    Convert Open-Meteo arrays => list objects, and reshape to frontend-friendly schema.

    Output schema:
    {
      "location": {...},
      "current": {...},
      "hourly": [ ... ],
      "daily": [ ... ],
      "meta": {...}
    }
    """
    tz_name = raw.get("timezone")
    lat = raw.get("latitude")
    lon = raw.get("longitude")

    current = (raw.get("current") or raw.get("current_weather") or {}).copy()

    def _fill_current_if_missing(cur_key: str, hourly_key: str):
        if current.get(cur_key) is not None:
            return
        t, v = _latest_hour_value(raw, hourly_key)
        if v is not None:
            current[cur_key] = v
            current["time"] = current.get("time") or t

    _fill_current_if_missing("temperature_2m", "temperature_2m")
    _fill_current_if_missing("apparent_temperature", "apparent_temperature")
    _fill_current_if_missing("relative_humidity_2m", "relative_humidity_2m")
    _fill_current_if_missing("precipitation", "precipitation")
    _fill_current_if_missing("precipitation_probability", "precipitation_probability")
    _fill_current_if_missing("cloud_cover", "cloud_cover")
    _fill_current_if_missing("wind_speed_10m", "wind_speed_10m")
    _fill_current_if_missing("wind_direction_10m", "wind_direction_10m")

    cur = {
        "time": current.get("time"),
        "temperature_c": current.get("temperature_2m", current.get("temperature")),
        "feels_like_c": current.get("apparent_temperature"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "rain_mm": current.get("precipitation"),
        "rain_prob_percent": current.get("precipitation_probability"),
        "cloud_percent": current.get("cloud_cover"),
        "wind_speed": current.get("wind_speed_10m", current.get("windspeed")),
        "wind_direction_deg": current.get("wind_direction_10m", current.get("winddirection")),
        "wind_direction_label": _deg_to_compass(
            current.get("wind_direction_10m", current.get("winddirection"))
        ),
    }

    # -------------------------
    # Hourly
    # -------------------------
    hourly = raw.get("hourly") or {}
    h_time = hourly.get("time") or []

    def _h(name: str):
        arr = hourly.get(name)
        if arr is None:
            return [None] * len(h_time)
        if len(arr) < len(h_time):
            return arr + [None] * (len(h_time) - len(arr))
        return arr[: len(h_time)]

    t = _h("temperature_2m")
    at = _h("apparent_temperature")
    rh = _h("relative_humidity_2m")
    pr = _h("precipitation")
    pp = _h("precipitation_probability")
    cc = _h("cloud_cover")
    ws = _h("wind_speed_10m")
    wd = _h("wind_direction_10m")

    hourly_points = []
    for i in range(len(h_time)):
        wd_label = _deg_to_compass(wd[i]) if wd[i] is not None else None
        hourly_points.append(
            {
                "time": h_time[i],
                "temperature_c": t[i],
                "feels_like_c": at[i],
                "humidity_percent": rh[i],
                "rain_mm": pr[i],
                "rain_prob_percent": pp[i],
                "cloud_percent": cc[i],
                "wind_speed": ws[i],
                "wind_direction_deg": wd[i],
                "wind_direction_label": wd_label,
            }
        )

    def _hourly_group_by_date(field: str) -> dict[str, list[float]]:
        buckets: dict[str, list[float]] = {}
        for p in hourly_points:
            v = p.get(field)
            if v is None:
                continue
            day = str(p.get("time", ""))[:10]
            if not day:
                continue
            try:
                buckets.setdefault(day, []).append(float(v))
            except Exception:
                continue
        return buckets

    def _mean(xs: list[float]) -> float | None:
        return (sum(xs) / len(xs)) if xs else None

    def _max(xs: list[float]) -> float | None:
        return max(xs) if xs else None

    def _dominant_wind_dir_deg(xs_deg: list[float]) -> float | None:
        if not xs_deg:
            return None
        counts = [0] * 16
        for deg in xs_deg:
            try:
                d = float(deg) % 360.0
            except Exception:
                continue
            idx = int((d / 22.5) + 0.5) % 16
            counts[idx] += 1
        best = max(range(16), key=lambda i: counts[i])
        return best * 22.5

    # -------------------------
    # Daily
    # -------------------------
    daily = raw.get("daily") or {}
    d_time = daily.get("time") or []

    def _d(name: str):
        arr = daily.get(name)
        if arr is None:
            return [None] * len(d_time)
        if len(arr) < len(d_time):
            return arr + [None] * (len(d_time) - len(arr))
        return arr[: len(d_time)]

    tmax = _d("temperature_2m_max")
    tmin = _d("temperature_2m_min")
    prsum = _d("precipitation_sum")
    ppmax = _d("precipitation_probability_max")
    wsmax = _d("wind_speed_10m_max")
    wddom = _d("wind_direction_10m_dominant")

    rh_mean_arr = _d("relative_humidity_2m_mean")
    cc_mean_arr = _d("cloud_cover_mean")

    rh_by_day = _hourly_group_by_date("humidity_percent")
    cc_by_day = _hourly_group_by_date("cloud_percent")
    ws_by_day = _hourly_group_by_date("wind_speed")
    wd_by_day = _hourly_group_by_date("wind_direction_deg")

    daily_points = []
    for i in range(len(d_time)):
        day = d_time[i]

        rh_mean = rh_mean_arr[i]
        cc_mean = cc_mean_arr[i]
        ws_max = wsmax[i]
        wd_dom = wddom[i]

        if rh_mean is None:
            rh_mean = _mean(rh_by_day.get(day, []))
        if cc_mean is None:
            cc_mean = _mean(cc_by_day.get(day, []))
        if ws_max is None:
            ws_max = _max(ws_by_day.get(day, []))
        if wd_dom is None:
            wd_dom = _dominant_wind_dir_deg(wd_by_day.get(day, []))

        daily_points.append(
            {
                "date": day,
                "tmax_c": tmax[i],
                "tmin_c": tmin[i],
                "humidity_mean_percent": rh_mean,
                "cloud_mean_percent": cc_mean,
                "wind_speed_max_kmh": ws_max,
                "wind_direction_dominant_deg": wd_dom,
                "wind_direction_dominant_label": _deg_to_compass(wd_dom) if wd_dom is not None else None,
                "rain_sum_mm": prsum[i],
                "rain_prob_max_percent": ppmax[i],
            }
        )

    return {
        "location": {"lat": lat, "lon": lon, "timezone": tz_name},
        "current": cur,
        "hourly": hourly_points,
        "daily": daily_points,
        "meta": {"source": "open-meteo", "generated_at": timezone.now().isoformat()},
    }


def _open_meteo_fetch(lat: float, lon: float, forecast_days: int = 10, tz: str | None = None) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": tz or "auto",
        "forecast_days": forecast_days,
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "current": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
            ]
        ),
        "hourly": ",".join(
            [
                "temperature_2m",
                "apparent_temperature",
                "relative_humidity_2m",
                "precipitation",
                "precipitation_probability",
                "cloud_cover",
                "wind_speed_10m",
                "wind_direction_10m",
            ]
        ),
        "daily": ",".join(
            [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "wind_speed_10m_max",
                "wind_direction_10m_dominant",
                "relative_humidity_2m_mean",
                "cloud_cover_mean",
            ]
        ),
    }

    resp = requests.get(OPEN_METEO_BASE, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


# =========================
# Endpoints
# =========================

@api_view(["GET"])
def province_weather(request, code: str):
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

    om = _om_get(
        lat,
        lon,
        {
            "current_weather": True,
            "daily": "temperature_2m_max,temperature_2m_min",
            "past_days": 7,
            "forecast_days": 7,
        },
    )

    current = om.get("current_weather", {})
    daily = om.get("daily", {})

    today = date.today().isoformat()
    past, future = [], []

    for i, t in enumerate(daily.get("time", [])):
        item = {"time": t, "tmax": daily["temperature_2m_max"][i], "tmin": daily["temperature_2m_min"][i]}
        (past if t < today else future).append(item)

    return Response(
        {
            "province": province,
            "coord": {"lat": lat, "lon": lon},
            "current": {"temperature": current.get("temperature"), "time": current.get("time")},
            "daily_past_7": past[-7:],
            "daily_future_7": future[:7],
        }
    )


@api_view(["GET"])
def province_rain(request, code: str):
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

    om = _om_get(
        lat,
        lon,
        {
            "current": "precipitation,precipitation_probability",
            "hourly": "precipitation,precipitation_probability",
            "daily": "precipitation_sum,precipitation_probability_max",
            "forecast_days": 7,
            "past_days": 1,
            "precipitation_unit": "mm",
        },
    )

    cur = om.get("current", {}) or {}
    t = cur.get("time")
    precip = cur.get("precipitation")
    prob = cur.get("precipitation_probability")

    if precip is None:
        t2, precip = _latest_hour_value(om, "precipitation")
        t = t or t2
    if prob is None:
        t3, prob = _latest_hour_value(om, "precipitation_probability")
        t = t or t3

    daily = om.get("daily", {}) or {}
    d_times = daily.get("time", []) or []
    d_sum = daily.get("precipitation_sum", []) or []
    d_pmax = daily.get("precipitation_probability_max", []) or []

    n = min(len(d_times), 7)
    points = []
    for i in range(n):
        points.append(
            {
                "date": d_times[i],
                "precipitation_sum_mm": d_sum[i] if i < len(d_sum) else None,
                "precipitation_probability_max": d_pmax[i] if i < len(d_pmax) else None,
            }
        )

    return Response(
        {
            "province": province,
            "coord": {"lat": lat, "lon": lon},
            "timezone": om.get("timezone"),
            "current": {"precipitation_mm": precip, "precipitation_probability": prob, "time": t},
            "daily": {"points": points},
        }
    )


@api_view(["GET"])
def province_wind(request, code: str):
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

    om = _om_get(
        lat,
        lon,
        {
            "hourly": "wind_speed_10m,wind_direction_10m",
            "past_days": 1,
            "forecast_days": 0,
            "windspeed_unit": "ms",  # giữ như bạn đang dùng
        },
    )

    hourly = om.get("hourly", {}) or {}
    times = hourly.get("time", []) or []
    wspd = hourly.get("wind_speed_10m", []) or []
    wdir = hourly.get("wind_direction_10m", []) or []

    if not times or not wdir:
        return Response({"detail": "No wind data"}, status=204)

    speed_kmh = (wspd[-1] * 3.6) if (wspd and wspd[-1] is not None) else None
    direction_deg = wdir[-1] if wdir else None
    time_str = times[-1] if times else None

    labels = [
        "Bắc", "BĐB", "ĐB", "ĐĐB",
        "Đ", "ĐĐN", "ĐN", "NĐN",
        "Nam", "NTN", "TN", "TTN",
        "T", "TTB", "TB", "BTB",
    ]
    counts = [0] * 16
    for deg in wdir[-24:]:
        if deg is None:
            continue
        idx = int(round((deg % 360) / 22.5)) % 16
        counts[idx] += 1

    rose = [{"dir_label": labels[i], "angle_deg": i * 22.5, "count": counts[i]} for i in range(16)]

    return Response(
        {
            "province": province,
            "coord": {"lat": lat, "lon": lon},
            "current": {"wind_speed_kmh": speed_kmh, "wind_direction_deg": direction_deg, "time": time_str},
            "rose_period_hours": 24,
            "rose": rose,
        }
    )


@api_view(["GET"])
def province_humidity(request, code: str):
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

    om = _om_get(
        lat,
        lon,
        {
            "current": "relative_humidity_2m",
            "hourly": "relative_humidity_2m",
            "past_days": 1,
            "forecast_days": 1,
        },
    )

    cur = om.get("current") or {}
    t = cur.get("time")
    v = cur.get("relative_humidity_2m")

    return Response(
        {
            "province": province,
            "coord": {"lat": lat, "lon": lon},
            "current": {"time": t, "humidity_percent": v},
        }
    )


@api_view(["GET"])
def province_cloud(request, code: str):
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=400)

    om = _om_get(
        lat,
        lon,
        {
            "current": "cloud_cover",
            "hourly": "cloud_cover",
            "past_days": 1,
            "forecast_days": 1,
        },
    )

    cur = om.get("current", {}) or {}
    t = cur.get("time")
    cloud = cur.get("cloud_cover")

    if cloud is None:
        t2, cloud = _latest_hour_value(om, "cloud_cover")
        t = t or t2

    return Response(
        {
            "province": province,
            "coord": {"lat": lat, "lon": lon},
            "timezone": om.get("timezone"),
            "current": {"time": t, "cloud_cover_percent": cloud, "visibility_m": None},
        }
    )


@api_view(["GET"])
def province_current(request, code: str):
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": f"Region {code} missing centroid_lat/centroid_lon"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        resp = requests.get(
            OPEN_METEO_BASE,
            params={
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "windspeed_unit": "kmh",
                "precipitation_unit": "mm",
                "current": ",".join(
                    [
                        "temperature_2m",
                        "relative_humidity_2m",
                        "precipitation",
                        "cloud_cover",
                        "wind_speed_10m",
                        "wind_direction_10m",
                    ]
                ),
            },
            timeout=15,
        )
        resp.raise_for_status()
        om = resp.json()
    except Exception as e:
        return Response({"detail": f"Open-Meteo error: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    curw = om.get("current") or {}

    return Response(
        {
            "region": {"code": province["code"], "name": province["name"]},
            "time": curw.get("time"),
            "temperature_c": curw.get("temperature_2m"),
            "feels_like_c": None,
            "wind_kmh": curw.get("wind_speed_10m"),
            "wind_dir_deg": curw.get("wind_direction_10m"),
            "humidity_percent": curw.get("relative_humidity_2m"),
            "cloud_percent": curw.get("cloud_cover"),
            "precipitation_mm": curw.get("precipitation"),
            "meta": {
                "source": "open-meteo",
                "timezone": om.get("timezone"),
                "lat": lat,
                "lon": lon,
            },
        }
    )


@api_view(["GET"])
def province_bundle(request, code: str):
    """
    Trả bundle current + hourly + daily để frontend vẽ HourlySection.
    """
    province, lat, lon = _get_region_coord(code)
    if lat is None or lon is None:
        return Response({"detail": "Missing centroid_lat/centroid_lon"}, status=status.HTTP_400_BAD_REQUEST)

    forecast_days = int(request.query_params.get("days", 10))
    forecast_days = max(1, min(forecast_days, 16))

    tz = request.query_params.get("tz")
    cache_key = _build_cache_key(lat, lon, forecast_days, tz or "auto")

    try:
        fc = ForecastCache.objects.filter(key=cache_key).first()
        if fc:
            payload = getattr(fc, "payload", None) or getattr(fc, "data", None)
            expires_at = getattr(fc, "expires_at", None)
            if payload and (expires_at is None or expires_at > timezone.now()):
                return Response(payload)
    except Exception:
        fc = None

    try:
        raw = _open_meteo_fetch(lat, lon, forecast_days=forecast_days, tz=tz)
        payload = _normalize_bundle(raw)
        payload["region"] = {"code": province["code"], "name": province["name"]}
    except Exception as e:
        return Response({"detail": f"Open-Meteo error: {str(e)}"}, status=status.HTTP_502_BAD_GATEWAY)

    try:
        if fc is None:
            fc = ForecastCache(key=cache_key)
        if hasattr(fc, "payload"):
            fc.payload = payload
        elif hasattr(fc, "data"):
            fc.data = payload
        if hasattr(fc, "expires_at"):
            fc.expires_at = timezone.now() + timedelta(minutes=10)
        fc.save()
    except Exception:
        pass

    return Response(payload)


@api_view(["GET"])
def province_index(request):
    """
    Trả danh sách tỉnh/thành siêu nhẹ cho search bar:
    {
      items: [
        { id, code, name, centroid: { lat, lon } }
      ]
    }
    """
    cache_key = "meteo:province_index:v2"
    cached = cache.get(cache_key)
    if cached is not None:
        resp = Response(cached)
        resp["Cache-Control"] = "public, max-age=604800"
        return resp

    items = []
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT id, code, name, centroid_lat, centroid_lon
            FROM provinces
            WHERE code IS NOT NULL AND name IS NOT NULL
            ORDER BY name ASC;
            """
        )
        for id_, code, name, lat, lon in cur.fetchall():
            if lat is None or lon is None:
                continue
            items.append(
                {
                    "id": int(id_),
                    "code": str(code),
                    "name": str(name),
                    "centroid": {"lat": float(lat), "lon": float(lon)},
                }
            )

    payload = {"items": items}
    cache.set(cache_key, payload, 60 * 60 * 24 * 7)

    resp = Response(payload)
    resp["Cache-Control"] = "public, max-age=604800"
    return resp


# =========================
# Places (quận/huyện)
# =========================

@api_view(["GET"])
def hcm_districts(request):
    qs = Place.objects.filter(kind="hcm_district").order_by("name")
    return Response(
        [
            {
                "id": x.id,
                "code": x.code,
                "name": x.name,
                "centroid": {"lat": x.lat, "lon": x.lon},
            }
            for x in qs
        ]
    )


@api_view(["GET"])
def kien_giang_places(request):
    qs = Place.objects.filter(kind="kien_giang_place").order_by("name")
    return Response(
        [
            {
                "id": x.id,
                "code": x.code,
                "name": x.name,
                "centroid": {"lat": x.lat, "lon": x.lon},
            }
            for x in qs
        ]
    )






