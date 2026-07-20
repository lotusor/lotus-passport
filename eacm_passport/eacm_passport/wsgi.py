"""
WSGI config for E时代ACM令牌通行证系统
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eacm_passport.settings')
application = get_wsgi_application()