# EACM通行证 — 项目1 (algo_rank) 集成包

## 集成方案说明

algo_rank 作为 OAuth 客户端接入 EACM 通行证系统，采用以下策略：

1. **双模式认证共存**：保留原有 username + 密码登录，新增通行证 OAuth 登录
2. **通行证 JWT 验证**：algo_rank 接收通行证签发的 JWT，通过 HTTP 调用通行证接口验证用户身份
3. **本地用户自动创建**：通行证用户首次登录时，自动在 algo_rank 创建本地用户（需要选择学校）
4. **账户关联**：本地 User 模型新增 `passport_user_id` 字段关联通行证用户

## 文件清单

### 需要新增的文件
- `apps/auth_app/passport_client.py` — 通行证客户端（验证JWT、获取用户信息）
- `apps/auth_app/passport_views.py` — 通行证认证视图
- `apps/auth_app/passport_serializers.py` — 通行证相关序列化器
- `tests/test_passport_integration.py` — 集成测试脚本

### 需要修改的文件
- `config/settings.py` — 添加通行证配置
- `apps/auth_app/urls.py` — 添加通行证路由
- `apps/auth_app/models.py` — 添加 passport_user_id 字段
- `apps/auth_app/serializers.py` — 添加 passport_user_id 字段
- `requirements.txt` — 添加 cryptography 依赖
- `.env` — 添加通行证环境变量

## 使用方式

运行 `apply_integration.py` 一键应用所有变更，或手动按照各文件中的注释操作。