# 数据合并工具

当前开发版本：v2.2。

这是一个基于 PySide6 的桌面工具，用于读取多种实验数据文件，预览并合并数据列，并支持将结果导出或发送到 Origin。根目录的 `数据合并工具_v2.2.py` 是本地启动入口，实际业务代码在 `src/data_merge_tool/` 中。

## 目录结构

- `src/data_merge_tool/`：当前 v2.2 模块化源码。
- `src/data_merge_tool/assets/`：界面静态资源。
- `sample/`：用于手动验证读取和合并逻辑的示例数据。
- `packaging/`：PyInstaller 打包配置。
- `requirements_desktop.txt`：桌面版运行与打包依赖。

旧版源码副本、demo、exe、PyInstaller build 缓存和 `__pycache__` 不再纳入版本库；后续版本变更用 Git commits/tags 管理，发布产物放到 GitHub Releases 或本地 `artifacts/`。

## 本地运行

```powershell
pip install -r .\requirements_desktop.txt
python .\数据合并工具_v2.2.py
```

也可以用可编辑安装方式运行：

```powershell
pip install -e .
data-merge-tool
```

如果使用现有 conda 环境：

```powershell
& 'D:\Program Files\Anaconda3\envs\my_base\python.exe' .\数据合并工具_v2.2.py
```

## 打包

```powershell
python -m PyInstaller --clean --noconfirm `
  --distpath .\artifacts\dist `
  --workpath .\artifacts\build\v2.2 `
  .\packaging\build_v2.2.spec
```

打包输出默认位于 `artifacts/dist/`，该目录已被 `.gitignore` 排除。

## 轻量检查

```powershell
python -m compileall -q src\data_merge_tool
python -m py_compile src\data_merge_tool\origin_panel.py src\data_merge_tool\main.py .\数据合并工具_v2.2.py
```

## 模块说明

- `main.py`：应用入口。
- `main_window.py`：主窗口、数据合并面板、Origin 面板切换。
- `data_io.py`：文件识别、读取、列校验和合并逻辑。
- `origin_panel.py`：嵌入式 Origin 绘图面板。
- `origin.py`：数据合并结果导入 Origin。
- `widgets.py`：通用控件、按钮工厂、文件选择和后台任务线程。
- `constants.py`：应用常量、资源路径和 Qt 样式。
