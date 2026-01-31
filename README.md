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
│   └── llm.py          # 大模型品类描述（相似度 &lt; 0.9 时二次规则匹配）
├── app/                 # 应用层
│   ├── batch.py        # 批量匹配流程（run_batch_match）
│   └── io.py           # 文件读写（read_categories_from_file, write_result_excel）
├── mcp_client/         # MCP 客户端（可选，通过配置连接外部 MCP 工具）
│   ├── config.py       # 配置加载
│   └── manager.py      # 连接与 list_tools / call_tool
├── mcp_client_config.json
├── build-onefile.spec   # Windows 打包（OneFile）
├── build.spec           # macOS 打包（onedir）
└── excel/ model/ output/  # 数据与输出目录
```

## 开发运行

- 依赖：`uv sync`（含 dev 时 `uv sync --group dev`）
- 运行：`uv run python main.py`

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

1. **配置文件**：在项目根目录放置 `mcp_client_config.json`，或设置环境变量 `CATEGORY_MATCHING_MCP_CONFIG` 指向该文件。
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

示例配置见仓库内 `mcp_client_config.json`。

## 大模型二次规则匹配（相似度 &lt; 0.9）

当相似度检索结果 &lt; 0.9 时，可调用大模型根据品类文本生成一句简短描述，再对该描述做一次关键词规则匹配；若规则命中则按规则结果输出。未配置 API Key 时该步骤自动跳过。

环境变量（可选）：
- `CATEGORY_MATCHING_LLM_API_KEY`：大模型 API Key（不设则不用 LLM）
- `CATEGORY_MATCHING_LLM_API_URL`：OpenAI 兼容接口 base URL，默认 `https://api.openai.com/v1`
- `CATEGORY_MATCHING_LLM_MODEL`：模型名，默认 `gpt-3.5-turbo`

## 使用与排错

解压发布包后，将 `excel`、`model`、`output` 与 exe 放在同一目录下运行。  
若出现 **“Failed to load Python DLL”** 或 **LoadLibrary** 报错，请查看同目录下的 **使用说明.txt**，按其中步骤操作（纯英文路径、VC++ 运行库、运行诊断.bat、OneFile 版等）。
