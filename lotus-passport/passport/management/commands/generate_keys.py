"""Generate the initial RSA keypair for RS256 (idempotent; --force to replace)."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "生成初始 RSA 密钥对（RS256）。写入 PASSPORT_JWT_KEYS_DIR 下的 "
        "manifest.json + private_<kid>.pem/public_<kid>.pem。已存在则跳过；"
        "--force 覆盖重建。使用 PASSPORT_JWT_PRIVATE_KEY/PUBLIC_KEY 时无需此命令。"
    )

    def add_arguments(self, parser):
        parser.add_argument("--bit-length", type=int, default=2048)
        parser.add_argument(
            "--force",
            action="store_true",
            help="删除已有密钥并重新生成（会令此前签发的 token 立即失效）",
        )

    def handle(self, *args, **options):
        ks = settings.KEY_STORE
        if ks._using_env:
            raise CommandError(
                "已通过 PASSPORT_JWT_PRIVATE_KEY / PASSPORT_JWT_PUBLIC_KEY 提供密钥，"
                "无需生成文件密钥。"
            )

        if options["force"]:
            import glob
            import os

            for pattern in ("*_*.pem", "manifest.json", "manifest.json.tmp"):
                for f in glob.glob(os.path.join(ks.keys_dir, pattern)):
                    try:
                        os.remove(f)
                    except OSError:  # noqa: BLE001
                        pass
            ks._manifest = None

        kid = ks.ensure_initial(kid=settings.JWT_KID, bit_length=options["bit_length"])
        self.stdout.write(
            self.style.SUCCESS(
                f"RSA 密钥已就绪：kid={kid}  目录={ks.keys_dir}\n"
                f"请将 public_<kid>.pem 的内容发布给接入方（或经 /.well-known/jwks.json 自动获取）。"
            )
        )
