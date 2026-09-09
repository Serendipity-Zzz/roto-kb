# 知识内容

该目录只包含 ROTO-KB 自身的公开工程资料、项目契约引用和本体快照，不包含服务器上现有第三方知识库的任何文件。

- `official-docs/`：FEniTop、Gmsh、DOLFINx、CadQuery、JAX-FEM 等官方资料。
- `papers/`：可公开获取的论文 PDF。
- `ontologies/qudt/`：QUDT 单位与量纲本体，CC BY 4.0。
- `ontologies/iof-core/`：IOF 工业本体，MIT。
- `ontologies/w3c/`：PROV-O、DCAT 3、SHACL 的 W3C 原始 TTL 快照和许可说明。
- `graph/deployment-manifest.yaml`：V1 图谱编译白名单，禁止递归扫描本体目录或联网解析 import。
- `graph/seeds/roto-domain-seed.v1.jsonl`：去除 API/许可不明确来源后的 ROTO 领域节点、关系和规则。
- `project-contracts/`：指向 ROTO 主仓库契约文件的清单。
- `manifest.yaml`：来源、版本、许可、部署隔离和下载状态。
- `checksums.sha256`：本目录静态资源的完整性校验。

SciBERT 和 MatSciBERT 只登记为 V2 可选信息抽取模型。Hunyuan3D 不属于本仓库。
