# CursorTokenTray 云同步服务

FastAPI + SQLite。客户端把账号和配置封进 PBKDF2 + AES-256-GCM 信封后上传，**服务器不解密，也看不到 Token**。

对外地址写死在客户端：`https://sync.harker.cn`

## 本地运行

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JWT_SECRET=请换成足够长的随机串
export DATABASE_PATH=./data/sync.db
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000
```

```bash
PYTHONPATH=. python -m unittest tests.test_api -v
```

## Docker

```bash
cd server
export JWT_SECRET=请换成足够长的随机串
docker compose up -d --build
```

前面用 Caddy / Nginx 做 HTTPS，反代到 `127.0.0.1:8000`，并把 `sync.harker.cn` 指过来。若反代会带 `X-Forwarded-For`，保持 `TRUST_PROXY=1`。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| POST | `/v1/auth/register` | 开放注册，`{email,password}` |
| POST | `/v1/auth/login` | 登录 |
| POST | `/v1/auth/refresh` | `{refresh_token}` |
| POST | `/v1/auth/logout` | 作废 refresh |
| GET | `/v1/me` | 当前用户 |
| GET | `/v1/sync` | 取加密信封 + revision |
| PUT | `/v1/sync` | `{revision, envelope}`，revision 不对返回 409 |

密码至少 8 位，邮箱小写去重，无需验证。Access token 默认 15 分钟，refresh 30 天。
