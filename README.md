# 品类匹配工具

从 Excel 读取匹配规则与已校验品牌数据，对输入的品类文本进行规则匹配或 BGE 相似度匹配，结果输出到 Excel。

## 开发运行

- 依赖：`uv sync`（含 dev 时 `uv sync --group dev`）
- 运行：`uv run python main.py`

## 打包

**Windows**
- 本地：`build.bat`（生成 `dist\CategoryMatching\`，内含 exe 与 `_internal`）
- OneFile 备用：`uv run pyinstaller --clean build-onefile.spec`（生成 `dist\CategoryMatching-OneFile.exe`）

**macOS**
- 在项目根目录执行：`./build.sh`（需先 `chmod +x build.sh`）
- 生成 `dist/CategoryMatching/`，内含可执行文件 `CategoryMatching`（无后缀）及依赖
- 分发时打包整个目录；运行时在可执行文件同目录下放置 `excel`、`model`、`output`，终端执行 `./CategoryMatching`

## 使用与排错

解压发布包后，将 `excel`、`model`、`output` 与 exe 放在同一目录下运行。  
若出现 **“Failed to load Python DLL”** 或 **LoadLibrary** 报错，请查看同目录下的 **使用说明.txt**，按其中步骤操作（纯英文路径、VC++ 运行库、运行诊断.bat、OneFile 版等）。
