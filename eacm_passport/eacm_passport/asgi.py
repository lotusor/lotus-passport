"""
ASGI config for E时代ACM令牌通行证系统
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eacm_passport.settings')
application = get_asgi_application()