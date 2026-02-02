# api/views_analytics.py
from datetime import timedelta
from django.utils import timezone
from django.db import connection
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework import status

@api_view(["POST"])
@permission_classes([AllowAny])
def track_region(request):
    province_code = request.data.get("province_code")
    province_name = request.data.get("province_name")
    source = request.data.get("source")
    meta = request.data.get("meta") or {}

    if not province_code or source not in ("map", "search"):
        return Response({"detail": "bad_request"}, status=status.HTTP_400_BAD_REQUEST)

    session_id = request.headers.get("x-session-id") or None
    ua = request.headers.get("user-agent") or None
    ip = request.META.get("REMOTE_ADDR")

    with connection.cursor() as cur:
        cur.execute(
            """
            insert into public.region_events (source, province_code, province_name, session_id, ip, ua, meta)
            values (%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            [source, province_code, province_name, session_id, ip, ua, str(meta).replace("'", '"')],
        )

    return Response({"ok": True})

@api_view(["GET"])
@permission_classes([IsAdminUser])
def top_provinces(request):
    # query params: ?days=7&source=all
    days = int(request.query_params.get("days", "7"))
    source = request.query_params.get("source", "all")
    since = timezone.now() - timedelta(days=days)

    args = [since]
    where_source = ""
    if source in ("map", "search"):
        where_source = "and source = %s"
        args.append(source)

    with connection.cursor() as cur:
        cur.execute(
            f"""
            select province_code,
                   coalesce(max(province_name), '') as province_name,
                   count(*)::int as hits,
                   sum(case when source='map' then 1 else 0 end)::int as map_hits,
                   sum(case when source='search' then 1 else 0 end)::int as search_hits
            from public.region_events
            where occurred_at >= %s
            {where_source}
            group by province_code
            order by hits desc
            limit 20
            """,
            args,
        )
        rows = cur.fetchall()

    data = [
        {
            "province_code": r[0],
            "province_name": r[1],
            "hits": r[2],
            "map_hits": r[3],
            "search_hits": r[4],
        }
        for r in rows
    ]
    return Response({"since": since.isoformat(), "days": days, "items": data})
