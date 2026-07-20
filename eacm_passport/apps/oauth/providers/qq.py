"""
QQ OAuth2.0提供者
"""
from urllib.parse import parse_qs
import requests
from .base import OAuthProviderBase
from .wechat import OAuthError


class QQProvider(OAuthProviderBase):
    provider_name = 'qq'

    def get_authorize_params(self, redirect_uri, state):
        return {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self.scope,
            'state': state,
        }

    def exchange_token(self, code, redirect_uri):
        params = {
            'grant_type': 'authorization_code',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'code': code,
            'redirect_uri': redirect_uri,
        }
        resp = requests.get(self.token_url, params=params, timeout=10)
        resp.raise_for_status()
        # QQ返回的是 text/plain 格式: access_token=xxx&expires_in=xxx&refresh_token=xxx
        parsed = parse_qs(resp.text)
        if 'error' in parsed:
            raise OAuthError(f"QQ token交换失败: {parsed.get('error_description', [''])[0]}")
        return {
            'access_token': parsed.get('access_token', [''])[0],
            'refresh_token': parsed.get('refresh_token', [''])[0],
            'expires_in': int(parsed.get('expires_in', ['0'])[0]),
        }

    def get_user_info(self, token_response):
        access_token = token_response['access_token']
        # QQ需要先获取openid
        resp = requests.get(
            'https://graph.qq.com/oauth2.0/me',
            params={'access_token': access_token},
            timeout=10
        )
        resp.raise_for_status()
        # 返回格式: callback( {"client_id":"xxx","openid":"xxx"} );
        import json
        text = resp.text
        start = text.index('{')
        end = text.rindex('}') + 1
        me_data = json.loads(text[start:end])
        openid = me_data['openid']

        # 获取用户信息
        resp = requests.get(
            self.userinfo_url,
            params={
                'access_token': access_token,
                'oauth_consumer_key': self.app_id,
                'openid': openid,
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get('ret', -1) != 0:
            raise OAuthError(f"QQ获取用户信息失败: {data.get('msg', '')}")

        return {
            'provider_user_id': openid,
            'nickname': data.get('nickname', ''),
            'avatar': data.get('figureurl_qq_2', data.get('figureurl_qq_1', '')),
        }