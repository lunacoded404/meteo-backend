from rest_framework_simplejwt.authentication import JWTAuthentication

class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        # Nếu có Authorization header thì dùng như bình thường
        header = self.get_header(request)
        if header is not None:
            return super().authenticate(request)

        # Nếu không có header, đọc từ cookie
        raw = request.COOKIES.get("access_token")
        if not raw:
            return None

        validated = self.get_validated_token(raw)
        return self.get_user(validated), validated
