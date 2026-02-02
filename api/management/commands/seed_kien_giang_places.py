import re
import time
import unicodedata
import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from api.models import Place

# Open-Meteo Geocoding (hay fail với huyện/xã VN), fallback Nominatim
OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"

KIEN_GIANG_PLACES = [
    "Rạch Giá",
    "Giồng Riềng",
    "Huyện Châu Thành",
    "Hòn Đất",
    "Phú Quốc",
    "Gò Quao",
    "Tân Hiệp",
    "An Biên",
    "Vĩnh Thuận",
    "Kiên Lương",
    "Hà Tiên",
    "Giang Thành",
    "Huyện Kiên Hải",
]

KIND = "kien_giang_place"
CODE_PREFIX = "kg"

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
    v = [name_vi, strip_accents(name_vi)]
    # bỏ tiền tố "Huyện " để tăng match
    if name_vi.lower().startswith("huyện "):
        v.append(name_vi[6:].strip())
        v.append(strip_accents(name_vi[6:].strip()))
    # unique
    out, seen = [], set()
    for x in v:
        x = x.strip()
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

def geocode_open_meteo(query: str) -> dict | None:
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

    # ưu tiên VN + admin1 có "Kien Giang"
    def score(x: dict) -> int:
        sc = 0
        if (x.get("country_code") or "").upper() == "VN":
            sc += 10
        admin1 = (x.get("admin1") or "").lower()
        if "kien giang" in admin1:
            sc += 10
        sc += int(x.get("population") or 0) // 100000
        return sc

    return sorted(results, key=score, reverse=True)[0]

def geocode_nominatim(query: str) -> dict | None:
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
            "User-Agent": "meteo-app/1.0 (seed_kien_giang_places; local dev)",
        },
        timeout=25,
    )
    r.raise_for_status()
    arr = r.json() or []
    if not arr:
        return None
    return arr[0]

class Command(BaseCommand):
    help = "Seed Kien Giang places into places table (Open-Meteo geocoding with Nominatim fallback)"

    def handle(self, *args, **options):
        ok, miss = 0, 0

        for name_vi in KIEN_GIANG_PLACES:
            code = f"{CODE_PREFIX}-{slugify_vi(name_vi)}"
            variants = make_variants(name_vi)

            hit = None
            lat = lon = None
            meta = {}
            used = None

            # 1) Open-Meteo
            for v in variants:
                q = f"{v}, Kien Giang, Vietnam"
                try:
                    om = geocode_open_meteo(q)
                except Exception as e:
                    self.stderr.write(self.style.WARNING(f"Open-Meteo error ({name_vi}/{v}): {e}"))
                    om = None

                if om:
                    used = f"open-meteo:{v}"
                    lat = float(om["latitude"])
                    lon = float(om["longitude"])
                    meta = {
                        "provider": "open-meteo",
                        "geocoding_id": om.get("id"),
                        "raw_name": om.get("name"),
                        "admin1": om.get("admin1"),
                        "admin2": om.get("admin2"),
                        "timezone": om.get("timezone"),
                        "variant": v,
                    }
                    hit = om
                    break

            # 2) Fallback Nominatim
            if not hit:
                for v in variants:
                    q = f"{v}, Kiên Giang, Việt Nam"
                    try:
                        nm = geocode_nominatim(q)
                    except Exception as e:
                        self.stderr.write(self.style.WARNING(f"Nominatim error ({name_vi}/{v}): {e}"))
                        nm = None

                    time.sleep(1.1)  # tôn trọng 1 req/s

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

            if not hit or lat is None or lon is None:
                miss += 1
                self.stderr.write(self.style.WARNING(f"NOT FOUND: {name_vi}"))
                continue

            with transaction.atomic():
                Place.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name_vi,
                        "kind": KIND,
                        "lat": lat,
                        "lon": lon,
                        "meta": meta,
                    },
                )

            ok += 1
            self.stdout.write(self.style.SUCCESS(f"OK: {name_vi} -> {lat},{lon} ({used}) [{code}]"))

        self.stdout.write(self.style.SUCCESS(f"DONE. ok={ok}, not_found={miss}"))
