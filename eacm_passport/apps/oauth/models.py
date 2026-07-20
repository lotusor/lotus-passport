"""
第三方OAuth账号绑定模型
"""
import base64
import os
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from django.db import models
from django.conf import settings


def _get_aes_key():
    key = settings.AES_SECRET_KEY.encode('utf-8')
    if len(key) != 32:
        raise ValueError(f"AES_SECRET_KEY 必须为 32 字节，当前 {len(key)} 字节。请设置 AES_SECRET_KEY 环境变量。")
    return key


def encrypt_token(plaintext):
    """AES-256-CBC 加密"""
    if not plaintext:
        return ''
    key = _get_aes_key()
    iv = os.urandom(16)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    padded = plaintext.encode('utf-8')
    # PKCS7 padding
    pad_len = 16 - (len(padded) % 16)
    padded += bytes([pad_len] * pad_len)
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(iv + encrypted).decode('utf-8')


def decrypt_token(ciphertext):
    """AES-256-CBC 解密"""
    if not ciphertext:
        return ''
    try:
        key = _get_aes_key()
        raw = base64.b64decode(ciphertext)
        iv = raw[:16]
        encrypted = raw[16:]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted = decryptor.update(encrypted) + decryptor.finalize()
        # 移除PKCS7 padding
        pad_len = decrypted[-1]
        return decrypted[:-pad_len].decode('utf-8')
    except Exception:
        return ''


class OAuthAccount(models.Model):
    """
    第三方OAuth账号绑定记录
    一个用户可绑定多个第三方账号（微信/QQ/GitHub）
    """

    class Meta:
        verbose_name = "第三方账号绑定"
        verbose_name_plural = "第三方账号绑定"
        db_table = "eacm_oauth_account"
        unique_together = ('provider', 'provider_user_id')

    PROVIDER_CHOICES = [
        ('wechat', '微信'),
        ('qq', 'QQ'),
        ('github', 'GitHub'),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="oauth_accounts", verbose_name="关联用户"
    )
    provider = models.CharField(
        max_length=20, choices=PROVIDER_CHOICES, verbose_name="登录平台"
    )
    provider_user_id = models.CharField(max_length=128, verbose_name="第三方用户ID")
    provider_username = models.CharField(
        max_length=100, blank=True, default="", verbose_name="第三方用户名"
    )
    access_token = models.CharField(
        max_length=512, blank=True, default="", verbose_name="访问令牌(加密)"
    )
    refresh_token = models.CharField(
        max_length=512, blank=True, default="", verbose_name="刷新令牌(加密)"
    )
    token_expires_at = models.DateTimeField(
        null=True, blank=True, verbose_name="令牌过期时间"
    )
    bound_at = models.DateTimeField(auto_now_add=True, verbose_name="绑定时间")

    def set_access_token(self, token):
        self.access_token = encrypt_token(token)

    def get_access_token(self):
        return decrypt_token(self.access_token)

    def set_refresh_token(self, token):
        self.refresh_token = encrypt_token(token)

    def get_refresh_token(self):
        return decrypt_token(self.refresh_token)

    def __str__(self):
        return f"{self.get_provider_display()} - {self.provider_username or self.provider_user_id}"