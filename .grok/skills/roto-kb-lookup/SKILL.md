---
name: roto-kb-lookup
description: 检索 ROTO 工程知识库（拓扑优化、FEniTop、Gmsh/meshio/Trimesh/PyVista/CadQuery、JAX-FEM、QUDT/IOF/W3C 本体、ROTO domain seed）。当用户提到"查一下 ROTO 知识库""看看工程文档""fenitop""topology optimization""traction_bcs""vol_frac""filter_radius""mesh""单位换算""QUDT""材料参数""边界条件"、或提问涉及拓扑优化、有限元、网格几何、工程参数校验、单位量纲、工业本体、证据包 EvidencePackage 时使用。即使用户没明说"查知识库"，只要问题落在 ROTO 工程域就应主动检索。
---

# ROTO 工程知识库检索 Skill

## 服务信息

ROTO-KB 提供渐进式加载接口（browse → search → fetch/graph）。公开样例不绑定真实部署地址；请在本地配置 `ROTO_KB_SERVER`（nginx 443 反代至本机 `127.0.0.1:8710`）：

```bash
ROTO_KB_SERVER="https://kb.example.invalid/roto-kb" # 替换为你自己的部署地址
# 或
ROTO_KB_SERVER="http://127.0.0.1:8710"            # 本地开发
```

查询接口需要 Bearer read token；管理接口需要独立 admin token：

```bash
ROTO_KB_READ_TOKEN="<read-token>"     # browse/search/fetch/graph
ROTO_KB_ADMIN_TOKEN="<admin-token>"   # reload/lint/releases
AUTH_READ="Authorization: Bearer $ROTO_KB_READ_TOKEN"
AUTH_ADMIN="Authorization: Bearer $ROTO_KB_ADMIN_TOKEN"
```

会话开始先做健康检查（可匿名）：

```bash
curl -sk "$ROTO_KB_SERVER/health"
```

期望字段：`status=ok`、`content_status`（`empty|ready`）、`active_release_id`、`document_count`、`chunk_count`。非 200 或连接失败时停止后续调用，告知用户检查 `roto-kb.service`。完整机器可读帮助：

```bash
curl -sk "$ROTO_KB_SERVER/help"
```

> 若证书为临时自签名证书，验收时可使用 `curl -sk`；正式 CA 证书就绪后去掉 `-k`。不要把 Bearer token 长期放在明文 HTTP 上。

## 知识库覆盖的领域

检索时可用 filters/`domain` 缩小范围。V1 主要领域：

- `fenitop-examples` — FEniTop README、beam_3d、topopt 示例与参数字段
- `mesh-geometry` — Gmsh、meshio、Trimesh、PyVista、CadQuery 几何与网格格式
- `fem-solvers` — DOLFINx、JAX-FEM、MFEM、NGSolve、MOOSE 等求解器文档
- `topopt-theory` — 拓扑优化/形态美学/形状偏好等相关论文
- `units-ontology` — QUDT 单位与量纲
- `industrial-ontology` — IOF Core 工业本体
- `provenance-vocab` — W3C PROV-O / DCAT 3 / SHACL
- `roto-domain` — ROTO 自有 domain seed（节点、关系、安全规则）

V1 active 图谱只编译 deployment manifest 白名单；CORA/PropNet 为 reference-only，MatOnto 为 link-and-map-only，默认不检索。

## 渐进式加载流程（核心调用模式）

知识内容可能很大，必须按“先浏览、再检索、按需取全”递进。收到用户问题后先做三个判断：

1. **范围判断**：点查（具体参数/API）直接 `search` + `top_k=3`；面查（对比/全景）先 `browse` 或 `graph`。
2. **深度判断**：快速回答只用 snippet；深度讲解再 `fetch` 章节。不要默认拉全文。
3. **置信度判断**：snippet 不足以支撑答案时再 fetch；不要脑补工程默认值。

### 步骤一：浏览（可选）

```bash
curl -sk -H "$AUTH_READ" "$ROTO_KB_SERVER/browse"
```

从返回的 `items[].title/domain/source_uri` 判断相关性，记下 `doc_id`。

### 步骤二：检索（核心）

混合检索（向量语义 + BM25 + RRF）返回 EvidencePackage v1：

```bash
curl -sk -X POST "$ROTO_KB_SERVER/search" \
  -H "Content-Type: application/json" \
  -H "$AUTH_READ" \
  -d '{
    "query": "traction_bcs and vol_frac boundary conditions in FEniTop",
    "top_k": 5,
    "filters": {"domains": ["fenitop-examples"], "security_scopes": ["public"]}
  }'
```

重点字段：`results[].snippets[].content`、`chapter_path`、`source_uri/source_hash/document_version/security_scope`、`index_release_id`、`no_match`、`degraded/degradation_reasons`。

**关键判断**：snippet 够用就停止并回答。只有截断明显或用户要求深讲时才进入步骤三。

### 步骤三：取全（按需）

```bash
curl -sk -H "$AUTH_READ" "$ROTO_KB_SERVER/fetch/<doc_id>"
curl -sk -H "$AUTH_READ" "$ROTO_KB_SERVER/fetch/<doc_id>?chapter=<chapter_path>"
```

### 关联查询

```bash
curl -sk -H "$AUTH_READ" "$ROTO_KB_SERVER/graph/<doc_id>"
```

跨文档对比（“A 和 B 的区别”“单位如何映射到参数”）先看 graph/`related_hint`，再分别 fetch。

## 调用时机决策树

```
用户问题
   │
   ├─ 涉及拓扑优化 / FEM / 网格几何 / 工程参数 / 单位本体 / ROTO 契约？
   │     ├─ 是 → 检索 ROTO-KB（优先 search，必要时 fetch）
   │     └─ 否 → 一般编程问题，不检索
   │
   ├─ 用户明确说“查 ROTO 知识库 / 工程文档 / FEniTop 资料”？
   │     └─ 是 → 检索
   │
   └─ 不确定？
         └─ 先 browse，再决定
```

典型信号词：`traction_bcs`、`vol_frac`、`filter_radius`、FEniTop、Gmsh、meshio、Trimesh、PyVista、CadQuery、JAX-FEM、拓扑优化、网格、边界条件、材料参数、QUDT、IOF、EvidencePackage、`index_release_id`。

不要检索：纯语法问题、与 ROTO 工程无关的问题、旧第三方 `kb-server` 个人笔记问题（那是另一套服务）。

## 绝对不要

- NEVER 一次 fetch 超过 2 篇完整文档；优先 `?chapter=`。
- NEVER 在 snippet 已足够时继续 fetch 全文。
- NEVER 把 RAG 空结果或低置信度片段写成工程默认参数。
- NEVER 因检索命中自动开启热学/电磁/审美求解器，或直接触发 solver。
- NEVER 忽略 `no_match` / `degraded` / `degradation_reasons`；降级结果必须显式告知。
- NEVER 在 health 失败后继续调用业务接口。
- NEVER 对同一问题重复 search 超过 2 次。
- NEVER 读取、复用或修改旧 `kb-server`、`/data/knowledge-base`、`~/.kb-server`。
- NEVER 在回答中泄露 token、内部绝对路径或 traceback。

## 异常处理

| 场景 | 判断条件 | 处理方式 |
|------|---------|---------|
| 服务不可用 | health 非 200 / 连接失败 | 停止调用，告知检查 `roto-kb.service` |
| 鉴权失败 | 401/403 | 检查 read/admin token 是否用错 |
| 检索无结果 | `no_match=true` 或空 results | 去掉 domain 过滤重试一次；仍空则说明知识库未覆盖，用自身知识并标注“非知识库内容” |
| 降级 | `degraded=true` | 说明降级原因，不把结果当完整证据 |
| 文档不存在 | fetch 404 `knowledge.not_found` | 回到 browse/search 重新定位 |
| 证书问题 | TLS 握手失败 | 临时验收可用 `curl -sk`；生产应换正式 IP-SAN 证书 |

## 结果消费指引

引用知识库内容时使用：

> 📖 来源：《文档标题》 > 章节 (`source_uri`, release=`index_release_id`)

主线参数优先级必须遵守：

```text
user_explicit > human_override > rag_verified > template > solver_inferred
```

EvidencePackage 是证据，不是可直接写入求解器的最终参数。

## 运维接口（一般不主动调用）

| 接口 | 用途 | 触发词 |
|------|------|--------|
| `POST /reload` | 增量/全量构建 staging | “重建索引”“知识更新了” |
| `GET /lint` | 质量检查 | “检查知识库质量” |
| `GET /releases` | 列出 release | “有哪些 release” |
| `POST /releases/{id}/activate` | 激活 | “激活这个 release” |
| `POST /releases/{id}/rollback` | 回滚 | “回滚上一版” |

以上全部需要 admin token。Qdrant 默认本机嵌入式模式（`QDRANT_MODE=embedded`），数据在部署机的私有数据目录中，不对公网暴露。

## 常见调用模式速查

**模式一：快速回答**
```bash
curl -sk -X POST "$ROTO_KB_SERVER/search" -H "Content-Type: application/json" -H "$AUTH_READ" \
  -d '{"query":"<用户问题>","top_k":3}'
```

**模式二：领域定向**
```bash
curl -sk -X POST "$ROTO_KB_SERVER/search" -H "Content-Type: application/json" -H "$AUTH_READ" \
  -d '{"query":"<用户问题>","top_k":5,"filters":{"domains":["fenitop-examples"]}}'
```

**模式三：深度讲解**
```bash
# search 定位后
curl -sk -H "$AUTH_READ" "$ROTO_KB_SERVER/fetch/<doc_id>?chapter=<章节>"
```

**模式四：跨文档/本体关联**
```bash
curl -sk -H "$AUTH_READ" "$ROTO_KB_SERVER/graph/<doc_id>"
```

**模式五：空库验收**
```bash
curl -sk "$ROTO_KB_SERVER/health"
# content_status=empty 且 active_release_id=rel_empty 时，search 应返回 no_match=true
```
