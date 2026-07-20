"""
OAuth提供者基类
"""
import secrets
from abc import ABC, abstractmethod
from urllib.parse import urlencode, parse_qs, urljoin

import requests


class OAuthProviderBase(ABC):
    """OAuth2.0 提供者抽象基类"""

    provider_name = ''

    def __init__(self, config):
        self.app_id = config.get('app_id', '')
        self.app_secret = config.get('app_secret', '') or config.get('app_key', '')
        self.authorize_url = config.get('authorize_url', '')
        self.token_url = config.get('token_url', '')
        self.userinfo_url = config.get('userinfo_url', '')
        self.scope = config.get('scope', '')

    @abstractmethod
    def get_authorize_params(self, redirect_uri, state):
        """获取授权URL参数"""
        pass

    @abstractmethod
    def exchange_token(self, code, redirect_uri):
        """用授权码换取access_token，返回原始响应字典"""
        pass

    @abstractmethod
    def get_user_info(self, token_response):
        """根据token响应获取用户信息，返回标准化字典"""
        pass

    def build_authorize_url(self, redirect_uri, state):
        params = self.get_authorize_params(redirect_uri, state)
        return f"{self.authorize_url}?{urlencode(params)}"

    @staticmethod
    def generate_state():
        return secrets.token_urlsafe(32)