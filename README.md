# ROTO-KB

ROTO 的独立工程知识服务仓库。它与主线 `ROTO` 通过版本化 `EvidencePackage`/HTTP 契约集成，不共享进程、索引或知识源目录。

远端仓库：`https://github.com/Serendipity-Zzz/roto-kb`

- 产品需求：[docs/PRD.md](docs/PRD.md)
- 软件设计：[docs/SDD.md](docs/SDD.md)
- 开发子任务：[docs/DEVELOPMENT-TASKS.md](docs/DEVELOPMENT-TASKS.md)
- 图谱种子选型：[docs/GRAPH-SEED-SELECTION.md](docs/GRAPH-SEED-SELECTION.md)
- 知识资源：[knowledge/manifest.yaml](knowledge/manifest.yaml)
- 资源说明：[docs/RESOURCE-NOTES.md](docs/RESOURCE-NOTES.md)

Qdrant 是本服务使用的向量数据库，不是模型或知识图谱。本地不要求手工安装，后续由 Docker Compose 启动；生产环境使用独立容器和 `/data/roto-kb/qdrant` 持久化目录，仅通过 `127.0.0.1:6334` 向 ROTO-KB 应用开放。

模型 API 供应商为阿里云百炼 Model Studio（DashScope），通过 OpenAI-compatible endpoint 调用。当前仓库只包含配置契约，不包含 API key，也不会在文档阶段调用远端模型。

V1 图谱内容采用 QUDT、IOF Core、W3C PROV-O/DCAT 3/SHACL 和 ROTO 自有种子，全部可离线编译；材料数据库、SPARQL 和许可证不清晰的外部图谱不作为运行时依赖。

服务器上的现有第三方 `kb-server`、`/data/knowledge-base` 和 `~/.kb-server` 不属于本仓库，禁止读取、修改或复用。
