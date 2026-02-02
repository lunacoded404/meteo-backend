# backend/api/open_meteo.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.db import connection

# =========================
# Open-Meteo endpoints
# =========================
OPEN_METEO_FORECAST_BASE = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_BASE = "https://archive-api.open-meteo.com/v1/archive"

# Bảng provinces hiện có của bạn (Supabase/Postgres)
PROVINCES_TABLE = "public.provinces"

# Timeout gọi API
HTTP_TIMEOUT_SEC = 20

# =========================
# Cloud field normalize
# =========================
# Open-Meteo: hourly/current = cloud_cover
# Open-Meteo: daily = cloud_cover_mean (thường), có thể có min/max tuỳ dataset
DAILY_CLOUD_CANONICAL = "cloud_cover_mean"
DAILY_CLOUD_ALIASES = {"cloud_cover": DAILY_CLOUD_CANONICAL}


# =========================
# Helpers
# =========================
def _normalize_code(code: str | int) -> str:
    """
    Chuẩn hoá mã tỉnh:
    - Trim khoảng trắng
    - Nếu là số 1 chữ số => pad thành '01'
    - Giữ nguyên nếu đã là '79', '01', '04', ...
    """
    s = str(code).strip()
    if s.isdigit() and len(s) == 1:
        s = s.zfill(2)
    return s


def _get_latlon_by_province_code(province_code: str | int) -> Tuple[float, float]:
    """
    Lấy centroid (lat, lon) từ bảng public.provinces theo code.
    Open-Meteo cần (latitude, longitude) => trả (centroid_lat, centroid_lon)
    """
    code = _normalize_code(province_code)

    with connection.cursor() as cur:
        cur.execute(
            f"""
            select centroid_lat, centroid_lon
            from {PROVINCES_TABLE}
            where code = %s
            limit 1
            """,
            [code],
        )
        row = cur.fetchone()

    if not row:
        raise ValueError(f"Province code not found: {code}")

    lat, lon = row[0], row[1]
    if lat is None or lon is None:
        raise ValueError(f"Province code {code} missing centroid_lat/centroid_lon")

    return float(lat), float(lon)


def _om_get(url: str, lat: float, lon: float, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Gọi Open-Meteo và trả JSON (dict).
    Tự thêm latitude/longitude/timezone=auto.
    """
    base = {
        "latitude": lat,
        "longitude": lon,
        "timezone": "auto",
    }
    base.update(params)

    resp = requests.get(url, params=base, timeout=HTTP_TIMEOUT_SEC)
    resp.raise_for_status()
    return resp.json()


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _pick_hour_index(times: List[str], target: datetime) -> int:
    """
    Chọn index giờ gần target nhất trong mảng time dạng ISO.
    Nếu parse fail -> trả 0.
    """
    best_i = 0
    best_dt = None
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(t)
        except Exception:
            continue
        if best_dt is None or abs((dt - target).total_seconds()) < abs((best_dt - target).total_seconds()):
            best_dt = dt
            best_i = i
    return best_i


def _normalize_daily_fields(fields: List[str]) -> List[str]:
    """
    Normalize danh sách daily fields để tương thích Open-Meteo.
    - Nếu ai đó truyền cloud_cover (hourly/current style) cho daily => đổi sang cloud_cover_mean.
    """
    out: List[str] = []
    for f in fields:
        f2 = DAILY_CLOUD_ALIASES.get(f, f)
        if f2 not in out:
            out.append(f2)
    return out


def _alias_daily_cloud(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Nếu payload daily có cloud_cover_mean mà FE đang xài cloud_cover,
    thì thêm alias daily["cloud_cover"] = daily["cloud_cover_mean"].
    """
    daily = payload.get("daily")
    if isinstance(daily, dict):
        if DAILY_CLOUD_CANONICAL in daily and "cloud_cover" not in daily:
            daily["cloud_cover"] = daily.get(DAILY_CLOUD_CANONICAL)
    return payload


# =========================
# Public API (dùng trong views)
# =========================
def om_forecast_daily(
    province_code: str | int,
    start: date,
    end: date,
    daily_fields: List[str],
) -> Dict[str, Any]:
    """
    Lấy daily từ Forecast API cho khoảng ngày [start, end].
    daily_fields ví dụ:
      ["temperature_2m_max","temperature_2m_min","precipitation_sum","wind_speed_10m_max","cloud_cover_mean"]

    ✅ Bạn cũng có thể truyền "cloud_cover" => backend tự đổi sang "cloud_cover_mean".
    """
    lat, lon = _get_latlon_by_province_code(province_code)

    normalized = _normalize_daily_fields(daily_fields)

    payload = _om_get(
        OPEN_METEO_FORECAST_BASE,
        lat,
        lon,
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(normalized),
        },
    )
    return _alias_daily_cloud(payload)


def om_archive_daily(
    province_code: str | int,
    start: date,
    end: date,
    daily_fields: List[str],
) -> Dict[str, Any]:
    """
    Lấy daily từ Archive API cho khoảng ngày [start, end] (quá khứ).
    ✅ Normalize cloud field tương tự forecast daily.
    """
    lat, lon = _get_latlon_by_province_code(province_code)

    normalized = _normalize_daily_fields(daily_fields)

    payload = _om_get(
        OPEN_METEO_ARCHIVE_BASE,
        lat,
        lon,
        {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": ",".join(normalized),
        },
    )
    return _alias_daily_cloud(payload)


def get_weather_snapshot(
    province_code: str | int,
    day: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Dùng cho export PDF từ popup (temp/humidity/wind/cloud/rain).
    - Nếu day=None hoặc day=today: dùng Forecast 'current=' để lấy số liệu hiện tại.
    - Nếu day là ngày quá khứ: dùng Archive 'hourly=' (start=end=day) và lấy giá trị gần 12:00 trưa (giảm lệch).

    Trả về dict chuẩn:
      {
        "province_name": "...",
        "time": "...",
        "temperature_c": ...,
        "humidity_percent": ...,
        "wind_kmh": ...,
        "wind_dir_deg": ...,
        "cloud_percent": ...,
        "precip_mm": ...
      }
    """
    lat, lon = _get_latlon_by_province_code(province_code)
    code = _normalize_code(province_code)

    # Lấy name để in PDF (không bắt buộc nhưng nên có)
    province_name = None
    with connection.cursor() as cur:
        cur.execute(f"select name from {PROVINCES_TABLE} where code=%s limit 1", [code])
        r = cur.fetchone()
        province_name = r[0] if r else None

    if day is None:
        day = date.today()

    today = date.today()

    # ====== TODAY => current ======
    if day == today:
        payload = _om_get(
            OPEN_METEO_FORECAST_BASE,
            lat,
            lon,
            {
                # Các biến current (v1)
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
        )
        cur = payload.get("current") or {}

        return {
            "province_code": code,
            "province_name": province_name,
            "time": cur.get("time"),
            "temperature_c": _safe_float(cur.get("temperature_2m")),
            "humidity_percent": _safe_float(cur.get("relative_humidity_2m")),
            "wind_kmh": _safe_float(cur.get("wind_speed_10m")),
            "wind_dir_deg": _safe_float(cur.get("wind_direction_10m")),
            "cloud_percent": _safe_float(cur.get("cloud_cover")),
            "precip_mm": _safe_float(cur.get("precipitation")),
        }

    # ====== PAST DAY => archive hourly ======
    # Chọn mốc 12:00 tại local time để lấy snapshot tương đối đại diện
    target_dt = datetime.fromisoformat(day.isoformat() + "T12:00")

    hourly_vars = [
        "temperature_2m",
        "relative_humidity_2m",
        "precipitation",
        "cloud_cover",
        "wind_speed_10m",
        "wind_direction_10m",
    ]

    payload = _om_get(
        OPEN_METEO_ARCHIVE_BASE,
        lat,
        lon,
        {
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "hourly": ",".join(hourly_vars),
        },
    )

    hourly = payload.get("hourly") or {}
    times: List[str] = hourly.get("time") or []
    if not times:
        # fallback nếu archive không có time
        return {
            "province_code": code,
            "province_name": province_name,
            "time": None,
            "temperature_c": None,
            "humidity_percent": None,
            "wind_kmh": None,
            "wind_dir_deg": None,
            "cloud_percent": None,
            "precip_mm": None,
        }

    i = _pick_hour_index(times, target_dt)

    def at(var: str) -> Optional[float]:
        arr = hourly.get(var)
        if not isinstance(arr, list) or i >= len(arr):
            return None
        return _safe_float(arr[i])

    return {
        "province_code": code,
        "province_name": province_name,
        "time": times[i] if i < len(times) else None,
        "temperature_c": at("temperature_2m"),
        "humidity_percent": at("relative_humidity_2m"),
        "wind_kmh": at("wind_speed_10m"),
        "wind_dir_deg": at("wind_direction_10m"),
        "cloud_percent": at("cloud_cover"),
        "precip_mm": at("precipitation"),
    }
