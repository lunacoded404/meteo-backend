from django.core.management.base import BaseCommand
from api.models import MapLayer

SEED = [
    {"key": "temp",     "name": "Nhiệt Độ",  "icon": "Thermometer", "is_enabled": True},
    {"key": "wind",     "name": "Gió",       "icon": "Wind",        "is_enabled": True},
    {"key": "rain",     "name": "Mưa",       "icon": "Umbrella",    "is_enabled": True},
    {"key": "humidity", "name": "Độ Ẩm",     "icon": "Droplet",     "is_enabled": True},
    {"key": "cloud",    "name": "Mây",       "icon": "Cloudy",      "is_enabled": True},
]

class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        for row in SEED:
            MapLayer.objects.update_or_create(
                key=row["key"],
                defaults=row,
            )
        self.stdout.write(self.style.SUCCESS("Seeded MapLayer OK"))
