# 数据合并工具

当前开发版本：v2.5.0。

这是一个基于 PySide6 的桌面工具，用于读取多种实验数据文件，预览并合并数据列，并支持将结果导出或发送到 Origin。根目录的 `数据合并工具.py` 是本地启动入口，实际业务代码在 `src/data_merge_tool/` 中。

## v2.5.0 更新要点

- 将数据探测、读取、合并、界面和 Origin 自动化拆分为职责明确的模块，删除旧版聚合转发层和版本化启动脚本。
- 文件夹拖放的递归扫描改为后台任务，避免大目录阻塞界面；外部拖入使用复制语义，列表内部仍可拖动排序。
- 数据探测只采样前 500 行，统一处理 quoted 字段、空字段、常见文本编码及 Excel 内置编码；读取阶段继续保留明确的解析错误。
- 所有 Origin 操作共用一个 FIFO 任务队列和 busy 状态。worker 后台处理期间显示等待光标，错误提示框恢复普通箭头；操作不再因忙碌直接丢弃。
- “导入 Origin”在没有可见实例时会启动 Origin，导入完成后恢复并前置其窗口；其他绘图和格式操作仍要求已有可见 Origin。
- Origin 自动化隔离到常驻 worker 子进程，GUI 主进程不加载 `originpro`/`OriginExt`。worker 超时或退出后由客户端重启。
- Origin 格式撤销作用于执行撤销时的当前活动图，不做项目名或原图身份硬校验，以免阻断格式应用。
- 用户 preset 改为原子保存，损坏文件会隔离并提示。X/Y 标题和图例文本仅保留在当前会话中，不写入 preset。
- 文件对话框和数据解析错误保持可见，不使用额外 fallback 掩盖真实问题。

## 目录结构

- `src/data_merge_tool/`：当前 v2.5.0 模块化源码。
- `src/data_merge_tool/resources/`：QSS 和界面静态资源。
- `sample/`：用于手动验证读取和合并逻辑的示例数据。
- `packaging/`：PyInstaller 打包配置。
- `tests/`：数据读取、合并、后台任务、Origin worker 和界面组件测试。
- `requirements_desktop.txt`：桌面版运行与打包依赖。

旧版源码副本、demo、exe、PyInstaller build 缓存和 `__pycache__` 不再纳入版本库；后续版本变更用 Git commits/tags 管理，发布产物放到 GitHub Releases 或本地 `artifacts/`。

## 本地运行

```powershell
pip install -r .\requirements_desktop.txt
python .\数据合并工具.py
```

也可以用可编辑安装方式运行：

```powershell
pip install -e .
data-merge-tool
```

如果使用现有 conda 环境：

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' .\数据合并工具.py
```

## 打包

```powershell
python -m PyInstaller --clean --noconfirm `
  --distpath .\artifacts\dist `
  --workpath .\artifacts\build\v2.5.0 `
  .\packaging\build_windows.spec
```

打包输出默认位于 `artifacts/dist/`，该目录已被 `.gitignore` 排除。

## 轻量检查

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' -B -c "import ast; from pathlib import Path; files=list(Path('src').rglob('*.py'))+list(Path('tests').rglob('*.py')); [ast.parse(p.read_text(encoding='utf-8'), filename=str(p)) for p in files]; print(len(files))"
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' -B -m unittest discover -s tests -v
git diff --check
git status --short
```

Windows 下 `git diff --check` 可能只提示 LF/CRLF 转换；没有空白错误即可。

## 本地数据与缓存

- 用户 preset：`%APPDATA%\DataMergeTool\user_presets.json`。
- 默认 Origin 导出目录：`%APPDATA%\DataMergeTool\origin_exports\`。
- `sample/`、`artifacts/`、`build/`、Python/测试缓存和本地 preset 均不提交。
- 清理缓存时可以删除 `__pycache__/`、顶层 `build/` 和 `artifacts/build/`；`artifacts/dist/`、`artifacts/wheel/` 以及 `sample/` 不是缓存，默认保留。

## 模块说明

- `main.py`：延迟加载 GUI，并分派 `--origin-worker` 入口。
- `data_reading/`：文件发现、自动探测和 Excel/text 表格读取。
- `merge/`：列校验、来源标签和合并表构建。
- `ui/main_window.py`：窗口组装及跨面板工作流协调。
- `ui/file_queue.py` / `read_options_panel.py` / `merge_panel.py`：文件、读取选项和合并参数组件。
- `ui/preview_panel.py` / `plot_preview.py`：表格及 matplotlib 预览组件。
- `ui/controls.py` / `task_runner.py`：通用控件和后台任务执行器。
- `origin/client.py` / `worker.py` / `automation.py` / `protocol.py`：Origin 子进程通信与自动化边界。
- `origin/field_handlers.py`：Origin 样式字段读取、应用和快照恢复。
- `origin/windowing.py`：可见 Origin 窗口检测、恢复和前台激活。
- `origin/panel.py` / `panel_actions.py` / `panel_presets.py`：Origin UI 组合、操作和 preset 控制。
- `origin/presets.py` / `style_registry.py`：preset 存储及样式字段注册。
- `resources/`：应用与 Origin 面板 QSS、勾选图标。
- `constants.py`：应用常量、资源路径和 Qt 常量别名。
