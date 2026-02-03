# backend/backend/urls.py
from django.contrib import admin
from django.urls import path, include
from api.views_analytics import track_region, top_provinces
# from api.views_reports import export_popup_pdf
from api.views_compare import compare_week
from api.views_reports import admin_export_popup_pdf



# Token refresh view (used by frontend to exchange refresh -> access)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path("admin/", admin.site.urls),

    # auth
    path("api/auth/", include("api.auth_urls")),

    # token refresh endpoint
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # các api khác (nếu có)
    path("api/", include("api.urls")),

    path("api-auth/", include("rest_framework.urls")),

    path("api/track/region/", track_region),
    path("api/admin/analytics/top-provinces/", top_provinces),

    path("api/admin/reports/popup/<str:province_code>/pdf/", admin_export_popup_pdf),

    path("api/admin/reports/compare-week/<str:province_code>/", compare_week),
]
