"""
EACM通行证客户端 — 验证通行证JWT并获取用户信息
用于 algo_rank 等接入方项目
"""
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class PassportClient:
    """
    EACM通行证客户端
    通过HTTP调用通行证API验证JWT并获取用户信息
    """

    def __init__(self):
        self.base_url = settings.EACM_PASSPORT_BASE_URL
        self.client_id = settings.EACM_PASSPORT_CLIENT_ID
        self.client_secret = settings.EACM_PASSPORT_CLIENT_SECRET
        self.timeout = settings.EACM_PASSPORT_TOKEN_VERIFY_TIMEOUT

    def verify_token(self, access_token):
        """
        向通行证验证access_token，返回用户信息

        Args:
            access_token: 通行证签发的JWT access_token

        Returns:
            dict: 用户信息字典，包含 id, nickname, avatar
            None: 验证失败

        流程：
        1. 调用通行证的 /api/user/profile/ 接口，携带Bearer token
        2. 通行证验证自身JWT后返回用户信息
        3. 客户端信任通行证返回的数据
        """
        if not settings.EACM_PASSPORT_ENABLED:
            logger.warning("EACM通行证未启用")
            return None

        try:
            resp = requests.get(
                f"{self.base_url}/api/user/profile/",
                headers={
                    'Authorization': f'Bearer {access_token}',
                    'X-Client-ID': self.client_id,
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    return data.get('data')
                logger.warning(f"通行证返回错误: {data.get('message')}")
            else:
                logger.warning(f"通行证验证失败, HTTP {resp.status_code}")
        except requests.RequestException as e:
            logger.error(f"通行证连接失败: {e}")

        return None

    def get_oauth_login_url(self, provider, redirect_uri):
        """
        获取通行证的OAuth登录跳转URL

        实际流程：
        1. 前端调用 algo_rank 的 /api/v1/auth/passport/login/{provider}/
        2. algo_rank 后端调用通行证 /api/auth/login/{provider}/ 获取授权URL
        3. 返回给前端进行跳转
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/auth/login/{provider}/",
                json={'redirect_uri': redirect_uri},
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    return data['data']
        except requests.RequestException as e:
            logger.error(f"获取通行证登录URL失败: {e}")
        return None

    def handle_callback(self, provider, code, state, redirect_uri):
        """
        通行证OAuth回调处理

        实际流程：
        1. 前端拿到code后调用 algo_rank 的 /api/v1/auth/passport/callback/{provider}/
        2. algo_rank 后端转发到通行证 /api/auth/callback/{provider}/
        3. 通行证验证code并签发JWT
        4. algo_rank 拿到JWT后验证用户信息并创建/关联本地用户
        5. algo_rank 签发自己的JWT给前端
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/auth/callback/{provider}/",
                json={
                    'code': code,
                    'state': state,
                    'redirect_uri': redirect_uri,
                },
                timeout=self.timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get('code') == 200:
                    return data['data']
                logger.warning(f"通行证回调错误: {data.get('message')}")
        except requests.RequestException as e:
            logger.error(f"通行证回调处理失败: {e}")
        return None


# 全局单例
passport_client = PassportClient()