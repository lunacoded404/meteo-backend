from rest_framework import mixins, viewsets
from api.models import MapLayer
from api.serializers import MapLayerAdminSerializer
from api.permissions import IsAdminRole

class AdminMapLayerViewSet(mixins.ListModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAdminRole]
    serializer_class = MapLayerAdminSerializer
    queryset = MapLayer.objects.all().order_by("id")
