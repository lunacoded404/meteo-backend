# api/views_compare.py
from datetime import date, timedelta
import requests
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from api.open_meteo import om_forecast_daily, om_archive_daily  # bạn tự implement gọi API

def week_range(d: date):
    # Monday=0
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start, end

@api_view(["GET"])
@permission_classes([IsAdminUser])
def compare_week(request, province_code: str):
    # ✅ guard: tránh /undefined/
    code = (province_code or "").strip()
    if not code or code.lower() == "undefined" or code.lower() == "null":
        return Response({"detail": "Invalid province_code"}, status=status.HTTP_400_BAD_REQUEST)

    today = date.today()
    this_start, this_end = week_range(today)
    last_start = this_start - timedelta(days=7)
    last_end = this_end - timedelta(days=7)

    def avg(arr):
        if not isinstance(arr, list):
            return None
        xs = [x for x in arr if x is not None]
        return (sum(xs) / len(xs)) if xs else None

    def sum0(arr):
        if not isinstance(arr, list):
            return 0
        return sum((x or 0) for x in arr)

    def summarize(payload):
        d = (payload or {}).get("daily") or {}
        return {
            "tmax_avg": avg(d.get("temperature_2m_max", [])),
            "tmin_avg": avg(d.get("temperature_2m_min", [])),
            "rain_sum": sum0(d.get("precipitation_sum", [])),
            "wind_max_avg": avg(d.get("wind_speed_10m_max", [])),
            "cloud_avg": avg(d.get("cloud_cover_mean", d.get("cloud_cover", []))),  # ✅ fallback
        }

    def diff(a, b):
        if a is None or b is None:
            return None
        return a - b

    # daily fields: thử cloud_cover_mean trước; nếu upstream 400 thì fallback cloud_cover
    daily_fields_primary = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "wind_speed_10m_max",
        "cloud_cover_mean",
    ]
    daily_fields_fallback = [
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "wind_speed_10m_max",
        "cloud_cover",
    ]

    try:
        try:
            this_week = om_forecast_daily(code, this_start, this_end, daily_fields_primary)
            last_week = om_archive_daily(code, last_start, last_end, daily_fields_primary)
        except requests.HTTPError as e:
            # ✅ nếu lỗi do field cloud_cover_mean không hỗ trợ => thử fallback cloud_cover
            resp = getattr(e, "response", None)
            body_text = ""
            try:
                body_text = (resp.text if resp is not None else "") or ""
            except Exception:
                body_text = ""

            if resp is not None and resp.status_code == 400 and "cloud_cover_mean" in body_text:
                this_week = om_forecast_daily(code, this_start, this_end, daily_fields_fallback)
                last_week = om_archive_daily(code, last_start, last_end, daily_fields_fallback)
            else:
                raise

        s_this = summarize(this_week)
        s_last = summarize(last_week)

        return Response(
            {
                "province_code": code,
                "ranges": {
                    "this_week": {"start": this_start.isoformat(), "end": this_end.isoformat()},
                    "last_week": {"start": last_start.isoformat(), "end": last_end.isoformat()},
                },
                "summary": {
                    "this_week": s_this,
                    "last_week": s_last,
                    "delta": {k: diff(s_this.get(k), s_last.get(k)) for k in s_this.keys()},
                },
                "series": {
                    "this_week": (this_week or {}).get("daily", {}) or {},
                    "last_week": (last_week or {}).get("daily", {}) or {},
                },
            }
        )

    except ValueError as e:
        # ✅ thường là: không tìm thấy province code hoặc thiếu centroid
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    except requests.HTTPError as e:
        # ✅ Open-Meteo trả 400/500: trả JSON rõ ràng
        resp = getattr(e, "response", None)
        upstream = None
        try:
            upstream = resp.json() if resp is not None else None
        except Exception:
            try:
                upstream = resp.text if resp is not None else None
            except Exception:
                upstream = None

        return Response(
            {"detail": "Open-Meteo request failed", "upstream": upstream},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    except Exception as e:
        # ✅ không trả HTML debug nữa
        return Response({"detail": f"Server error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
