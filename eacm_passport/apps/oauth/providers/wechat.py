"""
微信OAuth2.0提供者
"""
from urllib.parse import urlencode
import requests
from .base import OAuthProviderBase


class WeChatProvider(OAuthProviderBase):
    provider_name = 'wechat'

    def get_authorize_params(self, redirect_uri, state):
        return {
            'appid': self.app_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self.scope,
            'state': state,
        }

    def exchange_token(self, code, redirect_uri):
        params = {
            'appid': self.app_id,
            'secret': self.app_secret,
            'code': code,
            'grant_type': 'authorization_code',
        }
        resp = requests.get(self.token_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if 'errcode' in data and data['errcode'] != 0:
            raise OAuthError(f"微信token交换失败: {data.get('errmsg', '')}")
        return data

    def get_user_info(self, token_response):
        access_token = token_response.get('access_token')
        openid = token_response.get('openid')
        params = {
            'access_token': access_token,
            'openid': openid,
        }
        resp = requests.get(self.userinfo_url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if 'errcode' in data and data['errcode'] != 0:
            raise OAuthError(f"微信获取用户信息失败: {data.get('errmsg', '')}")
        return {
            'provider_user_id': openid,
            'nickname': data.get('nickname', ''),
            'avatar': data.get('headimgurl', ''),
        }


class OAuthError(Exception):
    pass