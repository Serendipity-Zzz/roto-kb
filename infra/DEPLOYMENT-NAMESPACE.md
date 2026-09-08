# 远端隔离命名空间

| 项目 | ROTO-KB | 现有第三方知识库 |
|---|---|---|
| systemd | `roto-kb.service` | `kb-server.service` |
| App | `127.0.0.1:8710` | `127.0.0.1:8700` |
| Qdrant | `127.0.0.1:6334` | embedded legacy store |
| Public | `/roto-kb/` | `/` |
| Code | `/home/ec2-user/roto-kb` | `/home/ec2-user/kb-server` |
| Source | `/data/roto-kb/sources` | `/data/knowledge-base` |
| Index | `/data/roto-kb/index` | `/home/ec2-user/.kb-server/data` |
| Logs | `/var/log/roto-kb` | `/home/ec2-user/kb-server.log` |

部署、备份、reload、回滚和清理脚本必须拒绝解析到 `/data/knowledge-base`、`/home/ec2-user/.kb-server` 或 `/home/ec2-user/kb-server` 的路径。

公网由 nginx 转发 `/roto-kb/` 到 `127.0.0.1:8710`。应用和 Qdrant 端口不得绑定 `0.0.0.0`；读取使用独立 read token，变更索引使用独立 admin token。

ROTO-KB 的 Qdrant 使用独立 Docker 容器：宿主机 `127.0.0.1:6334` 映射容器 REST 端口 `6333`，数据只写入 `/data/roto-kb/qdrant`。gRPC 不映射到宿主机；collection 使用 `roto_kb_<release_id>`，线上 alias 固定为 `roto_kb_active`。Qdrant 自身使用独立 API key，不复用 ROTO-KB 的 read/admin token。
