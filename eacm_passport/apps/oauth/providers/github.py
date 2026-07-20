"""
GitHub OAuth2.0提供者
"""
import requests
from .base import OAuthProviderBase
from .wechat import OAuthError


class GitHubProvider(OAuthProviderBase):
    provider_name = 'github'

    def get_authorize_params(self, redirect_uri, state):
        return {
            'client_id': self.app_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self.scope,
            'state': state,
        }

    def exchange_token(self, code, redirect_uri):
        resp = requests.post(
            self.token_url,
            json={
                'client_id': self.app_id,
                'client_secret': self.app_secret,
                'code': code,
            },
            headers={'Accept': 'application/json'},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if 'error' in data:
            raise OAuthError(f"GitHub token交换失败: {data.get('error_description', data.get('error'))}")
        return data

    def get_user_info(self, token_response):
        access_token = token_response.get('access_token')
        resp = requests.get(
            self.userinfo_url,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Accept': 'application/json',
            },
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            'provider_user_id': str(data['id']),
            'nickname': data.get('name', '') or data.get('login', ''),
            'avatar': data.get('avatar_url', ''),
        }