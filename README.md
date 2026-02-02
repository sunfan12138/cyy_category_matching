# cyy_category_matching 使用说明

## 1. 项目简介

**cyy_category_matching** 是一款基于 **规则 + 相似度 + LLM** 的 Excel 批量品类匹配工具。

- **项目用途**：从 Excel 读取匹配规则与已校验品牌数据，对输入的品类文本进行规则匹配或 BGE 向量相似度匹配，结果输出到 Excel；当相似度低于阈值时，可调用大模型生成品类描述并再次做关键词规则匹配。
- **适用场景**：需要将大量「待匹配品类」对照「原子品类/品牌」做标准化归类的业务（如商品分类、品牌映射等）。
- **核心能力**：
  - **规则匹配**：基于关键词规则表（Excel）优先命中。
  - **相似度匹配**：使用 BGE 向量与已校验品牌做相似度检索。
  - **LLM 兜底**：相似度 &lt; 0.9 时，可调用大模型（支持 MCP 工具）生成描述后再做规则匹配。

---

## 2. 环境要求

- **Python**：&gt;= 3.11（由项目根目录 `.python-version` 指定，uv 会自动使用或安装）。
- **操作系统**：Windows / macOS / Linux。
- **uv**：本项目以 **uv** 作为唯一的包管理与运行入口，请先安装 uv：
  - **macOS / Linux**：`curl -LsSf https://astral.sh/uv/install.sh | sh`
  - **Windows（PowerShell）**：`powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`
  - 安装后执行 `uv --version` 确认可用。

---

## 3. 快速开始（推荐）

### 3.1 克隆项目

```bash
git clone <仓库地址>
cd category_matching
```

### 3.2 使用 uv 安装依赖

```bash
uv sync
```

如需同时安装开发/打包依赖（测试、PyInstaller）：

```bash
uv sync --group dev
```

### 3.3 使用 uv 运行项目

```bash
uv run main.py
```

或使用入口命令（安装依赖后）：

```bash
uv run category-matching
```

### 3.4 最小可运行示例

1. 在项目根目录下创建 `excel`、`model`、`output` 三个目录。
2. 将规则 Excel（默认文件名：`原子品类关键词.xlsx`）和已校验品牌 Excel（默认：`校验过的品牌对应原子品类.xlsx`）放入 `excel/`。
3. （可选）将 BGE 模型放入 `model/`，或首次运行时会自动下载。
4. 执行：

```bash
uv run main.py
```

5. 按提示输入待匹配品类文件路径（每行一个品类），或使用命令行参数：

```bash
uv run main.py 待匹配品类.txt
```

6. 匹配结果会写入 `output/` 目录下的 Excel 文件。

---

## 4. 使用说明

### 4.1 输入文件说明（Excel / 品类文件）

- **规则与已校验品牌（Excel）**  
  放在 `excel/` 目录（或通过环境变量 `CATEGORY_MATCHING_EXCEL_DIR` 指定）：
  - **原子品类关键词.xlsx**：规则表，用于关键词规则匹配。
  - **校验过的品牌对应原子品类.xlsx**：已校验品牌表，用于相似度匹配与向量计算。
- **待匹配品类文件**  
  任意 UTF-8 文本文件，**每行一个品类**；程序会读取该文件并对每行执行匹配，结果写入 Excel。

### 4.2 输出文件说明

- **匹配结果 Excel**：保存在 `output/`（或 `CATEGORY_MATCHING_OUTPUT_DIR` 指定目录），文件名形如 `源文件名_匹配结果_时间戳.xlsx` 或 `匹配结果_时间戳.xlsx`。
- **列含义**：输入品类、一级原子品类、品类编码、原子品类、匹配方式（规则/相似度/搜索后匹配等）、相似度匹配结果、大模型描述。
- **日志**：写入 `logs/` 目录，按日期命名 `category_matching_YYYYMMDD.log`。

### 4.3 运行方式说明

**方式一：使用 uv run（源码运行，推荐开发者）**

```bash
uv run main.py
uv run main.py 待匹配品类.txt
uv run main.py 待匹配品类.txt --no-loop
```

- 不传参数：进入交互式，提示输入文件路径，输入 `q` 退出。
- 传文件路径：先处理该文件，然后根据是否 `--no-loop` 决定是否继续交互。
- `--no-loop`：仅处理指定文件一次后退出。

**方式二：使用已构建的可执行文件（非开发用户）**

- **Windows**：运行 `dist/CategoryMatching.exe`（OneFile 单文件）或 `dist/CategoryMatching/CategoryMatching.exe`（onedir）。
- **macOS / Linux**：运行 `dist/CategoryMatching/CategoryMatching`。
- 将 `excel`、`model`、`output` 文件夹放在**与可执行文件同一目录**（或通过环境变量指定），双击或在终端运行即可。

### 4.4 配置文件说明（app_config.yaml）

所有可调参数统一放在 **config/app_config.yaml**（YAML 格式）中：

- **llm**：大模型 API（api_key、api_key_encrypted、base_url、model）
- **mcp**：MCP 服务器列表（servers），供大模型调用搜索等工具
- **matching**：相似度阈值、LLM 回退阈值、批量并发数、未匹配标记等
- **app**：规则/品牌 Excel 文件名、输入文件名忽略
- **embedding**：BGE 模型 ID、bge_weight、编码批大小等
- **llm_client**：max_tokens、日志摘要长度
- **prompt**：参考关键词条数与字数

首次使用：将 **config/app_config.yaml.example** 复制为 **config/app_config.yaml**，按需修改。若未创建 app_config.yaml，程序使用内置默认值。

### 4.5 常见使用示例

```bash
# 交互式：运行后按提示输入文件路径
uv run main.py

# 指定一个文件，处理完后继续等待下一个路径
uv run main.py D:/data/品类列表.txt

# 指定一个文件，处理完即退出
uv run main.py D:/data/品类列表.txt --no-loop
```

**环境变量（可选）**：可覆盖默认目录，便于多环境或打包后自定义路径。

| 变量 | 含义 |
|------|------|
| `CATEGORY_MATCHING_BASE_DIR` | 基准目录（默认：源码为项目根，打包后为 exe 所在目录） |
| `CATEGORY_MATCHING_EXCEL_DIR` | 规则/已校验品牌 Excel 目录 |
| `CATEGORY_MATCHING_OUTPUT_DIR` | 匹配结果输出目录 |
| `CATEGORY_MATCHING_MODEL_DIR` | BGE 模型目录 |
| `CATEGORY_MATCHING_LOG_DIR` | 日志目录 |

---

## 5. 项目结构说明

| 路径 | 职责 |
|------|------|
| `main.py` | 入口：加载配置与规则 → 循环接受文件路径 → 批量匹配 → 输出 Excel；支持 `--input`、`--no-loop`。 |
| `paths.py` | 路径入口：从 `core.config` 统一导出基准目录、excel/model/output/logs、用户路径规范化（含 WSL 盘符转换）。 |
| `app/` | 应用层：`batch_match.py` 批量匹配流程；`file_io.py` 品类文件读取、结果 Excel 写入。 |
| `core/` | 核心领域：`models.py` 数据模型；`loaders.py` Excel 加载规则与品牌；`matching.py` 规则匹配与相似度回退；`embedding.py` BGE 向量与组合相似度；`config/` 路径、LLM、MCP 配置（统一配置包）；`utils/` Excel 读写、相似度计算。 |
| `models/` | Pydantic Schema：`schemas.py` 全局配置、类目节点、匹配结果及 JSON 配置解析（供 `core.config` 使用）。 |
| `llm/` | 大模型封装：`prompt.py` 提示词；`client.py` 客户端（支持 MCP 工具）；`llm_config.py` 配置与加密 CLI（`uv run -m llm.llm_config <明文key>`）。 |
| `mcp_client/` | MCP 客户端：通过 `config/app_config.yaml` 的 `mcp.servers` 连接外部 MCP 服务器并调用工具。 |
| `config/` | 配置文件目录：**app_config.yaml**（统一 YAML，含 llm、mcp、matching、app、embedding、llm_client、prompt）；复制 `app_config.yaml.example` 为 `app_config.yaml` 后修改。API Key 加密：`uv run -m core.config <明文key>`。 |
| `tests/` | 单元测试（`uv run pytest`），`unit/` 下按模块划分。 |
| `scripts/build.py` | 跨平台构建脚本，内部通过 uv 调用 PyInstaller。 |
| `build.spec` / `build-onefile.spec` | PyInstaller 配置：onedir（目录）与 onefile（单文件）。 |

---

## 6. 构建与打包说明（uv + PyInstaller）

### 6.1 构建前准备

- 已安装 **uv**，且项目可正常执行 `uv sync --group dev`。
- 构建会安装 PyInstaller（dev 依赖），并依赖当前项目的 `uv.lock` 与 `.python-version` 保证可复现。

### 6.2 使用 uv 的构建流程

1. 同步依赖（含 PyInstaller）：`uv sync --group dev`
2. 执行构建脚本（推荐）：`uv run python scripts/build.py`  
   或直接调用 PyInstaller：`uv run pyinstaller --clean build.spec` / `build-onefile.spec`

### 6.3 构建命令示例

```bash
# 使用脚本（推荐）：默认 Windows 为 onefile，其他为 onedir
uv run python scripts/build.py

# 指定打包模式与输出目录
BUILD_TARGET=onefile uv run python scripts/build.py
OUTPUT_DIR=release uv run python scripts/build.py
VERSION=0.2.0 BUILD_TARGET=onedir uv run python scripts/build.py
```

**Windows PowerShell：**

```powershell
$env:BUILD_TARGET="onefile"; uv run python scripts/build.py
```

**保留的壳脚本（内部仍调用 uv）：**

- Windows：`build.bat`（默认 onefile）
- macOS / Linux：`./build.sh`（默认 onedir）

### 6.4 构建产物说明

- **onedir**（`build.spec`）：在 `dist/CategoryMatching/` 下生成可执行文件及依赖目录；分发时需打包整个目录。
- **onefile**（`build-onefile.spec`）：在 `dist/` 下生成单个可执行文件（如 `CategoryMatching.exe`）；运行时解压到临时目录。

### 6.5 Windows / macOS / Linux 注意事项

- **Windows**：OneFile 更便于分发；若出现 “Failed to load Python DLL” 或 LoadLibrary 报错，请将程序放在**纯英文路径**、安装 VC++ 运行库、解除文件“锁定”并排除杀毒（详见下文 FAQ）。
- **macOS / Linux**：通常使用 onedir；运行前赋予可执行权限：`chmod +x dist/CategoryMatching/CategoryMatching`。
- 打包后运行：需在可执行文件同目录下放置 `excel`、`model`、`output`（及可选 `config`），或通过上述环境变量指定路径。

---

## 7. 常见问题（FAQ）

### uv 相关

- **未找到 uv 命令**  
  请按「环境要求」安装 uv，并确认安装目录已加入 PATH；安装后执行 `uv --version` 校验。

- **uv sync 很慢或失败**  
  检查网络与 PyPI/镜像；若使用私有或 CPU 版 PyTorch 等，确认 `pyproject.toml` 中 `[[tool.uv.index]]` 等配置正确。

### 依赖安装失败

- **torch 或 sentence-transformers 安装失败**  
  本项目通过 `tool.uv.sources` 使用 PyTorch CPU 索引；若需 GPU 版或其它源，需修改 `pyproject.toml` 中对应 index 配置后重新 `uv lock` 与 `uv sync`。

- **uv.lock 冲突或过时**  
  在项目根执行 `uv lock`，解决冲突后提交更新后的 `uv.lock`。

### 构建失败排查

- **PyInstaller 报错缺少模块**  
  在 `build.spec` / `build-onefile.spec` 的 `hiddenimports` 中补充缺失模块，再执行 `uv run pyinstaller --clean <spec>` 或 `uv run python scripts/build.py`。

- **打包后运行报错**  
  确认 `excel`、`model`、`output` 与可执行文件同目录（或通过环境变量指定），且所需 Excel 文件名与默认一致（或后续扩展支持自定义）。

### 运行无输出等情况

- **“加载数据失败”**  
  检查 `excel/` 下是否存在 `原子品类关键词.xlsx` 与 `校验过的品牌对应原子品类.xlsx`，或通过 `CATEGORY_MATCHING_EXCEL_DIR` 指定正确目录。

- **结果 Excel 未生成**  
  查看 `output/`（或 `CATEGORY_MATCHING_OUTPUT_DIR`）是否有写入权限；查看 `logs/` 下当日日志是否有异常。

- **Windows 下 “Failed to load Python DLL” / LoadLibrary 报错**  
  1）将整个程序目录移到**纯英文路径**（如 `C:\CategoryMatching`）；  
  2）安装 [Microsoft Visual C++ Redistributable 2015-2022 (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)；  
  3）若从浏览器下载的 zip，解压后对程序文件夹右键 → 属性 → 勾选「解除锁定」；  
  4）将程序目录加入杀毒/安全软件排除项；  
  5）可尝试以管理员身份运行可执行文件。

---

## 8. 附录

### 8.1 常用 uv 命令速查

| 命令 | 说明 |
|------|------|
| `uv sync` | 按 `pyproject.toml` + `uv.lock` 同步依赖并创建/更新虚拟环境 |
| `uv sync --group dev` | 同时安装 dev 依赖（如 pytest、pyinstaller） |
| `uv run main.py` | 使用项目环境运行 `main.py` |
| `uv run category-matching` | 使用项目环境运行入口命令（同 main） |
| `uv run pytest` | 运行测试 |
| `uv run python scripts/build.py` | 执行构建脚本（PyInstaller 打包） |
| `uv build` | 构建 wheel / sdist（用于分发或发布） |
| `uv add <包名>` | 添加依赖并更新 lock |
| `uv add --group dev <包名>` | 添加开发依赖 |
| `uv lock` | 更新锁文件 |

### 8.2 推荐使用方式

- **开发者**：克隆后 `uv sync --group dev`，将 `config/app_config.yaml.example` 复制为 `config/app_config.yaml` 并按需修改；日常使用 `uv run main.py` 或 `uv run category-matching` 运行，用 `uv run pytest` 跑测试，用 `uv run python scripts/build.py` 打包。
- **非开发用户**：使用发布包中的可执行文件，将 `excel`、`model`、`output` 与可执行文件放在同一目录（或通过环境变量指定），直接运行；大模型与 MCP 为可选，需时在 `config/` 下配置 **app_config.yaml**。
