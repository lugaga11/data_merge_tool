# AGENTS.md

## 项目定位

这是一个 Windows 桌面端实验数据合并工具，当前开发版本为 `v2.3.0`。应用基于 PySide6，主要面向本地数据文件读取、预览、列选择、合并、导出，以及与 Origin/OriginPro 的自动化联动。

根目录的 `数据合并工具_v2.3.0.py` 是当前版本的本地启动入口；实际业务代码在 `src/data_merge_tool/`。发布包通过 PyInstaller 生成，输出默认放在 `artifacts/`，该目录不纳入版本控制。

## 目录和模块

- `src/data_merge_tool/main.py`：应用入口，创建 `QApplication` 和 `MainWindow`。
- `src/data_merge_tool/main_window.py`：主窗口、数据合并面板、预览、导出、导入 Origin 入口。
- `src/data_merge_tool/data_io.py`：数据文件识别、编码/分隔符/表头探测、读取、列校验、合并表构建。
- `src/data_merge_tool/origin_panel.py`：Origin 绘图和格式控制面板。
- `src/data_merge_tool/origin_client.py`：GUI 主进程侧 Origin worker 客户端。
- `src/data_merge_tool/origin_worker.py`：Origin 自动化子进程入口。
- `src/data_merge_tool/origin_automation.py`：worker 专用 Origin 自动化实现。
- `src/data_merge_tool/origin_protocol.py`：主进程和 worker 共享的数据结构与序列化。
- `src/data_merge_tool/widgets.py`：通用控件、按钮工厂、文件队列拖拽控件、后台任务线程。
- `src/data_merge_tool/constants.py`：应用版本、支持的文件类型、Qt 常量别名、全局样式。
- `src/data_merge_tool/models.py`：表格预览模型。
- `src/data_merge_tool/data_types.py`：跨模块传递的数据结构。
- `src/data_merge_tool/errors.py`：用户可见异常类型。
- `packaging/build_windows.spec`：当前 PyInstaller 打包配置。
- `sample/`：本地验证样例数据，已被 `.gitignore` 排除。
- `artifacts/`：本地构建和发布产物，已被 `.gitignore` 排除。

## 运行和验证

优先使用用户机器上的 `my_base` 环境进行验证：

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' .\数据合并工具_v2.3.0.py
```

轻量语法检查可以用：

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' -B -c "import ast; from pathlib import Path; files=['src/data_merge_tool/main_window.py','src/data_merge_tool/origin_panel.py','src/data_merge_tool/widgets.py','src/data_merge_tool/data_io.py','src/data_merge_tool/origin_client.py','src/data_merge_tool/origin_worker.py','src/data_merge_tool/origin_protocol.py','src/data_merge_tool/origin_automation.py']; [ast.parse(Path(p).read_text(encoding='utf-8'), filename=p) for p in files]"
```

离屏 GUI 构造检查可以用：

```powershell
$env:QT_QPA_PLATFORM='offscreen'
$env:PYTHONPATH=(Resolve-Path -LiteralPath 'src').Path
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' -B -c "from PySide6.QtWidgets import QApplication; from data_merge_tool.main_window import MainWindow; app=QApplication([]); w=MainWindow(); print(type(w).__name__, w.origin_worker._process is None, w.originPanel.origin_client is w.origin_worker); w.close()"
```

提交前至少跑：

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' -B -m unittest tests.test_origin_client -v
git diff --check
git status --short
```

`git diff --check` 在 Windows 上可能提示 LF/CRLF 转换；只要没有空白错误即可。

## 打包

当前打包锚点是 `packaging/build_windows.spec`，入口会匹配根目录的 `*_v2.3.0.py`。使用 PyInstaller 时建议继续沿用 `my_base`：

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' -m PyInstaller --clean --noconfirm `
  --distpath .\artifacts\dist `
  --workpath .\artifacts\build\v2.3.0 `
  .\packaging\build_windows.spec
```

打包产物默认不提交。发布时只提交源码和配置，exe 放到 `artifacts/dist/` 或 GitHub Release。

## 重要设计约束

### 文件选择和拖拽

- 文件队列控件是 `widgets.py` 里的 `DropFileList`。
- 外部文件/文件夹拖入应作为 `CopyAction` 接受；内部列表重排仍保留移动语义。
- 添加文件按钮只负责选择文件；文件夹展开属于拖拽逻辑。
- 不要把文件选择再包一层“回退 PySide 原生对话框”的防御函数。当前代码应直接使用 `QFileDialog.getOpenFileNames()`、`QFileDialog.getSaveFileName()`、`QFileDialog.getExistingDirectory()`，问题需要暴露出来而不是被 fallback 掩盖。

### Origin 自动化

- `originpro`/`OriginExt` 可能影响 Windows COM/OLE 状态，不能在 PySide6 GUI 主进程里 import 或调用。
- 主进程通过 `OriginWorkerClient` 与常驻 worker 子进程通信；worker 入口是 `data_merge_tool.origin_worker`，打包后同一个 exe 用 `--origin-worker` 进入 worker 模式。
- 真实 Origin 自动化逻辑集中在 `src/data_merge_tool/origin_automation.py`；只有这个 worker 专用模块可以 import `originpro`。
- 绘图、读取样式、应用格式、撤销、导出、导入 Origin 都应通过 worker 命令执行。worker 卡死或退出时，主进程应 kill/restart worker，而不是恢复全局频繁 `detach()`。
- 如果继续排查卡死、禁止拖拽、文件对话框异常，优先检查 worker 边界和 IPC 调用链，不要加文件对话框 fallback。

### Preset 持久化

- 用户 preset 当前只应保存在 `%APPDATA%\DataMergeTool\user_presets.json`，环境变量不可用时退到用户 home 下的 `.data_merge_tool`。
- 不再读取源码目录旁边的旧 `user_presets.json`。
- 不再静默吞掉 preset JSON 解析错误或格式错误；配置损坏应该直接暴露。
- `PRESETS` 当前为空，启动时要允许没有内置 preset。

### 数据合并

- 对外合并入口优先使用 `build_origin_import_table()` 和 `build_prechecked_merged_table()`。
- 不要重新引入只返回 dataframe 的薄 wrapper，除非确实有新的调用方需要。
- 数据读取逻辑要尽量保留结构化解析；不要用临时字符串拼接绕过 `read_table()`、`detect_read_options()`、`preflight_merge_columns()` 等已有边界。
- 自动读入检测集中在 `src/data_merge_tool/data_io.py`：`detect_read_options()` 只读取前 500 行做分隔符、表头和数据起点判断，`read_table()` 才负责完整读取。不要为了某个样例把完整文件扫描重新塞回检测路径。
- 表头候选使用 `_DetectionCandidate` 评分，优先级是有无表头、数据列宽、连续数据行长度、起始行更靠前；不要再恢复只比较 header/skip 行的零散判断。
- 分隔符拆分必须走 `_split_fields()`，逗号/Tab/分号使用 `csv.reader`，这样 quoted 数字和空字段不会被误判；不要退回简单 `str.split()`。
- 自动编码检测为快速路径：BOM、ASCII/UTF-8、确有中文的 GBK，最后用 `latin1` 保住西文仪器符号；不要重新引入 `charset-normalizer`、`cp1250/cp1257` 猜测或编码缓存。手动的 `ANSI/系统默认` 仍映射到 `mbcs`。
- Excel 文件不做文本编码探测，自动编码显示为 `Excel 内置`，实际读取交给 `openpyxl`/`xlrd`。
- `跳过异常行` 只处理数据区内的坏行，不负责自动跳过文件开头的说明区。像 `sample/kto sw 2v.csv` 这类前 30 行是仪器设置、31 行才是真表头的文件，手动 `skip_rows=0` 本来就会让 pandas 从说明区开始建表并可能失败；正确行为是自动识别或手动跳过 30 行。

## 代码风格

- 保持改动范围小，优先沿用现有 PySide6 写法和本项目的 helper。
- 手写编辑优先用 `apply_patch`。
- 不要删除用户本地样例、构建产物或未跟踪文件，除非用户明确要求。
- 不要恢复已经清理掉的兼容/防御代码，特别是文件对话框 wrapper、旧 preset 路径 fallback、无意义的 `hasattr` 空保护。
- 遇到 Windows 中文路径或终端乱码时，不要仅凭 PowerShell 显示判断文件坏了；用 Python 按 UTF-8 读取或 AST 校验确认。

## Git 注意事项

- 当前主分支是 `main`。
- 如果用户只说提交，先 `git status --short` 和 `git diff --check`，再提交当前确认范围。
- `.git` 在受限环境中可能需要提权才能 `git add` 或 `git commit`。
- `sample/`、`artifacts/`、`user_presets.json`、`origin_exports/` 是本地数据/产物，默认不提交。
