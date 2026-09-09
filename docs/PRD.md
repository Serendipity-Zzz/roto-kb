# PRD：ROTO 独立 RAG 知识服务子任务

| 项目 | 内容 |
|---|---|
| 产品 | ROTO（Robot-Oriented Topology Optimization Agent） |
| 子系统 | ROTO-KB：结构优化工程知识服务 |
| 文档版本 | PRD v1.4 |
| 日期 | 2026-09-09 |
| 状态 | 独立仓库设计基线，可与主线 Loop Engineering 并行 |
| 上游 | ROTO 总 PRD/SDD、T02 RAG 契约；首次部署前需提供可发布的契约快照 |
| 下游 | `rag_subgraph`、参数抽取、Policy、报告和事件投影 |
| 独立仓库 | 本地 `E:\Project\ROTO-KB`；远端 `https://github.com/Serendipity-Zzz/roto-kb` |

## 1. 背景与问题

ROTO 主线包含 LangGraph/Workflow、参数确认、几何生成、拓扑优化、评估器和报告等多个高耦合环节。知识库索引、向量化、文档更新和检索服务具有独立生命周期，如果与主线同步开发，会使索引重建、远端模型故障或知识内容变更阻塞 loop engineering。

本子任务将 RAG 做成可独立运行、可独立发布、可独立评测和可独立回滚的知识服务。主线只依赖版本化的 `RagService`/`EvidencePackage` 契约，不直接访问 Qdrant、BM25 或原始文件。

## 2. 目标

### 2.1 必须实现

1. 将结构优化所需的工程资料整理为可追溯的原始知识目录。
2. 实现离线解析、切片、Embedding、Qdrant、BM25、RRF 和关系图编译流程。
3. 提供渐进式接口：`browse -> search -> fetch`，并支持 `graph` 关联查询。
4. 提供 source/version/hash/license/security_scope 和 `index_release_id`。
5. 支持 staging 构建、离线评测、原子激活和回滚。
6. 通过远端 HTTP 服务供 ROTO 主线调用，同时保留本地 Fake/Local adapter 便于测试。
7. 知识内容变更与代码发布分离：内容同步后调用 `reload`，代码发布不强制重建索引。
8. 支持 RAG 故障降级；无命中时不得生成无来源的关键工程参数。
9. 首批外部图谱内容必须可离线部署，不依赖付费图谱 API、在线 SPARQL 或第三方运行时账号。

### 2.2 不做

- 本子任务不实现 LangGraph 主循环、参数确认、求解器调度、几何生成或前端工作流。
- 不让 RAG 命中结果直接触发昂贵的 FEniTop/多物理求解。
- 不下载或提交大模型权重、API 密钥、服务器私有配置。
- 允许公网访问查询服务；所有接口使用独立 Token，写接口使用管理 Token。
- V1 不建设复杂知识图谱平台；关系图使用 JSON/SQLite/内存邻接表即可。
- 不复用、复制、索引或修改服务器上现有的第三方知识库内容。
- V1 不接入 Materials Project、NOMAD、Materials Cloud、AFLOW、OQMD 等在线材料数据库 API；DashScope 仅作为已选定的 Embedding/可选 LLM 供应商，不属于图谱数据源。

## 3. 已知远端基线与隔离要求

本次已通过只读检查确认：

- 服务器：`54.172.101.190`，SSH 用户：`ec2-user`。
- `kb-server.service` 已由 systemd 管理，当前运行正常。
- 服务进程监听 `127.0.0.1:8700`，nginx 对外提供 HTTP 80 端口。
- 远端现有服务、代码、配置、原始资料和索引均属于第三方部署，只能作为端口与资源冲突检查对象。
- 禁止读取其知识内容作为 ROTO-KB 数据源；禁止修改 `/data/knowledge-base/` 和 `~/.kb-server/`。

ROTO-KB 采用以下独立资源：

| 资源 | ROTO-KB | 现有第三方服务 | 隔离要求 |
|---|---|---|---|
| 代码目录 | `/home/ec2-user/roto-kb/` | `/home/ec2-user/kb-server/` | 不共享 |
| Python venv | `/home/ec2-user/.roto-kb-venv/` | `/home/ec2-user/.kb-venv/` | 不共享 |
| systemd unit | `roto-kb.service` | `kb-server.service` | 不同服务名 |
| 应用端口 | `127.0.0.1:8710` | `127.0.0.1:8700` | 不同监听端口 |
| 原始知识 | `/data/roto-kb/sources/` | `/data/knowledge-base/` | 不共享、不扫描父目录 |
| 索引数据 | `/data/roto-kb/index/` | `~/.kb-server/data/` | 不共享 |
| Qdrant | `127.0.0.1:6334` | 嵌入式旧索引 | 独立进程和 storage |
| collection | `roto_kb_<release>` | `kb_chunks` | 不同前缀 |
| 日志 | `/var/log/roto-kb/` | `~/kb-server.log` | 不共享 |
| 公网入口 | `443 /roto-kb/` | `/` | nginx 路径隔离；ROTO-KB 不监听公网应用端口 |

部署前必须执行隔离验收：旧服务 `/health` 结果不变；新服务停止、重载、回滚均不得改变旧服务的文档数、切片数、进程、端口、目录或日志。

## 4. 产品边界与总体架构

```text
ROTO 主线 Loop Engineering
  LangGraph / Policy / 参数抽取 / 求解器编排
                    |
                    | RagService.retrieve(query, filters)
                    v
ROTO-KB RemoteRagClient
                    |
                    | HTTP(S)，超时、重试、Token
                    v
独立 kb-server（远端或 Compose 服务）
  ├── browse/search/fetch/graph
  ├── reload、lint、release activate/rollback
  ├── 原始知识文件
  ├── Qdrant collection
  ├── BM25 index
  └── relations / metadata / release manifest
```

### 4.1 三平面

| 平面 | 组件 | 责任 |
|---|---|---|
| 控制平面 | ROTO LangGraph | 决定什么时候检索、是否追问、是否允许使用候选参数 |
| 知识数据平面 | kb-server、Qdrant、BM25、原始文档 | 解析、索引、检索、引用、版本和质量 |
| 执行平面 | worker、FEniTop、GPU/多物理服务 | 执行长任务；不由 RAG 直接触发 |

### 4.2 运行模式

| 模式 | 用途 | 实现 |
|---|---|---|
| Fake | Loop 单元测试 | 固定返回合法 `EvidencePackage` |
| Local | 离线开发和契约测试 | 当前 `backend/app/rag` 的本地实现或本地 kb-server |
| Remote | 集成/生产 | `RemoteRagClient` 调用 `https://54.172.101.190/roto-kb/` |

通过 `ROTO_RAG_MODE` 配置切换，主线代码不感知底层实现。

### 4.3 Qdrant 的角色与选型结论

Qdrant 是向量数据库，不是 Embedding 模型，也不是知识图谱。文档切片先由独立的 Embedding 服务转成定长浮点向量，Qdrant 再保存“向量 + 原文片段 + metadata”，并执行相似度检索和 metadata 过滤。BM25 负责关键词召回，关系索引负责实体关联；三者属于不同索引，在线查询通过 RRF 融合结果。

V1 采用自托管 Qdrant Server，原因是：数据和 release 生命周期可控、支持 collection alias 原子切换、可做 snapshot、对本项目体量足够轻量。它不需要用户在 Windows 手工安装：本地开发由 Docker Compose 拉取固定版本镜像，生产由部署脚本在服务器启动独立容器。

生产形态确定为：

```text
公网请求
  -> nginx :80/443 /roto-kb/
  -> roto-kb.service 127.0.0.1:8710
  -> Qdrant REST 127.0.0.1:6334
  -> Docker container qdrant:6333
       storage: /data/roto-kb/qdrant
```

说明：Qdrant 容器 REST 默认端口是 `6333`；本项目只把它映射为宿主机 `127.0.0.1:6334`，以形成明确的独立命名空间。Qdrant gRPC 端口不对宿主机和公网开放。禁止使用 `0.0.0.0:6334`。

release 对应物理 collection `roto_kb_<release_id>`，线上只通过 alias `roto_kb_active` 查询。激活时先完成 staging collection、BM25、relations 和 manifest 的一致性校验，再切换 alias；保留上一 release 供回滚。Embedding 模型、向量维度或距离度量改变时必须新建 collection，不能向旧 collection 混写不同维度的向量。

### 4.4 阿里云模型 API 选型

模型调用供应商锁定为阿里云百炼 Model Studio（DashScope）。ROTO-KB 通过其 OpenAI-compatible API 调用 Embedding；需要 LLM 辅助摘要或关系抽取时也复用同一供应商，但使用独立的模型配置、超时和调用预算。

- 中国内地默认 endpoint：`https://dashscope.aliyuncs.com/compatible-mode/v1`；若账号和 API key 属于其他地域，部署时使用该地域对应 endpoint，二者不能混用。
- 凭据统一从 `DASHSCOPE_API_KEY` 注入，不在 manifest、日志、GitHub 或 Qdrant payload 中保存。
- V1 推荐候选 Embedding 为 `text-embedding-v4`；最终模型名、可选维度和批量上限必须以用户账号所在地域实际可用能力为准。
- 启动时对配置做一次 capability probe：发送固定短文本，验证模型可用并读取实际向量长度；实际长度与 `EMBEDDING_DIMENSION` 不一致时拒绝构建索引。
- 远端 API 只负责生成向量或辅助结构化提取，不保存 ROTO-KB 的 active release 状态，也不能直接访问 Qdrant。
- 更换 DashScope Embedding 模型或维度必须生成新 `pipeline_version` 和全量 staging release；原 collection 保留到新 release 激活并完成回滚窗口。

## 5. 知识范围与资源策略

### 5.1 V1 优先资源

1. FEniTop 官方 README、`scripts/beam_3d.py`、`fenitop/topopt.py`。
2. FEniTop 论文及官方示例中的边界条件、载荷、体积分数和网格说明。
3. JAX-FEM、MFEM、NGSolve、MOOSE 等官方文档中与结构/多物理求解相关的说明。
4. Gmsh、meshio、Trimesh、PyVista、CadQuery 的官方文档和格式说明。
5. ROTO 自有 PRD/SDD/T02、单位规则、参数 Schema、求解器 adapter 文档。
6. 公开论文：JAX-FEM、TopoDiff、3D 形状审美等，用于背景解释，不直接作为工程参数真值。
7. QUDT 单位/量纲、IOF Core Released 核心文件、W3C PROV-O/DCAT 3/SHACL vocabulary 和 ROTO 自建领域种子图。

### 5.2 资源分层

| 层级 | 内容 | 是否落盘 | 是否可直接作为默认值来源 |
|---|---|---:|---:|
| `official-docs` | 官方 README、API、示例、文档 | 是 | 是，需带版本/URL |
| `papers` | 公开论文 PDF/Markdown | 是 | 否，仅作背景证据 |
| `project-contracts` | ROTO PRD/SDD/Schema/测试 | 是/引用 | 是，需标注项目内部来源 |
| `code-snapshots` | 关键源码文件或浅克隆 | 是，限量 | 仅解释实现，不直接产生参数 |
| `extractor-manifests` | SciBERT/MatSciBERT 等可选信息抽取模型 | 只保存清单 | 否 |
| `weights` | 大模型权重、缓存 | 不下载 | 否 |
| `graph-seeds` | 许可明确的 RDF/OWL/TTL 与 ROTO JSONL 种子 | 是，白名单 | 仅提供语义/映射/校验，不提供材料数值真值 |

### 5.3 许可证与来源

每个 source 必须记录：`source_uri`、`retrieved_at`、`version/revision`、`sha256`、`license`、`attribution`、`status`。第三方资料只保留公开许可允许的文本或链接；不把闭源 API 响应、密钥和私有配置写入知识库。

### 5.4 外部图谱离线种子决策

首批图谱以 [部署清单](../knowledge/graph/deployment-manifest.yaml) 为唯一允许输入，采用静态快照和显式文件白名单：

| 选择 | 许可 | 首批摄取范围 | 用途 |
|---|---|---|---|
| QUDT | CC BY 4.0 | schema、unit、quantitykind、dimension vector 四类文件 | 单位、物理量、量纲和换算语义 |
| IOF Core | MIT | `core/Core.rdf`，且 maturity 为 `Released` | 工业对象、过程和设计产物上位语义 |
| W3C PROV-O | W3C Document License | 原始 `prov-o.ttl` | source/artifact/release provenance |
| W3C DCAT 3 | W3C Document License | 原始 `dcat3.ttl` | Dataset、Distribution、CatalogRecord |
| W3C SHACL | W3C Document License | 原始 `shacl.ttl` vocabulary | 本地图约束的词汇基础 |
| ROTO domain seed v1 | 项目自有 | 41 nodes、18 relations、3 rules | 工程别名、FEniTop 字段映射和安全规则 |

这些内容无需 API key，可随知识 source 同步到服务器后由 `rdflib/JSONL` 离线编译。解析器禁止递归扫描整个本体仓库，也禁止在 build 期间联网解析 `owl:imports`；只读取清单白名单，外部 URI 作为标识保存。

以下候选保留为 `reference-only`，默认不进入 V1 active release：

- Materials Project、NOMAD、Materials Cloud、AFLOW、OQMD：移为未来可选 connector 或人工审核的离线数据批次，不承担启动和查询依赖。
- IEEE 1872 CORA：上游 README 声明 OWL 实现为 CC BY-4.0；保留来源和版权声明，可在后续离线白名单批次启用，但不作为 V1 启动依赖。
- PropNet：上游 LICENSE 允许源码/二进制再分发；保留 LICENSE 和归属，默认只登记模型/术语映射，不执行模型或导入未经核对的依赖数据。
- MatOnto：仓库未发现明确标准许可证；只保留链接、revision 和内部 URI 映射，不复制 OWL。
- Wikidata：不下载全量 dump，也不依赖 SPARQL API；少量别名由 ROTO 自有种子维护。
- AiiDA、Common Core Ontologies、OBO RO：分别因属于软件框架、上位本体重叠或领域噪声而暂缓。

原调研种子中的 `Aluminum6061T6`、`MaterialProject`、`CORA` 及关联已从部署版删除。V1 只定义 `Material`、模量、泊松比、密度等概念，不写入具体牌号数值；材料事实必须来自以后许可明确、带状态/温度/单位/来源的离线表。

## 6. 本地知识目录

独立仓库为 `E:\Project\ROTO-KB`，知识内容位于该仓库的 `knowledge/`：

```text
ROTO-KB/
  README.md
  docs/PRD.md
  knowledge/
    manifest.yaml
    official-docs/
      fenitop/
      gmsh/
      cadquery/
      dolfinx/
    papers/
    project-contracts/
    graph/
      deployment-manifest.yaml
      seeds/roto-domain-seed.v1.jsonl
    ontologies/
      qudt/
      iof-core/
      w3c/
    extractor-manifests/
    checksums.sha256
  src/
  tests/
  infra/
```

本仓库不存在 `raw-remote-kb/`。服务器现有第三方知识库不会被同步、纳入 manifest 或参与索引。

## 7. 核心接口契约

### 7.1 `RagService`

```python
class RagService(Protocol):
    def retrieve(self, query: str, *, filters: dict | None = None,
                 top_k: int = 6) -> EvidencePackage: ...

    def fetch(self, doc_id: str, *, chapter: str | None = None) -> DocumentDetail: ...
```

### 7.2 `EvidencePackage v1`

必须包含：`query`、`index_release_id`、`results`、`degraded`；每个结果包含 `doc_id`、`title`、`domain`、`score`、`match_type`、`snippets`、`related_hint`；每个 snippet 包含 `chunk_id`、`chapter_path`、`content`、`source_uri`、`source_hash`、`document_version`、`security_scope`。

### 7.3 HTTP 接口

| Method | Path | 说明 |
|---|---|---|
| GET | `/health` | 服务、索引、依赖和 release 状态 |
| GET | `/browse` | 文档元数据和 domain 统计 |
| POST | `/search` | 向量 + BM25 + RRF，返回 evidence package |
| GET | `/fetch/{doc_id}?chapter=...` | 取全文或指定章节 |
| GET | `/graph/{doc_id}` | 出边、入边和关系类型 |
| POST | `/reload` | 构建增量 staging index |
| GET | `/lint` | 质量检查 |
| POST | `/releases/{id}/activate` | 评测通过后原子激活 |
| POST | `/releases/{id}/rollback` | 回滚上一 release |

公网接口基址为 `https://54.172.101.190/roto-kb/`；在 IP-SAN 证书就绪前，只允许受限临时验收，不把 Bearer Token 长期放在 IP + HTTP 上。查询接口使用 `Authorization: Bearer <ROTO_KB_READ_TOKEN>`；reload/release 等写接口使用权限独立的 `ROTO_KB_ADMIN_TOKEN`。

### 7.4 鉴权与错误契约

- `/health` 只返回服务状态、版本和聚合计数，不返回路径、密钥、异常栈或文档内容；可匿名访问供探活。
- `/browse`、`/search`、`/fetch`、`/graph` 必须使用 read token；`/reload`、`/lint` 写模式和 release 操作必须使用 admin token。
- read/admin token 至少 32 字节随机值，分别生成、分别轮换；比较使用常量时间算法。
- Qdrant 使用独立 `QDRANT_API_KEY`，只提供给 `roto-kb.service`，不得复用 HTTP read/admin token。
- 统一错误结构为 `{error: {code, message, request_id}}`；公网响应不得包含内部文件路径和 traceback。
- `401` 表示凭据缺失/无效，`403` 表示权限不足，`409` 表示 release 状态冲突，`503` 表示依赖降级且当前请求无法完成。

## 8. 索引与发布生命周期

```text
同步原始资料
  -> source hash/version
  -> 解析与切片
  -> Embedding/Qdrant + BM25 + relations
  -> lint + 检索评测
  -> 生成 index_release_id
  -> 原子 activate
  -> 在线查询只读 active release
```

要求：

- 原始资料不可变，索引为可重建产物。
- 同一 `source_uri + sha256` 不重复向量化。
- 删除采用 `disabled -> offline delete` 两阶段，保留审计。
- 激活失败继续使用上一 release。
- 记录 Embedding 模型、维度、切片参数、pipeline 版本和 source version 集合。
- `/reload` 不直接清空线上索引；先构建 staging，再评测和切换。

### 8.1 先建服务、后补内容

ROTO-KB 必须支持内容与引擎分期交付。服务部署不以“知识资料全部收集完成”为前置条件。

初始状态：

- 没有知识内容时仍可启动，`/health` 返回 `status=ok`、`content_status=empty`、`active_release_id=rel_empty`。
- `browse` 返回空列表；`search` 返回合法的空 `EvidencePackage`，标记 `no_match=true`，不得返回 500 或伪造答案。
- `fetch` 对不存在的文档返回稳定的 `404 knowledge.not_found`。
- `rel_empty` 只表示服务契约可用，不允许作为工程参数来源。

建议先导入 5-20 个种子资料完成首个可用 release：FEniTop 示例、单位本体核心文件、参数 Schema、材料字段定义和 10-20 条验收查询。后续资料按批次进入：

```text
新增/更新文件
  -> source catalog 登记和 SHA-256
  -> 仅编译变化文档
  -> staging release
  -> 对固定评测集执行回归
  -> 通过后 activate
  -> 旧 release 保留用于回滚
```

每次补充知识内容不要求重新部署应用，也不修改 Loop Engineering。只有解析器、切片算法、Embedding 模型/维度或 metadata schema 发生不兼容变化时，才触发带新 `pipeline_version` 的受控全量重建。

内容批次建议：

| 批次 | 内容 | 目的 |
|---|---|---|
| Seed | FEniTop 核心示例、QUDT 核心单位、ROTO 参数 Schema | 跑通完整链路 |
| V1-A | 材料参数、载荷、边界条件、网格规则 | 支撑参数抽取 |
| V1-B | Gmsh/meshio/Trimesh/PyVista 工程文档 | 支撑几何与格式解释 |
| V1-C | JAX-FEM、多物理和优化论文 | 支撑方案解释与关联检索 |
| Continuous | 新案例、项目结论、经过审核的实验记录 | 持续提升覆盖率 |

知识内容进入 active release 前必须具备来源、许可、版本和 hash。资料可以后补，但 metadata 质量门不能后补。

## 9. RAG 与 Loop 的联调规则

### 9.1 主线允许做的事

- 发送自然语言 query 和结构化 filters。
- 读取 evidence、source、confidence、release。
- 根据证据生成候选参数或追问。
- 将 `index_release_id` 和 citation 写入事件/报告。

### 9.2 主线禁止做的事

- 直接读 Qdrant/BM25 文件。
- 根据单个低置信度片段自动覆盖用户显式参数。
- 因 RAG 命中自动开启热学、电磁或审美求解器。
- 把 RAG 空结果当作默认参数。

### 9.3 参数来源优先级

```text
user_explicit > human_override > rag_verified > template > solver_inferred
```

`rag_verified` 必须有来源和足够置信度；`inferred` 或低置信度结果进入人工确认。

### 9.4 降级

Embedding 不可用时使用已有向量 + BM25；Qdrant 不可用时使用 BM25 + graph；BM25 损坏时使用 Qdrant；RAG 完全不可用时进入普通参数抽取和自然语言追问。每次降级都产生结构化 `rag.fallback` 事件。

## 10. 安全与运维

- `ladder.pem` 仅用于本地 SSH 操作，必须加入 `.gitignore` 并从 Git 历史排除；如曾提交过则立即轮换密钥。
- 远端 API Key 只保存在服务器 secret/config，不复制到本地知识目录、PRD、日志或镜像。
- 公网入口由 nginx 在 TCP 443 提供 `/roto-kb/` 路径；80 保留旧服务根路径，不代理 ROTO-KB；8710、6334 仅监听 loopback，不直接暴露公网。TLS 最低启用 TLS 1.2，证书替换/续期失败必须告警。
- 原始知识目录、Qdrant、BM25、release manifest 必须分别备份；恢复后先校验 SHA-256，再激活 release。
- 监控 `/health`、检索 p95、fallback rate、索引构建失败数和磁盘使用率。
- 远端当前磁盘约 16 GB、可用约 11 GB；V1 只部署文档和索引，不部署 SciBERT、MatSciBERT 或 Hunyuan3D 权重。

### 10.1 部署拓扑与配置基线

本地开发使用 Docker Compose 启动 Qdrant，应用可在宿主机 Python 环境运行；生产使用 systemd 管理应用、Docker 管理 Qdrant。镜像必须在实现阶段固定版本和 digest，禁止生产使用浮动 `latest`。

| 变量 | 本地默认 | 生产值/来源 | 是否秘密 | 说明 |
|---|---|---|---:|---|
| `ROTO_KB_HOST` | `127.0.0.1` | `127.0.0.1` | 否 | 应用禁止直接公网监听 |
| `ROTO_KB_PORT` | `8710` | `8710` | 否 | nginx 上游端口 |
| `ROTO_KB_PUBLIC_BASE_URL` | `http://localhost:8710` | `https://54.172.101.190/roto-kb` | 否 | 生产公网基址；证书必须包含 IP SAN |
| `ROTO_KB_SOURCE_PATH` | `./knowledge` | `/data/roto-kb/sources` | 否 | 只扫描该目录 |
| `ROTO_KB_INDEX_PATH` | `./data/index` | `/data/roto-kb/index` | 否 | BM25、relations、release manifest |
| `QDRANT_URL` | `http://127.0.0.1:6334` | `http://127.0.0.1:6334` | 否 | 宿主机映射端口 |
| `QDRANT_STORAGE_PATH` | Docker volume | `/data/roto-kb/qdrant` | 否 | Qdrant 持久化目录 |
| `QDRANT_COLLECTION_PREFIX` | `roto_kb` | `roto_kb` | 否 | collection 命名隔离 |
| `QDRANT_ACTIVE_ALIAS` | `roto_kb_active` | `roto_kb_active` | 否 | 在线查询入口 |
| `QDRANT_API_KEY` | 本地 `.env` | server env file | 是 | Qdrant 自身鉴权 |
| `MODEL_PROVIDER` | `dashscope` | `dashscope` | 否 | 锁定阿里云百炼 Model Studio |
| `DASHSCOPE_BASE_URL` | 中国内地 compatible endpoint | 按 API key 地域配置 | 否 | OpenAI-compatible API 基址 |
| `DASHSCOPE_API_KEY` | 本地 `.env` | server env file | 是 | Embedding/可选 LLM 共用供应商凭据 |
| `EMBEDDING_MODEL` | `text-embedding-v4`（建议值） | server env file | 否 | release manifest 必填 |
| `EMBEDDING_DIMENSION` | 待地域/模型确认 | 与 capability probe 一致 | 否 | collection 创建时固定 |
| `EMBEDDING_BATCH_SIZE` | `16` | 经压测调整 | 否 | 不超过模型接口限制 |
| `DASHSCOPE_LLM_MODEL` | 空，V1 可关闭 | server env file | 否 | 摘要/关系抽取的可选模型 |
| `ROTO_KB_READ_TOKEN` | 本地 `.env` | server env file | 是 | 只读 API token |
| `ROTO_KB_ADMIN_TOKEN` | 本地 `.env` | server env file | 是 | 索引管理 token |
| `ROTO_KB_RELEASE_RETENTION` | `2` | `2` | 否 | 至少保留当前和上一 release |
| `ROTO_KB_LOG_LEVEL` | `INFO` | `INFO` | 否 | 日志不得记录 token/全文 |

生产 secret 文件建议使用 `/etc/roto-kb/roto-kb.env`，owner 为 `root`、权限 `0600`，systemd 通过 `EnvironmentFile=` 读取。仓库只提供 `.env.example`，不提供真实值。

### 10.2 容量与性能预算

当前原始资料约 36 MB，V1 按不超过 50,000 chunks 规划。以 1,024 维、float32 为容量示例，纯向量约 195 MB；计入 HNSW、payload、WAL、双 release 和 snapshot 后，预留 2-4 GB Qdrant 空间，另预留 1-2 GB 给原始资料、BM25、构建临时文件和日志。实际预算必须根据最终 DashScope 模型返回维度重算。

- 首次构建前服务器剩余磁盘必须不少于 5 GB；低于阈值时 `/reload` 拒绝全量构建。
- 默认只并存 active 和 previous 两个 release；staging 失败后清理其临时 collection。
- 初期单实例即可，不引入 Qdrant 集群；目标是 1-10 QPS、`search` p95 小于 1.5 秒（不含上游 LLM 生成）。
- Embedding 采用批处理、hash 去重和可恢复 checkpoint，避免重复调用外部 API。
- 实际向量维度由最终 DashScope Embedding 模型决定，上述容量仅为 1,024 维示例。

### 10.3 备份与恢复

备份单元包含：`knowledge/manifest.yaml` 及原始 source、active/previous release manifest、BM25/relations 产物、对应 Qdrant collection snapshot。代码由 GitHub 恢复，不把虚拟环境和容器镜像层当作备份。

- 每次 release 激活后创建 Qdrant snapshot，并记录 snapshot hash、collection、Embedding 模型/维度和 source manifest hash。
- 每日增量备份 source/manifest；每周验证一次 active release snapshot 可读性。V1 保留最近 7 个每日备份和 4 个每周备份。
- 恢复顺序：恢复 source 和 manifest -> 校验 SHA-256 -> 恢复 Qdrant snapshot -> 恢复同 release 的 BM25/relations -> 校验计数和评测集 -> 设置 active alias -> 开放流量。
- 未通过 hash、维度、chunk count 和固定检索评测的恢复结果不得激活。

### 10.4 可观测性与运行手册

每个请求生成 `request_id`；记录 release、耗时、召回数量、降级原因和状态码，不记录 token、完整 query 或全文片段。告警覆盖：服务不可用、Qdrant 不可达、Embedding 失败率、p95 超标、磁盘低于 20%、reload 失败和 active release 异常。运维脚本必须先校验目标路径属于 `/data/roto-kb/`，并显式拒绝第三方知识库路径。

## 11. 验收标准

### 11.1 RAG 独立验收

- 本地可启动 kb-server 并通过 `/health`。
- 空库可启动；`rel_empty`、空 browse、空 EvidencePackage 和稳定 404 契约通过。
- `browse/search/fetch/graph` 契约测试通过。
- 导入最小种子资料后无需重启应用即可生成并激活首个 release。
- 新增、修改、停用文档后，`reload` 只处理变化 source。
- staging release 评测失败时 active release 不变。
- 向量、BM25、Qdrant、Embedding 故障注入能产生结构化降级。
- 每条返回证据可追溯到 source/version/hash/release。
- 结构优化术语（`traction_bcs`、`vol_frac`、`filter_radius`、`mesh`、材料和单位）有精确检索测试。

### 11.2 Loop 契约验收

- FakeRagService 可驱动主线参数抽取和追问测试。
- RemoteRagClient 可将远端响应映射为 `EvidencePackage v1`。
- RAG 超时/空结果不会阻塞 loop，也不会编造关键参数。
- citation、`index_release_id` 和 fallback 事件能进入主线事件日志。
- RAG 命中不会绕过 Policy 直接启动求解器。

### 11.3 质量指标

至少记录：`hit@k`、`mrr`、`keyword_hit_rate`、`evidence_coverage`、`citation_accuracy`、`latency_p95`、`fallback_rate`。

## 12. 里程碑与交付物

工程设计和任务拆解文档：

- [SDD：ROTO-KB 独立工程知识服务](./SDD.md)：组件、数据模型、API、状态机、故障和测试设计。
- [ROTO-KB SDD 驱动开发子任务](./DEVELOPMENT-TASKS.md)：阶段门、任务依赖、输出、验收、回滚和持续内容运营清单。
- [外部图谱离线种子选型](./GRAPH-SEED-SELECTION.md)：最终纳入/排除列表、许可和更新约束。

| 阶段 | 交付 | 依赖 |
|---|---|---|
| R0 | 本 PRD、SDD、开发子任务、目录、manifest、资源许可清单 | 当前文档 |
| R1 | `RagService`/EvidencePackage Schema、Fake adapter、契约测试 | R0 |
| R2 | 原始资料导入、解析切片、Local index、browse/search/fetch/graph | R1 |
| R3 | Remote kb-server 适配、超时/鉴权/降级、release API | R2 |
| R4 | 远端服务器同步脚本、staging reload、评测和回滚 | R3 |
| R5 | 与 Loop 的 `rag_subgraph` 联调和事件投影 | R1、R3 |
| R6 | 生产安全加固、备份恢复、监控和上线验收 | R4、R5 |

R1/R2 与主线 Loop 可并行；R5 才需要真实联调。

### 12.1 GitHub 与交付流程

代码仓库为 `https://github.com/Serendipity-Zzz/roto-kb`，默认分支 `main`。内容文件和索引发布分离：代码 PR 负责应用、schema、infra 和测试；知识变更 PR 负责 source/manifest/checksum/eval case，生成的 Qdrant/BM25 索引不提交 Git。

推荐 CI：

```text
pull request
  -> format/lint/unit tests
  -> manifest/schema/license/checksum validation
  -> empty-library contract tests
  -> small fixture retrieval evaluation
  -> merge main
  -> build immutable artifact/image
  -> manual production deployment approval
  -> deploy app without touching active index
```

知识 release 另走管理流程：同步资料 -> 远端 staging build -> eval -> 人工/策略批准 -> activate。GitHub Actions 只能通过 Secrets 取得部署凭据，且默认不能直接执行 destructive cleanup。V1 上线前至少保护 `main`、要求 CI 通过，并禁止提交 `.env`、`*.pem`、模型权重和生成索引。

## 13. 需要用户确认/执行的事项

仓库已提供，模型供应商已确定为阿里云。当前有一项必须先完成的契约前置，以及若干不阻塞空库开发、但会阻塞首次真实索引或公网部署的决策：

### 13.1 现在必须完成（阻塞跨仓实现）

1. **固化跨仓契约**：ROTO 主线当前 `EvidenceSnippet` 仍使用 `source`，`EvidencePackage` 仍使用单个 `degradation_reason`；本仓 SDD 要求 `source_uri/source_hash/document_version/security_scope`、`no_match` 和 `degradation_reasons[]`。在 KB-002/KB-601 开始前，必须由两仓共同确定 v1 字段，提交 `contracts/` 下的 JSON Schema、OpenAPI 和 success/empty/degraded/error fixtures，并让两仓 CI 离线通过。不能让服务器依赖 `E:/Project/ROTO/...` Windows 绝对路径。
2. **决定项目契约交付方式**：推荐从 ROTO 主仓发布带 commit/SHA-256 的 `project-contracts` 快照；如果暂不复制全文，至少发布可解析的 Schema/OpenAPI/fixture。当前外部路径仅适合本机开发，不能作为远端 release 的 source。
3. **保护 GitHub 主分支**：`roto-kb` 当前为 public 且 `main` 未启用 branch protection；需启用 PR、CI 必过和 secret scanning，并确认 `.pem/.env/生成索引/模型权重` 不入库。

4. 在首次索引前确认阿里云账号地域、最终 Embedding 模型和维度；默认建议中国内地 endpoint + `text-embedding-v4`，维度由 capability probe 校验。不要在聊天中粘贴 API key。
5. 确认是否由本任务自动生成 `ROTO_KB_READ_TOKEN`、`ROTO_KB_ADMIN_TOKEN` 和 `QDRANT_API_KEY` 并直接写入服务器 `/etc/roto-kb/roto-kb.env`；明文不会写入仓库或回复。
6. 确认当前阶段是只完成文档/契约和 G1-G4 本地实现，还是继续实现并部署 G5-G6。服务器变更前需完成 Docker/nginx/磁盘/端口只读预检；本地 `ladder.pem` 当前 ACL 过宽，OpenSSH 会拒绝使用，需要你在部署时收紧密钥权限或提供合规的 SSH 凭据。
7. 使用公网 IP 直接访问时，提供包含 `54.172.101.190` IP SAN 的受信任 TLS 证书及私钥，或明确仅做临时自签名验收。没有受信任 IP 证书前，不启用长期公网 Bearer Token 服务。`ladder.pem` 仅用于 SSH，不可作为 HTTPS 证书。

### 13.3 可以后补（不阻塞空库和契约开发）

- CORA、PropNet、MatOnto 的实际文件导入；先保持 reference-only/link-and-map-only。
- 材料牌号和实验属性数据；必须另有带条件、单位、来源和许可的离线批次。
- SciBERT、MatSciBERT 权重和任何 Hunyuan3D 组件；不属于 V1 RAG 部署。

## 14. 风险与决策记录

| 风险 | 影响 | 缓解 |
|---|---|---|
| 远端服务公网无认证 | 知识泄露/索引破坏 | HTTPS、Token、白名单；写接口单独保护 |
| Embedding API 不稳定或数据外发 | 索引失败/隐私风险 | 可配置 adapter、缓存、重试、敏感资料分级 |
| 新旧知识库资源串用 | 泄露、污染检索或误删 | 独立目录、服务、端口、Qdrant、Token和隔离回归测试 |
| RAG 误命中修改工程参数 | 工程风险 | 来源优先级、Schema、Policy、人工确认 |
| 索引重建中断线上查询 | 服务空窗 | staging + 原子 activate + rollback |
| 知识库过大占满服务器 | 部署失败 | 当前服务器容量门槛、磁盘监控、禁止下载模型权重 |
| Embedding 模型或维度被替换 | collection 不兼容、检索漂移 | 新建 release collection、全量重建、固定评测后切 alias |
| Qdrant 端口直接暴露公网 | 索引被读取或篡改 | 仅绑定 `127.0.0.1:6334`、独立 API key、防火墙复核 |
| DashScope 地域与 API key 不匹配 | 调用失败、首次构建阻塞 | endpoint 显式配置、启动 capability probe、禁止自动回退其他供应商 |
| 外部本体递归 import 膨胀或漂移 | 构建联网、重复类、版本不可复现 | 白名单文件、禁网络 import、namespace/版本/hash gate |
| 计算材料数据被误作工程许用值 | 错误材料参数进入求解器 | V1 不接材料 API；具体数值需离线来源、条件、单位和人工确认 |

## 15. 参考资料

资源 URL 以 `knowledge/manifest.yaml` 为准。RAG 知识源包括 FEniTop、JAX-FEM、Gmsh、meshio、Trimesh、PyVista、CadQuery、QUDT 和 IOF Core 等公开资料。Hunyuan3D 属于 ROTO 主线 Geometry 服务，不作为 ROTO-KB 模型或图谱资源。
