# 目录与模块层级说明（重构后）

本文档描述重构后的目录结构、各层职责与单元测试约定，便于维护与扩展。

---

## 一、目标目录结构

```
category_matching/
├── main.py                 # 入口：日志、配置、循环接受文件路径并批量匹配
├── paths.py                # 根路径：基准/模型/Excel/输出/日志 + 输入路径规范化
├── app/                    # 应用层：仅流程控制与文件 I/O
│   ├── __init__.py
│   ├── batch_match.py      # 批量匹配编排（规则→相似度→LLM 回退）
│   └── io.py               # 品类文件读取、结果 Excel 写入
├── core/                   # 核心领域
│   ├── __init__.py
│   ├── models.py           # 数据模型：CategoryRule, RuleSheetMeta, VerifiedBrand
│   ├── loaders.py          # 数据读取：规则与已校验品牌 Excel
│   ├── matching.py         # 规则匹配 + 向量/相似度匹配
│   ├── embedding.py        # 向量模型加载与编码、相似度（依赖 utils.similarity）
│   ├── config.py           # 向后兼容：从 core.conf 统一 re-export
│   ├── conf/               # 配置子模块（路径、LLM、MCP 配置与加载）
│   │   ├── __init__.py
│   │   ├── paths.py
│   │   ├── llm.py
│   │   ├── mcp.py
│   │   └── __main__.py
│   └── utils/              # 核心工具：Excel 读写、相似度计算
│       ├── __init__.py
│       ├── excel_io.py     # cell_value, open_excel_read, write_sheet
│       └── similarity.py    # jaro_winkler_similarity, weighted_combined, DEFAULT_BGE_WEIGHT
├── llm/                    # LLM 独立封装（顶层，便于单测与复用）
│   ├── __init__.py
│   ├── client.py           # 大模型调用（带 MCP 工具）
│   ├── prompt.py           # 提示词与参考关键词
│   └── llm_config.py      # 从 core.conf re-export + 加密 CLI（uv run -m llm.llm_config）
├── mcp_client/             # MCP 客户端
│   ├── __init__.py
│   ├── config.py
│   └── manager.py
├── config/                 # 静态配置目录（JSON 等）
│   └── mcp_client_config.json
└── tests/                  # 单元测试
    ├── __init__.py
    ├── conftest.py
    └── unit/
        ├── __init__.py
        ├── test_models.py
        ├── test_matching.py
        └── test_similarity.py
```

---

## 二、各层职责与边界

| 层级 | 职责 | 依赖方向 |
|------|------|----------|
| **main** | 启动日志、加载配置、加载规则与品牌、循环接受文件路径并调用 app.run_batch_match、写结果 | paths, app, core, core.conf |
| **app** | 流程控制（单条匹配编排、批量并发）、文件 I/O（读品类、写 Excel） | core（models、matching）、llm、app.io |
| **core** | 领域模型、规则/相似度匹配、数据加载、向量嵌入、配置 | core 内部（utils、conf）；无依赖 app/llm |
| **core.utils** | 与业务无关的工具：Excel 读写、相似度公式（Jaro-Winkler、加权组合） | 仅标准库与 rapidfuzz/openpyxl |
| **llm** | 大模型调用与 MCP 工具编排、提示词、配置入口 | core.conf, mcp_client |
| **mcp_client** | MCP 连接与 list_tools/call_tool | core.conf（配置结构） |

- **核心逻辑（core）**：按职责拆分为 models、loaders、matching、embedding、utils；配置集中在 conf。
- **应用层（app）**：只做流程与 I/O，不实现规则/相似度/LLM 算法。
- **LLM**：独立包，便于单测（mock core.conf / mcp_client）和后续替换实现。

---

## 三、单元测试约定

- **tests/conftest.py**：保证项目根在 `sys.path`，便于直接 `import core`、`import llm`。
- **tests/unit/**：按模块分文件，例如 `test_models.py`、`test_matching.py`、`test_similarity.py`。
- **可测范围**：
  - **core.models**：纯数据，无依赖。
  - **core.utils.similarity**：纯函数，无模型，适合快速单测。
  - **core.matching**：`match_rule`、`match_store` 不依赖 embedding 模型，可单测。
  - **core.embedding**：依赖 BGE 模型，单测可 mock 或标记为集成测试。
  - **llm**：可 mock `core.conf`、`mcp_client` 做单测。

运行测试：

```bash
uv run pytest tests/ -v
# 仅单元（不拉模型）
uv run pytest tests/unit/test_models.py tests/unit/test_similarity.py tests/unit/test_matching.py -v
```

---

## 四、与重构目标的对应关系

| 目标 | 实现方式 |
|------|----------|
| 核心逻辑按职责拆分 | core：matching（规则+相似度）、loaders（Excel）、models（数据）、utils（相似度、Excel 工具） |
| 应用层只负责流程与 I/O | app：batch_match（编排）、io（读品类、写 Excel） |
| LLM 独立封装 | 顶层 **llm/**，依赖 core.conf 与 mcp_client，便于单测与替换 |
| 所有模块支持单元测试 | tests/ 结构 + conftest；core.utils.similarity、core.matching 规则部分无模型即可测 |
| 重复工具统一到 utils | core.utils.excel_io（Excel）、core.utils.similarity（Jaro-Winkler、加权组合） |

---

## 五、入口与常用命令

- **主程序**：`uv run python main.py` 或 `python main.py`
- **加密 API Key**：`uv run -m llm.llm_config <明文key>`（原 `core.llm.llm_config` 已迁移至 `llm.llm_config`）
- **配置加密（core.conf）**：`uv run -m core.conf encrypt <明文key>`
