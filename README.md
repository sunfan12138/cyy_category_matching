# 品类匹配工具

从 Excel 读取匹配规则与已校验品牌数据，对输入的品类文本进行规则匹配或 BGE 相似度匹配，结果输出到 Excel。当相似度匹配结果 &lt; 0.9 时，可调用大模型生成品类描述并再次做关键词规则匹配（需配置 API）。

## 项目结构

```
category_matching/
├── main.py              # 入口：加载规则 → 循环输入文件 → 批量匹配 → 输出 Excel
├── paths.py             # 路径与输入规范化（基准目录、model/excel/output、normalize_input_path）
├── core/                # 匹配核心
│   ├── models.py        # 数据模型（CategoryRule, VerifiedBrand）
│   ├── loaders.py       # Excel 加载（load_rules, load_verified_brands）
│   ├── matching.py     # 规则匹配 + 相似度回退（match_store, match_by_similarity）
│   ├── embedding.py    # BGE 向量与 Jaro-Winkler 组合相似度
│   └── llm/            # 大模型品类描述（相似度 &lt; 0.9 时调用，带 MCP 工具）
│       ├── prompt.py   # 提示词与参考关键词
│       └── client.py    # 大模型客户端（支持 MCP 工具），日志记录每轮对话与工具
├── app/                 # 应用层
│   ├── batch.py        # 批量匹配流程（run_batch_match）
│   └── io.py           # 文件读写（read_categories_from_file, write_result_excel）
├── mcp_client/         # MCP 客户端（可选，通过配置连接外部 MCP 工具）
│   ├── config.py       # 配置加载
│   └── manager.py      # 连接与 list_tools / call_tool
├── config/             # 配置文件目录（未打包=项目根/config，打包后=当前工作目录/config）
│   ├── llm_config.json       # 大模型配置（可选，含 api_key/base_url/model）
│   └── mcp_client_config.json # MCP 服务器配置
├── build-onefile.spec   # Windows 打包（OneFile）
├── build.spec           # macOS 打包（onedir）
└── excel/ model/ output/  # 数据与输出目录
```

## 开发运行

- 依赖：`uv sync`（含 dev 时 `uv sync --group dev`）
- 运行：`uv run main.py`

## 打包

**Windows（仅 OneFile）**
- 本地：`build.bat`（生成单文件 `dist\CategoryMatching.exe`）
- 发布 zip 内含：CategoryMatching.exe、使用说明.txt、运行诊断.bat

**macOS**
- 在项目根目录执行：`./build.sh`（需先 `chmod +x build.sh`）
- 生成 `dist/CategoryMatching/`，内含可执行文件 `CategoryMatching`（无后缀）及依赖
- 分发时打包整个目录；运行时在可执行文件同目录下放置 `excel`、`model`、`output`，终端执行 `./CategoryMatching`

## MCP 客户端（通过配置集成外部 MCP 工具）

通过配置文件连接外部 MCP 服务器并调用其工具。

1. **配置文件**：在 `config` 目录下放置 `mcp_client_config.json`（未打包=项目根/config，打包后=当前工作目录/config），或设置环境变量 `CATEGORY_MATCHING_MCP_CONFIG` / `CATEGORY_MATCHING_CONFIG_DIR`。
2. **格式**：JSON，包含 `servers` 数组；每项为 `name`、`transport`（`stdio` 或 `streamable-http`），以及：
   - **stdio**：`command`、`args`（可选 `env`、`cwd`）
   - **streamable-http**：`url`
3. **用法**（异步）：
   ```python
   from paths import get_mcp_config_path
   from mcp_client import load_config, MCPClientManager

   config = load_config(get_mcp_config_path())
   if config:
       async with MCPClientManager(config) as manager:
           tools = await manager.list_tools()  # [(server_name, tool), ...]
           result = await manager.call_tool("example_stdio", "tool_name", {"arg": "value"})
   ```
4. **同步调用**：`from mcp_client import run_async`，用 `run_async(coro)` 包装单次异步调用。

示例配置见仓库内 `config/mcp_client_config.json`。

## 大模型二次规则匹配（相似度 &lt; 0.9）

当相似度检索结果 &lt; 0.9 时，可调用大模型根据品类文本生成一句简短描述，再对该描述做一次关键词规则匹配；若规则命中则按规则结果输出。未配置 API Key 时该步骤自动跳过。

**key/url/model 可配置**，key 支持加密存储，**不可直接展示**（日志/界面仅脱敏显示）。

- **key 优先级**：默认取环境变量 `OPENAI_API_KEY`（明文，不需解密）；若 `llm_config.json` 里配置了 key，则用配置的（`api_key` 明文 或 `api_key_encrypted` 需解密）。
- **配置文件**：`config/llm_config.json`（未打包=项目根/config，打包后=当前工作目录/config；或环境变量 `CATEGORY_MATCHING_LLM_CONFIG` / `CATEGORY_MATCHING_CONFIG_DIR` 指定路径），格式示例：
  ```json
  { "api_key": "可选明文", "api_key_encrypted": "可选加密字符串", "base_url": "https://api.openai.com/v1", "model": "gpt-3.5-turbo" }
  ```
  - `api_key`：明文 API Key（配置后覆盖环境变量，不需解密）
  - `api_key_encrypted`：加密后的 API Key（解密口令写死在代码中）
  - `base_url`、`model`：OpenAI 兼容 base URL 与模型名
- **加密 key**：运行 `uv run -m core.llm.llm_config <明文key>`，将输出的字符串填入 `api_key_encrypted`（解密口令已写死在代码中）。
- **环境变量**：
  - `OPENAI_API_KEY`：默认 API Key（明文，不需解密；被配置文件中的 key 覆盖时不用）
  - base_url、model 仅从配置文件 `llm_config.json` 取，未配置则用默认值

## 使用与排错

解压发布包后，在 exe 所在目录或当前工作目录下准备 `excel`、`model`、`output`、`config`（内含 `llm_config.json`、`mcp_client_config.json`），或通过环境变量指定路径后运行。  
若出现 **“Failed to load Python DLL”** 或 **LoadLibrary** 报错，请查看同目录下的 **使用说明.txt**，按其中步骤操作（纯英文路径、VC++ 运行库、运行诊断.bat、OneFile 版等）。
