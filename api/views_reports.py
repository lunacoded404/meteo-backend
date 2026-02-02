import os
from datetime import date, datetime
from django.http import HttpResponse
from django.conf import settings

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework import status

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .open_meteo import get_weather_snapshot


_FONT_READY = False

def _ensure_vn_fonts():
    global _FONT_READY
    if _FONT_READY:
        return

    font_dir = os.path.join(settings.BASE_DIR, "assets", "fonts")
    regular = os.path.join(font_dir, "NotoSans-Regular.ttf")
    bold = os.path.join(font_dir, "NotoSans-Bold.ttf")

    if not os.path.exists(regular):
        raise FileNotFoundError(f"Missing font file: {regular}")
    if not os.path.exists(bold):
        raise FileNotFoundError(f"Missing font file: {bold}")

    pdfmetrics.registerFont(TTFont("VN", regular))
    pdfmetrics.registerFont(TTFont("VN-B", bold))
    _FONT_READY = True


def _draw_wrapped(c: canvas.Canvas, text: str, x: int, y: int, max_w: int, font="VN", size=11, leading=14):
    c.setFont(font, size)
    lines = simpleSplit(text or "", font, size, max_w)
    for line in lines:
        c.drawString(x, y, line)
        y -= leading
    return y


def fmt_date_vn(d: date) -> str:
    # ✅ dd/mm/yyyy
    return d.strftime("%d/%m/%Y")


def fmt_date_filename(d: date) -> str:
    # ✅ dd-mm-yyyy (tên file không được có "/")
    return d.strftime("%d-%m-%Y")


def fmt_time_vn(iso: str | None) -> str:
    """
    Nhận iso kiểu '2026-01-03T10:00' hoặc '2026-01-03 10:00'
    -> trả '10:00 • 03/01/2026'
    Nếu parse fail thì trả nguyên chuỗi.
    """
    if not iso:
        return "—"
    s = str(iso).strip()
    try:
        s2 = s.replace("Z", "").replace(" ", "T")
        dt = datetime.fromisoformat(s2)
        return dt.strftime("%H:%M")
    except Exception:
        return s


@api_view(["GET"])
@permission_classes([IsAdminUser])
def admin_export_popup_pdf(request, province_code: str):
    try:
        _ensure_vn_fonts()

        day_str = request.query_params.get("day")
        day = date.fromisoformat(day_str) if day_str else date.today()

        snap = get_weather_snapshot(province_code=province_code, day=day)

        filename = f"bao_cao_thoi_tiet_{province_code}_{fmt_date_filename(day)}.pdf"
        resp = HttpResponse(content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'

        c = canvas.Canvas(resp, pagesize=A4)
        w, h = A4

        left = 48
        right = 48
        max_w = int(w - left - right)
        y = h - 56

        # Title
        c.setFont("VN-B", 16)
        c.drawString(left, y, "BÁO CÁO THỜI TIẾT (ADMIN)")
        y -= 22

        province_name = snap.get("province_name") or snap.get("region_name") or ""
        time_str = fmt_time_vn(snap.get("time"))

        c.setFont("VN", 11)
        y = _draw_wrapped(c, f"Tỉnh/Thành: {province_name} ({province_code})", left, y, max_w, font="VN", size=11)
        y = _draw_wrapped(c, f"Ngày: {fmt_date_vn(day)}", left, y, max_w, font="VN", size=11)
        y = _draw_wrapped(c, f"Cập nhật lúc: {time_str}", left, y, max_w, font="VN", size=11)
        y -= 10

        c.setFont("VN-B", 12)
        c.drawString(left, y, "Dữ liệu từ popup")
        y -= 14

        rows = [
            ("Nhiệt độ", snap.get("temperature_c"), "°C"),
            ("Độ ẩm", snap.get("humidity_percent"), "%"),
            ("Gió", snap.get("wind_kmh"), "km/h"),
            ("Mây", snap.get("cloud_percent"), "%"),
            ("Lượng mưa", snap.get("precip_mm"), "mm"),
        ]

        c.setFont("VN", 11)
        for label, value, unit in rows:
            v = "—" if value is None else f"{value}"
            line = f"• {label}: {v} {unit}".strip()
            y = _draw_wrapped(c, line, left, y, max_w, font="VN", size=11, leading=15)

            if y < 80:
                c.showPage()
                y = h - 56
                c.setFont("VN", 11)

        y -= 10
        c.setFont("VN", 9)
        _draw_wrapped(c, "Nguồn dữ liệu: Open-Meteo", left, y, max_w, font="VN", size=9, leading=12)

        c.showPage()
        c.save()
        return resp

    except FileNotFoundError as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    except ValueError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({"detail": f"Server error: {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
