# Contributing

感谢参与 Lotus Passport。这个仓库是**公开仓库**，提交前请先确认内容边界。

## 公开 / 私有边界

适合公开：

- 产品源代码、SDK、测试、类型定义
- 脱敏的 `.env.example` / `*.example` 配置模板
- 公开 API 契约、架构说明、开发文档
- 不含真实主机信息的本地 compose / nginx 示例

不得公开：

- 真实密码、Token、私钥、数据库连接串、OAuth secret、SMTP 授权码
- 服务器 IP、root / SSH 账号、面板地址、宿主路径、容器名、证书路径
- 交接文档、上线前验证报告、事故复盘、部署 runbook
- 真实用户数据、数据库转储、备份文件
- 构建缓存、截图、临时脚本、编辑器/IDE 文件
- 面向 Agent 的提示词、交付说明、会话日志或“用户决策”式工作记录

## 提交前检查

可选：安装 pre-commit 钩子，让门禁在每次 commit 前自动运行。

```bash
pip install pre-commit && pre-commit install
```

手动检查：

```bash
# 1. 当前树门禁：密钥、真实 .env、内部文档、公网 IP、默认凭据
python .github/scripts/check_public_repo.py

# 2. 后端测试
cd lotus-passport && python -m pytest -q

# 3. 前端构建
cd ../lotus-passport-security && npm ci && npm run build

# 4. 可选：更严格的门禁（把告警也当失败）
cd .. && python .github/scripts/check_public_repo.py --strict
```

如果你已经提交了敏感内容：

1. **先轮换凭据**，不要先删文件；
2. 立即把仓库设为私有或限制访问；
3. 评估是否用新仓库重建历史，或用 `git filter-repo` 清理；
4. 清理后 force-push，并联系 GitHub Support 清理旧 commit 缓存；
5. 检查 deploy keys、webhooks、Actions secrets 与服务器登录日志；
6. 在工作区接手文档中记录处置结果。

## 分支与提交

- 从 `main` 拉分支：`feat/<topic>`、`fix/<topic>`、`docs/<topic>`、`chore/<topic>`。
- 提交信息使用 Conventional Commits，例如：
  - `feat(auth): add PKCE code exchange`
  - `fix(oauth): reject mismatched redirect_uri`
  - `docs(security): document secret rotation`
- 一个 PR 只做一件事；避免把格式化、重构和功能混在一起。
- 不在提交信息里粘贴真实域名、IP、账号、密码或内部文档内容。

## Pull Request

- 描述“为什么”而不只是“改了什么”。
- 列出验证命令与结果。
- 涉及认证、OAuth、JWT、权限、上传、反代时，必须说明威胁模型与回滚方案。
- 公开仓库 PR 必须通过 CI 的 `public-repo-guard` 与测试。
- 不要在 PR 评论、截图或日志中粘贴真实凭据；如必须展示，先脱敏。

## 代码与文档

- 后端遵循 Django / DRF 现有结构；新增模型必须提交迁移。
- 前端保持 TypeScript 类型检查零错误；新增页面遵循现有设计令牌。
- 注释解释“为什么”，不要粘贴会话过程、用户对话或 Agent 工作日志。
- 新增依赖需说明用途、许可证与安全影响。
- 公开文档不要引用私有交接文档的章节号；需要公开的规则请直接写在仓库文档中。

## 安全

漏洞请通过 [SECURITY.md](SECURITY.md) 的私有渠道报告，不要开公开 Issue。

## 许可证

提交即表示你同意以本仓库的 [MIT](LICENSE) 许可证发布贡献。
