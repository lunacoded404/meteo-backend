from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from api.models import MapLayer

@api_view(["GET"])
@permission_classes([AllowAny])
def map_layers_public(request):
    qs = MapLayer.objects.all().order_by("id")
    return Response([
        {"key": x.key, "name": x.name, "is_enabled": x.is_enabled, "icon": x.icon}
        for x in qs
    ])
