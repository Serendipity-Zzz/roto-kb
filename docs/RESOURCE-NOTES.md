# 模型、图谱和知识源的区别

## SciBERT

SciBERT 是在 114 万篇科学论文、约 31 亿 token 上预训练的 BERT 语言模型。交付物主要是模型权重、配置和面向科学文本的词表。它可以做科学文本分类、命名实体识别或关系抽取，但自身不包含可直接查询的结构优化知识图谱。

ROTO-KB 定位：V2 可选 extractor，用于从论文中识别材料、载荷、边界条件和实体关系；不是 V1 知识源，也不是默认 Embedding 模型。

官方来源：https://huggingface.co/allenai/scibert_scivocab_uncased

## MatSciBERT

MatSciBERT 是在材料科学论文上预训练的 BERT 模型，面向材料文本挖掘和信息抽取。它同样提供已训练权重，而不是材料实体关系数据库。只有在配合 NER/关系抽取任务和目标 schema 后，它才能参与构建材料知识图谱。

ROTO-KB 定位：V2 可选 extractor，用于识别材料、工艺、属性和实验条件；不是材料参数真源。材料参数仍需来自有版本、单位、测试条件和许可证的表格、标准或图谱。

官方来源：https://huggingface.co/m3rg-iitd/matscibert

## Hunyuan3D

Hunyuan3D 是从文本、单图或多视图生成三维资产的生成模型/流水线，交付物包括模型权重和推理代码。它既不是语言知识库，也不是知识图谱。

ROTO 定位：属于主线 Geometry 执行服务，用来生成候选表面几何；不进入 ROTO-KB，不负责检索、参数来源或工程事实校验。

官方来源：https://github.com/Tencent-Hunyuan/Hunyuan3D-2

## 真正可作为现成图谱/本体的数据

- QUDT：单位、量纲、数量类型的 RDF/OWL 本体，可用于单位语义和量纲一致性。
- IOF Core Ontology：工业领域核心本体，可用于设备、材料、过程和质量语义约束。
- 材料知识图谱：必须具体选定公开数据集并核对许可、属性单位、测试条件和版本；“MatSciBERT”不能替代它。

这些本体提供已经结构化的类、属性和关系，但仍需映射到 ROTO 的 `ParameterState`、材料 schema 和检索 metadata，不能原样导入后就自动得到可靠工程默认值。
