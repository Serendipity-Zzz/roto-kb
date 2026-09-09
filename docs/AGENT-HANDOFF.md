# ROTO-KB RAG Agent Handoff

用于将 ROTO-KB 独立 RAG 工程交给下一位 agent。本文是执行上下文摘要；产品和技术细节以 PRD/SDD 为准。

## 1. 必读文件（按顺序）

1. `docs/PRD.md`：产品范围、EvidencePackage v1、API、发布策略、安全和验收目标。
2. `docs/SDD.md`：组件边界、数据模型、端口、状态机、降级、API、release、部署、恢复和测试设计。
3. `docs/RAG-DETAILED-TASKS.md`：本次 RAG 的 G0-G8 详细任务、依赖、输入/输出、验收、回滚和并行关系；实现任务以此为主。
4. `docs/PRE-REQUISITES.md`：当前前置状态、跨仓契约阻塞项、DashScope 配置、IP-SAN TLS 和服务器门槛。
5. `docs/DEVELOPMENT-TASKS.md`：旧的粗粒度任务索引；详细任务和新端口策略以 `RAG-DETAILED-TASKS.md` 为准。
6. `infra/DEPLOYMENT-NAMESPACE.md`：ROTO-KB 与服务器现有第三方知识库的目录、端口、服务、Qdrant 和公网路径隔离矩阵。

## 2. 知识源与图谱文件

- `knowledge/manifest.yaml`：内容清单、部署地址、模型供应商、IP-SAN TLS 策略、资源状态和禁止路径。
- `knowledge/graph/deployment-manifest.yaml`：V1 图谱白名单和离线解析策略；只读该清单允许的文件。
- `knowledge/graph/seeds/roto-domain-seed.v1.jsonl`：ROTO 自有 41 nodes、18 relations、3 rules 的领域种子。
- `knowledge/official-docs/`：已下载的 FEniTop、Gmsh、CadQuery、DOLFINx、JAX-FEM、meshio、trimesh、PyVista、MFEM、NGSolve、MOOSE 等资料。
- `knowledge/papers/`：已下载的 JAX-FEM、TopoDiff、形态美学、形状偏好论文。
- `knowledge/ontologies/qudt/`：QUDT；V1 只按 deployment manifest 的 allowlist 文件解析。
- `knowledge/ontologies/iof-core/core/Core.rdf`：IOF Core released core；不运行远程 import closure。
- `knowledge/ontologies/w3c/`：PROV-O、DCAT 3、SHACL 静态词汇。
- `docs/GRAPH-SEED-SELECTION.md`：图谱最终选入/排除、许可和更新理由。
- `docs/RESOURCE-NOTES.md`：资料下载和许可备注。
- `knowledge/checksums.sha256`：当前知识文件的 SHA-256 清单；修改 manifest 或图谱部署清单后必须更新并全量校验。

V1 active 图谱固定为 QUDT、IOF Core、W3C PROV-O/DCAT3/SHACL 和 ROTO seed。CORA、PropNet 只保留 reference-only；MatOnto 只保留 link-and-map-only。SciBERT/MatSciBERT 是后续可选实体抽取模型，Hunyuan3D 是主线几何生成模型，均不是 V1 知识图谱或 RAG 数据源。

## 3. 跨仓契约输入

下一位 agent 在实现 KB-001/KB-002/KB-701 前，需要从 ROTO 主仓生成版本化契约快照，不能让服务运行时读取 Windows 路径：

- `E:/Project/ROTO/docs/PRD-LLM-RAG-Topology-Optimization-Agent.md`
- `E:/Project/ROTO/docs/SDD-LLM-RAG-Topology-Optimization-Agent.md`
- `E:/Project/ROTO/docs/tasks/T02-RAG知识索引与参数校验.md`

必须将 `EvidencePackage v1` 的 JSON Schema、OpenAPI 和 success/empty/degraded/error fixtures 放入本仓 `contracts/`，冻结 `source_uri/source_hash/document_version/security_scope`、`no_match`、`degradation_reasons[]`、citation 和 `index_release_id`。当前主线仍存在 `EvidenceSnippet.source` 与单值 `degradation_reason` 漂移，未冻结前不得宣称联调兼容。

## 4. 服务器上下文

- 公网 IP：`54.172.101.190`，SSH 用户：`ec2-user`。
- SSH 私钥：`E:/Project/ROTO/ladder.pem`，仅用于 SSH 登录；不能当作 HTTPS 证书、RAG Bearer token、Qdrant API key 或 DashScope key，不能提交 Git。
- 生产公网基址：`https://54.172.101.190/roto-kb/`。
- 应用：`roto-kb.service`，仅监听 `127.0.0.1:8710`。
- Qdrant：独立 Docker Server，宿主机仅 `127.0.0.1:6334`，数据 `/data/roto-kb/qdrant/`，collection 前缀 `roto_kb_`，alias `roto_kb_active`。
- 代码、source、index、secret、日志：分别使用 `/home/ec2-user/roto-kb/`、`/data/roto-kb/sources/`、`/data/roto-kb/index/`、`/etc/roto-kb/`、`/var/log/roto-kb/`。
- nginx：`/etc/nginx/sites-available/roto-kb.conf`，启用链接 `/etc/nginx/sites-enabled/roto-kb.conf`，443 终止 TLS 后只代理 `/roto-kb/`。
- 80 端口现由第三方 `kb-server` 根路径使用；不得改写、停用或代理到 ROTO-KB。
- 旧服务：`kb-server.service`、`127.0.0.1:8700`、旧目录和旧索引禁止读取/复制/修改。

2026-09-09 只读预检：旧 health 为 `ok`（498 docs/21684 chunks）；nginx 现有配置仅监听 80；443/8710/6334 未监听；Docker 未运行；根分区可用约 11 GB；AWS CLI 无凭据；`ec2-user` 无免密 sudo。不要在缺少授权、证书和防火墙凭据时写入半成品生产配置。

IP 直连生产必须使用包含 `54.172.101.190` 的 IP SAN 受信任证书。自签名证书只可用于受限 `curl -k` 临时验收，不能长期承载 Bearer token。

## 5. API 与模型约束

- 模型供应商锁定阿里云百炼 Model Studio / DashScope，OpenAI-compatible adapter。
- 默认 Embedding 候选 `text-embedding-v4`；地域、endpoint 和 dimension 必须由用户后续 key + capability probe 确认。
- V1 默认关闭 LLM 摘要/关系抽取；无 API key 时 fake/fixture、空库和离线图谱编译必须可运行。
- read/admin/Qdrant 三套 token 必须不同；真实 secret 只写服务器 `/etc/roto-kb/roto-kb.env`，不写仓库、不写知识目录、不写日志。
- Qdrant 是独立向量数据库服务，不是模型，也不是知识图谱；本地由 Compose、生产由独立 Docker 容器提供。

## 6. 推荐执行顺序

```text
KB-000..004  文档、契约、来源和质量门
 -> KB-101..104  空库、领域模型、配置和 PathPolicy
 -> KB-201..207  扫描、解析、切片和 lint
 -> KB-301..305  DashScope、Qdrant、BM25、关系和 RRF
 -> KB-401..404  API、鉴权、渐进式加载和降级
 -> KB-501..504  build/eval/activate/rollback/self-evolution
 -> KB-601..605  443、systemd、备份、隔离和巡检
 -> KB-701..702  ROTO Fake/Remote client 联调
 -> KB-801..803  后续内容批次运营
```

内容可以后补：新增资料只需 manifest/checksum/license/eval gate、增量 build、评测和人工 activate，不需要重新部署应用。parser、chunk schema、Embedding 维度或检索算法变化必须提升 pipeline version 并全量重建。

