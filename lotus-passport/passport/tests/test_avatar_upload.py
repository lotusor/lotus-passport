"""头像本地上传端点测试（§9.1）。"""
from __future__ import annotations

import io
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ..models import PassportUser

TMP_MEDIA = tempfile.mkdtemp(prefix="lp-avatar-test-")


def _png_bytes(size=(300, 300), color=(220, 80, 60)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class AvatarUploadTests(TestCase):
    def setUp(self):
        self.user = PassportUser.objects.create_user(
            email="avatar@lotus.local", nickname="头像测试"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_upload_valid_png_sets_avatar(self):
        resp = self.client.post(
            "/api/v1/profile/avatar/",
            {"file": SimpleUploadedFile("a.png", _png_bytes(), "image/png")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("/media/avatars/", resp.json()["avatar"])
        self.user.refresh_from_db()
        self.assertIn("/media/avatars/", self.user.avatar)

    def test_upload_rejects_oversize(self):
        big = b"\x89PNG\r\n\x1a\n" + b"\x00" * (128 * 1024 + 10)
        resp = self.client.post(
            "/api/v1/profile/avatar/",
            {"file": SimpleUploadedFile("big.png", big, "image/png")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 413)

    def test_upload_rejects_bad_content_type(self):
        resp = self.client.post(
            "/api/v1/profile/avatar/",
            {"file": SimpleUploadedFile("a.txt", b"hello", "text/plain")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 415)

    def test_upload_requires_auth(self):
        anon = APIClient()
        resp = anon.post(
            "/api/v1/profile/avatar/",
            {"file": SimpleUploadedFile("a.png", _png_bytes(), "image/png")},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 401)

    def test_reupload_deletes_old_file(self):
        first = self.client.post(
            "/api/v1/profile/avatar/",
            {"file": SimpleUploadedFile("a.png", _png_bytes(color=(1, 2, 3)), "image/png")},
            format="multipart",
        )
        first_path = TMP_MEDIA + first.json()["avatar"].replace("/media/", "/")
        self.assertTrue(__import__("os").path.exists(first_path))
        self.client.post(
            "/api/v1/profile/avatar/",
            {"file": SimpleUploadedFile("b.png", _png_bytes(color=(9, 9, 9)), "image/png")},
            format="multipart",
        )
        self.assertFalse(__import__("os").path.exists(first_path))
