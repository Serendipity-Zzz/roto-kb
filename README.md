# ROTO-KB

ROTO 的独立工程知识服务仓库。它与主线 `ROTO` 通过版本化 `EvidencePackage`/HTTP 契约集成，不共享进程、索引或知识源目录。

远端仓库：`https://github.com/Serendipity-Zzz/roto-kb`

- 产品需求：[docs/PRD.md](docs/PRD.md)
- 软件设计：[docs/SDD.md](docs/SDD.md)
- 开发子任务：[docs/DEVELOPMENT-TASKS.md](docs/DEVELOPMENT-TASKS.md)
- 前置条件：[docs/PRE-REQUISITES.md](docs/PRE-REQUISITES.md)
- 详细任务：[docs/RAG-DETAILED-TASKS.md](docs/RAG-DETAILED-TASKS.md)
- 图谱种子选型：[docs/GRAPH-SEED-SELECTION.md](docs/GRAPH-SEED-SELECTION.md)
- 知识资源：[knowledge/manifest.yaml](knowledge/manifest.yaml)
- 资源说明：[docs/RESOURCE-NOTES.md](docs/RESOURCE-NOTES.md)

Qdrant 是本服务使用的向量数据库，不是模型或知识图谱。默认采用本机嵌入式模式（`QDRANT_MODE=embedded`），数据落在 `.roto-kb/qdrant`（本地）或 `/data/roto-kb/index/qdrant`（服务器），不占用公网端口。可选的独立 Server 模式见 `infra/docker-compose.yml`。Agent 检索用法见 [`docs/SKILL.md`](docs/SKILL.md)。

本地联调可在 `.env` 设置 `ROTO_KB_ENV_FILE`，指向一个未提交 Git 的共享 secret env 文件；服务会按“进程环境 > 外部 env 文件 > 本仓 `.env` > 默认值”加载配置。这样调用方与服务端可以共用 read/admin token，避免复制密钥导致 `401 auth.invalid`。生产仍只使用 systemd 的 `/etc/roto-kb/roto-kb.env`。

模型 API 供应商为阿里云百炼 Model Studio（DashScope），通过 OpenAI-compatible endpoint 调用。当前仓库只包含配置契约，不包含 API key，也不会在文档阶段调用远端模型。

V1 图谱内容采用 QUDT、IOF Core、W3C PROV-O/DCAT 3/SHACL 和 ROTO 自有种子，全部可离线编译；材料数据库、SPARQL 和许可证不清晰的外部图谱不作为运行时依赖。

服务器上的现有第三方 `kb-server`、`/data/knowledge-base` 和 `~/.kb-server` 不属于本仓库，禁止读取、修改或复用。
