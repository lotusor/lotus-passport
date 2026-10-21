"""Rotate the active RS256 signing key (old keys stay valid until pruned)."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "轮换激活的 RS256 签名密钥。生成新密钥并提升为激活态，旧密钥保留 "
        "retention-days 天（默认 16 ≈ refresh TTL 14d + 2d 缓冲），期间旧 refresh "
        "token 仍可验证。JWKS 端点会同时发布新旧公钥，接入方平滑过渡。\n"
        "使用 PASSPORT_JWT_PRIVATE_KEY/PUBLIC_KEY（env PEM）时无法轮换文件密钥，"
        "需改在部署侧更换这对环境变量并重启。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--bit-length", type=int, default=2048)
        parser.add_argument(
            "--retention-days",
            type=int,
            default=16,
            help="旧密钥保留天数（须 >= 最长 refresh token 生命周期）",
        )

    def handle(self, *args, **options):
        ks = settings.KEY_STORE
        if ks._using_env:
            raise CommandError(
                "当前使用 env PEM（PASSPORT_JWT_PRIVATE_KEY/PUBLIC_KEY），"
                "无法轮换文件密钥。请在部署侧更换这对环境变量后滚动重启。"
            )

        old_kid = ks.active_kid
        new_kid = ks.rotate(
            bit_length=options["bit_length"], retention_days=options["retention_days"]
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"已轮换激活密钥：{old_kid} -> {new_kid}\n"
                f"旧密钥保留 {options['retention_days']} 天（此前签发的 refresh token 仍可验证）。\n"
                f"JWKS 已同时发布新旧公钥；接入方最长 {options['retention_days']} 天后停止接受旧 token。"
            )
        )
