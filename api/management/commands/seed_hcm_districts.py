import re
import time
import unicodedata
import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Place

OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"

DISTRICTS = [
    "Quận 1","Quận 2","Quận 3","Quận 4","Quận 5","Quận 6","Quận 7","Quận 8","Quận 9","Quận 10","Quận 11","Quận 12",
    "Quận Bình Thạnh","Quận Gò Vấp","Quận Phú Nhuận","Quận Tân Bình","Quận Tân Phú","Quận Bình Tân",
    "Thủ Đức","Nhà Bè","Hóc Môn","Bình Chánh","Củ Chi","Cần Giờ",
]

def slugify_vi(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def strip_accents(s: str) -> str:
    x = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in x if unicodedata.category(ch) != "Mn")

def make_variants(name_vi: str) -> list[str]:
    """
    Tạo vài biến thể để tăng tỉ lệ match (VN có dấu / không dấu / English District n).
    """
    v = [name_vi]

    no_acc = strip_accents(name_vi)
    if no_acc != name_vi:
        v.append(no_acc)

    m = re.match(r"(?i)quận\s*(\d+)$", name_vi.strip())
    if m:
        n = m.group(1)
        v.append(f"District {n}")
        v.append(f"Dist {n}")

    # Một số tên hay gặp dạng tiếng Anh / không dấu
    repl = {
        "Thủ Đức": ["Thu Duc", "Thu Duc City", "Thanh pho Thu Duc"],
        "Nhà Bè": ["Nha Be"],
        "Hóc Môn": ["Hoc Mon"],
        "Bình Chánh": ["Binh Chanh"],
        "Củ Chi": ["Cu Chi"],
        "Cần Giờ": ["Can Gio"],
        "Quận Bình Thạnh": ["Binh Thanh"],
        "Quận Gò Vấp": ["Go Vap"],
        "Quận Phú Nhuận": ["Phu Nhuan"],
        "Quận Tân Bình": ["Tan Binh"],
        "Quận Tân Phú": ["Tan Phu"],
        "Quận Bình Tân": ["Binh Tan"],
    }
    for k, extra in repl.items():
        if name_vi.strip().lower() == k.strip().lower():
            v.extend(extra)

    # unique
    seen = set()
    out = []
    for x in v:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

def geocode_open_meteo(query: str) -> dict | None:
    """
    Open-Meteo: name + countryCode (ISO alpha2).
    """
    r = requests.get(
        OPEN_METEO_GEOCODE,
        params={
            "name": query,
            "count": 10,
            "language": "vi",
            "format": "json",
            "countryCode": "VN",
        },
        timeout=20,
    )
    r.raise_for_status()
    data = r.json() or {}
    results = data.get("results") or []
    if not results:
        return None

    # Ưu tiên country_code=VN và admin1 có "Ho Chi Minh"
    def score(x: dict) -> int:
        sc = 0
        if (x.get("country_code") or "").upper() == "VN":
            sc += 10
        admin1 = (x.get("admin1") or "").lower()
        if "ho chi minh" in admin1:
            sc += 10
        sc += int(x.get("population") or 0) // 100000
        return sc

    return sorted(results, key=score, reverse=True)[0]

def geocode_nominatim(query: str) -> dict | None:
    """
    Nominatim Search endpoint. Phải set User-Agent & tôn trọng 1 req/s.
    """
    r = requests.get(
        NOMINATIM_SEARCH,
        params={
            "q": query,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "vn",
            "accept-language": "vi",
            "addressdetails": 1,
        },
        headers={
            # User-Agent "thật" để khỏi bị chặn
            "User-Agent": "meteo-app/1.0 (seed_hcm_districts; local dev)",
        },
        timeout=25,
    )
    r.raise_for_status()
    arr = r.json() or []
    if not arr:
        return None
    return arr[0]

class Command(BaseCommand):
    help = "Seed HCM districts into places table (Open-Meteo geocoding with Nominatim fallback)"

    def handle(self, *args, **options):
        ok = 0
        miss = 0

        for name_vi in DISTRICTS:
            code = f"hcm-{slugify_vi(name_vi)}"

            # Thử nhiều variant
            variants = make_variants(name_vi)

            hit = None
            used = None

            # 1) Open-Meteo (GeoNames) — hay fail với quận/huyện VN
            for v in variants:
                q = f"{v}, Ho Chi Minh City"
                try:
                    hit = geocode_open_meteo(q)
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f"Open-Meteo error ({name_vi} / {v}): {e}"))
                    hit = None
                if hit:
                    used = f"open-meteo:{v}"
                    lat = float(hit["latitude"])
                    lon = float(hit["longitude"])
                    meta = {
                        "provider": "open-meteo",
                        "geocoding_id": hit.get("id"),
                        "raw_name": hit.get("name"),
                        "admin1": hit.get("admin1"),
                        "admin2": hit.get("admin2"),
                        "timezone": hit.get("timezone"),
                        "variant": v,
                    }
                    break

            # 2) Fallback Nominatim (OSM) — tỉ lệ match quận/huyện VN tốt hơn
            if not hit:
                for v in variants:
                    q = f"{v}, Thành phố Hồ Chí Minh, Việt Nam"
                    try:
                        nm = geocode_nominatim(q)
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(f"Nominatim error ({name_vi} / {v}): {e}"))
                        nm = None

                    # Nominatim policy: max 1 request/s
                    time.sleep(1.1)

                    if nm:
                        used = f"nominatim:{v}"
                        lat = float(nm["lat"])
                        lon = float(nm["lon"])
                        meta = {
                            "provider": "nominatim",
                            "display_name": nm.get("display_name"),
                            "osm_type": nm.get("osm_type"),
                            "osm_id": nm.get("osm_id"),
                            "class": nm.get("class"),
                            "type": nm.get("type"),
                            "address": nm.get("address"),
                            "variant": v,
                        }
                        hit = nm
                        break

            if not hit:
                miss += 1
                self.stderr.write(self.style.WARNING(f"NOT FOUND: {name_vi}"))
                continue

            with transaction.atomic():
                Place.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name_vi,
                        "kind": "hcm_district",
                        "lat": lat,
                        "lon": lon,
                        "meta": meta,
                    },
                )

            ok += 1
            self.stdout.write(self.style.SUCCESS(f"OK: {name_vi} -> {lat},{lon} ({used})"))

        self.stdout.write(self.style.SUCCESS(f"DONE. ok={ok}, not_found={miss}"))
