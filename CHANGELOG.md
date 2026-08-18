# GZ 安环监测系统 — 版本更新日志

## v5.31（2026-08-18）✅ 当前版本

### 🐛 修复（Win7 预测闪退的全链路诊断修复）
- **背景**：v5.30 用户实测仍"win10正常 / win7点击开始预测闪退"。v5.27/v5.28/v5.29 连续三轮未根除根本原因是**诊断黑盒**——`main.py` 的 `_global_exception_hook` **只 print 到 stderr 却从未真正写文件**，Win7 用户看不到 stderr，结果就是"静默闪退"，无法提供任何 Python 栈
- **修复 1：crash.log 真正落盘**：`_write_crash_log()` 写到 `%APPDATA%\GZ_Monitor\logs\crash.log`（权限稳定路径），所有 Python 未捕获异常均落盘；SEH 注册成功也写入日志证明已注册。修复 `from datetime import datetime` 在 module 顶层（之前 `_write_crash_log` 调 `datetime.now()` 时 NameError，落入 fallback `print`）
- **修复 2：Windows 原生崩溃兜底**：通过 ctypes 注册 `SetUnhandledExceptionFilter` + `AddVectoredExceptionHandler` + `MiniDumpWriteDump`，可在 matplotlib/Qt C 层段错误（如 Win7 高分屏 QImage blit 越界）时落盘 `.dmp` 文件 + 写 `crash.log` 一行 `NATIVE_CRASH`
- **修复 3：Win7 环境诊断**：`main()` 启动后立即调用 `_log_win7_diagnostics()`，把 OS 版本（`platform.release()`/`version()`）、Qt/PyQt5/matplotlib 版本、`screen.devicePixelRatio()`、可执行路径全部记录到 `crash.log`，下一轮排查不再需要第二次提问
- **修复 4：预测链路埋点**：`_run_prediction` 进入时记录 `dpr + horizon + pred_type + has_data`；`_assemble_and_plot_pred_chart` 出图前记录 `canvas_size + chart_size + n_curves + mode + normalize`，每次 `plot_series` + `draw_idle` 都有日志；捕获异常时同时调 `_write_crash_log('PRED_CHART', tb)` 落盘
- **改动文件**：`src/main.py`（核心）、`src/main_window.py`（预测埋点）

### 📋 用户使用说明
1. 双击 `dist\GZ_Monitor_v5.31_Win7.exe`
2. 若 Win7 仍崩溃 → 把 `%APPDATA%\GZ_Monitor\logs\` 下的 `crash.log` + `crash_<pid>_<ts>.dmp` 发给我，我有完整 Python 栈 + MiniDump 才能精准定位
3. 若不再崩溃 → 视为修复成功；最后保留 v5.28 浮层改动（已确认 Win7 安全）
- **产物**: `dist\GZ_Monitor_v5.31_Win7.exe`（70 MB，含 dbghelp.dll 支持 MiniDump）
- **提交**: `efd3c51`

## v5.30（2026-08-18）

### ✨ 改进（状态栏显示"生成时间"，一眼确认是否更新到最新版）
- **背景**：用户多次反馈"生成时间不对，是不是没更新"。排查确认：v5.29 EXE 实际构建于 2026-08-18 14:08（对应提交 `1444174`），**确已更新**；代码内本来没有任何"生成时间"界面标签，用户看到的是 Windows 资源管理器里 EXE 文件的"修改/创建时间"，在 `dist/` 有 13 个版本、且跨机拷贝会重置"创建时间"时极易误判为旧版
- **修复/改进**：状态栏新增自维护的"生成时间"——运行时读取**当前 EXE 文件自身的修改时间**显示，格式 `📦 文件名 生成于 YYYY-MM-DD HH:MM`。打开哪个 EXE 就显示那个 EXE 的真实生成时间，无需人工维护版本号，一眼即可确认是否是最新版（v5.30 应显示本次构建时间）
- **改动**：`src/main_window.py` 的 `_update_status_bar()`（注意 `datetime` 在本文件是类而非模块，故用 `datetime.fromtimestamp(...)` 而非 `datetime.datetime.fromtimestamp(...)`）
- **测试**：offscreen 验证状态栏含"生成于"字符串、冒烟无回归

### 🧪 测试
- `tests/smoke_main_window.py` 无回归
- offscreen 端到端：状态栏消息含 `生成于`（如 `📦 python.exe 生成于 2021-05-03 11:54`）—— 通过

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.30_Win7.exe`
- **提交**: `bce214f`

## v5.29（2026-08-18）⏪ 上一版

### 🐛 修复（Win7 预测页「出图/趋势图」闪退 — 真正根因：v5.24/v5.27 的画布加固回归）
- **现象**：v5.28 已去掉 `Qt.Popup` 浮层，但用户实测"**趋势图预测后，闪退**"——崩溃点在"开始预测→出图"那一刻，并非浮层
- **定位方法（关键）**：用 `git diff 9b0ba46(v5.23) HEAD` 逐行比对预测绘制路径，结论：
  - `main_window.py` 的"出图"函数（`_draw_pred_chart_multi` / `_show_prediction_chart` / `pred_chart.plot_series` 等）在 v5.23→当前**完全没改**
  - `chart_widget.py` 的**绘制逻辑（plot_series 等）也没改**
  - 唯一差异 = 我 v5.24（尺寸守卫）+ v5.27（DPR 锁 + `_update_pixel_ratio` 覆盖 + `setDevicePixelRatio(1.0)`）加的 `HoverFigureCanvas` 包装器
- **根因**：v5.23 的 `HoverFigureCanvas` 是干净的（无 `setDevicePixelRatio`、无守卫、无覆盖），让 matplotlib 自然处理 DPI 在 Win7 上稳定。我加的 `setDevicePixelRatio(1.0)` 让画布内部缓冲(1.0)与 Win7 屏幕 DPI(1.25/1.5) 失配，加上 `_update_pixel_ratio` 覆盖打乱 matplotlib 原生 DPR 处理，出图时原生 blit 尺寸错位 → 段错误。**v5.23 不崩，正是因为没这些"加固"**
- **修复**：把 `HoverFigureCanvas` **逐字节还原到 v5.23（9b0ba46）状态**（git blob `e7c1087` 一致）。移除 `setDevicePixelRatio` / `_has_valid_size` / `_update_pixel_ratio` / `resizeEvent`·`draw`·`draw_idle` 覆盖 / `QResizeEvent` import。v5.28 的浮层去 `Qt.Popup` 改动保留（是 genuine 的 Win7 安全改进，只是不是出图崩溃点）
- **经验**：Win7 原生崩溃排查时，用 `git diff <已知好版本> HEAD` 锁定回归点，比"猜 matplotlib 内部机制"可靠得多；"为兼容而加的加固"可能反向引入崩溃

### 🧪 测试
- **删除** `tests/test_device_pixel_ratio.py`（断言 DPR 锁，已失效）
- **改写** `tests/test_pred_chart_draw.py`：去掉 DPR 断言，保留"多曲线/双轴/归一化/clear 全链路不抛异常 + renderer 生成"覆盖
- `tests/smoke_main_window.py` / `test_param_picker.py`(9/9) / `test_pred_chart_draw.py` 全部通过，无回归

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.29_Win7.exe`
- **提交**: `1444174`

---

## v5.28（2026-08-18）（上一版）

### 🐛 修复（Win7 预测页「对比参数」下拉闪退 — 真正的根因）
- **现象**：用户确认 **v5.23 在 Win7 不闪退**，但 v5.25 引入下拉浮层后、v5.26/v5.27 在 Win7 仍闪退（Win10 正常）
- **根因（已纠正 v5.27 的误判）**：v5.27 曾把崩溃归因于 matplotlib 的 `device_pixel_ratio`(DPI)，但 **v5.23 同样走 `HoverFigureCanvas` 的 matplotlib 绘制路径、且在同机 Win7 上不崩**，证明 DPI 不是元凶。真正跨版本稳定引发 Win7 原生崩溃的，是 **v5.25 引入的 `Qt.Popup` 顶层浮层窗口**——它无论 `parent=None`(v5.26) 还是 `parent=self`(v5.25 初版)，本质都是"顶层原生窗口(HWND)"，在 Win7 预测页签内创建/显示即段错误闪退。v5.23 用的是内嵌式选择器（无浮层窗口），故安全
- **修复**：把浮层从"顶层 `Qt.Popup` 窗口"改为 **挂在主窗口下的普通子控件**（`QWidget(self)` 创建、展开时 `setParent(主窗口)` 绝对定位叠加），用全局事件过滤器实现"点击外部 / 按 ESC 关闭"。**零顶层原生窗口、零 Win7 崩溃风险**，且完整保留 v5.25 你要的"按钮 + 下拉多选"UX
- **v5.27 的 DPR 锁处置**：`HoverFigureCanvas.device_pixel_ratio` 强制 1.0 仍保留，但定位为**高分屏防御性加固**（非本次根因）；Win10 100% DPI 下本就是 1.0，行为不变

### 🧪 测试
- **`tests/test_param_picker.py`**：`test_popup_is_not_top_level` 反向回归锁（浮层必须 `parent 不为 None`、不带 `Qt.Popup`/`Qt.Window` 顶层标志）；展开/搜索/全选/反选/清空/信号/空态全通过
- **端到端（offscreen）**：构造 MainWindow → 点「对比参数」展开浮层 → 断言 `visible=True` 且 `parent 为主窗口` 且 `无 Qt.Popup` → 模拟点击浮层外部 → 浮层自动关闭；全程无异常
- `tests/smoke_main_window.py` / `test_pred_chart_draw.py` / `test_device_pixel_ratio.py` 无回归

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.28_Win7.exe`
- **提交**: `a56c5e5`

---

## v5.27（2026-08-18）（已被 v5.28 纠正根因）

### 🐛 修复（原判定为"出图 DPI 崩溃"，实为误判）
- 曾在 `HoverFigureCanvas` 强制 `device_pixel_ratio = 1.0`，意图修复"开始预测出图"崩溃
- **后续纠正**：用户反馈 v5.23 不闪退，而 v5.23 同样走 matplotlib 绘制路径 → 证明 DPI 非元凶。该改动降级为**高分屏防御性加固**保留，真正的崩溃点是 v5.25 引入的 `Qt.Popup` 顶层浮层（见 v5.28）
- **提交**: `a14cc1e`

---

## v5.26（2026-08-18）（上一版）

### 🐛 修复（Win7 打开「数据预测」必崩 + 归一化按钮"消失"）
- **现象**：用户反馈 v5.25「预测一点开就闪退」，且原本好用的「归一化」按钮不见了
- **根因**：v5.25 的下拉浮层被实现为 `QWidget(self)` + `Qt.Popup` 顶层窗口标志，但它位于**隐藏的预测页签内**。一旦打开预测页签、Qt 要为这个带顶层标志的子控件创建原生窗口(HWND)，而其父级此时尚未完成原生窗口化 —— Win7 下直接段错误闪退（offscreen 无头环境无法复现，故 v5.24 的冒烟/单测未能捕获）。整页崩溃导致同页的「归一化」按钮也一并"消失"（代码仍在 `main_window.py:2041`，只是没渲染出来）
- **修复**：浮层改为**真正的顶层窗口**（`QWidget(None)` + `Qt.Popup`）—— 隐藏时不创建 HWND，仅点击「对比参数 (N) ▾」展开时才作为独立顶层弹窗显示，彻底规避"隐藏页签内带顶层标志的子控件"陷阱
- **附带确认**：归一化按钮（`pred_normalize_btn`，`main_window.py:2041`）与对比模式下拉（`pred_mode_combo`）均完好接入 `pred_compare_panel`，崩溃修复后即可正常显示

### 🧪 测试
- **新增回归 `tests/test_param_picker.py::test_popup_is_top_level`**：断言浮层 `parent() is None` 且带 `Qt.Popup` 标志，锁定本修复 —— **9 项单测全过**
- 4 套测试（smoke / param_picker 9 项 / chart_splitter / onboarding）**全绿**，无回归

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.26_Win7.exe`
- **提交**: (待提交)

---

## v5.25（2026-08-17）

### 🎨 简化（对比参数选择器：从"双栏分类+搜索"改为"下拉多选"）
- **来源**：用户在 v5.20 双栏选择器基础上反馈"对比参数选择有点太复杂了"
- **新形态**：主面板只保留一个按钮「对比参数 (N) ▾」，平时只占一行，最大化趋势图空间。点击按钮弹出浮层，浮层内含：
  - 顶部搜索框（按关键字实时过滤勾选项）
  - 中部可滚动分组勾选列表（按废气/废水/其他分组，组标题加粗）
  - 底部全选/清空 + "已选 N / T" 计数
- **消除的复杂度**：原左侧 170px 分类导航栏、内嵌横向分割条、顶部分类/搜索/操作 3 段式 UI 全部移除
- **公共 API 完全不变**：`selected_changed(list)` / `set_available_params` / `get_selected` / `set_selected` / `select_all` / `invert` / `clear_selection` 签名与 v5.20 一致 —— `main_window.py` 的 `_on_compare_params_changed` / `_get_checked_compare_params` / `_populate_compare_list` / `_select_all_params` / `_invert_params` / `_clear_params` 无需改动
- **细节**：
  - 移除 `pred_compare_panel` 内冗余的「📋 对比参数」静态标题（按钮本身已带"对比参数 (N) ▾"）
  - 选择器自身 `minimumHeight` 由 120 → 40（v5.21 缩一次，v5.25 再缩）
  - 浮层 `Qt.Popup`：点外部 / ESC 自动关闭，置顶显示
  - 分类优先级逻辑 `_classify` 完全保留：gas/water > rax > limbo（实际数据下「双轴」组恒为空，与 v5.20~v5.24 一致）

### 🧪 测试
- `tests/test_param_picker.py` 重写为新 API（实例化 / 去重保序 / set_get 往返 / `_classify` 优先级 / 搜索过滤 / 全选反选清空 / 信号 / 空态）—— 8 项全过
- `tests/test_chart_splitter.py` 同步 `minimumHeight` 断言 120 → 40 —— 通过
- `tests/smoke_main_window.py` 同步子组件清单（`toggle_btn`/`popup`/`search_edit`/`_checkboxes`）—— 通过
- `tests/render_param_picker.py` 重写：渲染收起态 / 浮层 / 浮层搜索态 3 张截图

### 📦 交付
- `dist/GZ_Monitor_v5.25_Win7.exe`（单文件，约 55 MB）
- GitHub: `junkechen/gz-monitor`（待 push）

---

## v5.24（2026-08-12）✅ 当前版本

### 🐛 修复（Win7 打开「数据预测」有时闪退）
- **根因**：`chart_widget.HoverFigureCanvas` 继承自 `FigureCanvasQTAgg`，但未重写 `resizeEvent`。该基类在画布尺寸为 **0/负** 时会自动 `draw()`，而 matplotlib **Agg 后端在 Win7 上创建 0 尺寸位图即触发 C++ 层段错误（无 Python 异常、直接闪退）**。两个触发场景：
  1. v5.21 引入的 `QSplitter` 把「趋势图」格拖到极小/折叠，或窗口布局某瞬间使画布高度为 0
  2. v5.23 首次启动教学引导第③步切到预测页时，主窗口几何尚未完全稳定，画布尺寸为 0
- **修复**：在 `HoverFigureCanvas` 重写 `resizeEvent` / `draw` / `draw_idle`，统一加尺寸守卫——「width≤0 或 height≤0 时直接 return，不绘制」。覆盖 `plot_series`(line 505 `draw`)、`_toggle_line`(518 `draw`)、`clear` 后续重绘、以及 splitter 拖拽引起的所有 resize 路径；尺寸恢复有效时基类 `resizeEvent` 正常重绘，图表照常显示
- **影响面**：所有 `ChartWidget`（预测图 + 历史图共用该 canvas 类）均受益；纯防御性改动，有效尺寸时行为与修复前完全一致

### 🧪 测试
- 4 套测试（smoke / param_picker 9 项 / chart_splitter / onboarding）**全绿**，无头构造 MainWindow 不崩、无回归
- 注：该崩溃为 Win7 + 真实显示器特有的 C++ 层问题，offscreen 无头环境无法复现；真实修复效果由用户在本机验收（把趋势图拖到最小、或引导首登切到预测页，验证不再闪退）

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.24_Win7.exe`
- **提交**: (待提交)

---

## v5.23（2026-08-12）

### 🐛 修复（教学引导在本机不可见）
- **根因**：v5.22 的 `TourGuide` 被实现为 `MainWindow` 的**子 widget** 并设置了 `WA_TranslucentBackground`。但 Qt 明确该属性**仅对顶层窗口（top-level）生效**，对子 widget 设置后行为未定义，在 Windows 7 上表现为整个遮罩控件透明、不绘制 —— 用户双击后「什么都没发生」，而引导逻辑其实已跑过一次（故 `app_info.json` 已写入 `first_run:false` + `onboarding_version:1`），之后自然不再触发
- **修复 1**：`TourGuide` 改为**真正的顶层窗口**（`super().__init__()` 无 parent + `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`），`WA_TranslucentBackground` 对其生效，且 `WindowStaysOnTopHint` 保证必定置顶、不被主窗口遮挡
- **修复 2**：聚光灯坐标改用 `target.mapToGlobal(...)`（屏幕坐标）配合 `self.geometry().topLeft()` 换算，遮罩几何用 `self._win.frameGeometry()` 对齐（含标题栏，基准与 `mapToGlobal` 一致）；主窗口 move/resize 时通过 `eventFilter` 自动跟随重定位
- **修复 3**：首登判定升级为**基于 `onboarding_version` 比对** —— 即「首次运行 或 引导版本已过期」才触发。因 v5.22 用户本机已写 `onboarding_version:1`，本次将 `ONBOARDING_VERSION` 自 `1` 升到 `2`，使其**下次双击即可自动重看一次修复版**；看完即写入 `2` 并锁定，仍只触发一次

### 🧪 测试
- **更新 `tests/test_onboarding.py`**：`test_start_onboarding_gating` 同步新语义（非首登+同版本不触发 / 版本过期仍触发 / force 强制触发）；docstring 措辞改为「顶层窗口 + mapToGlobal」 —— **全部通过**
- 4 套测试（smoke / param_picker / chart_splitter / onboarding）全绿

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.23_Win7.exe`
- **提交**: (待提交)

---

## v5.22（2026-08-12）

### ✨ 新增（首次启动教学演示）
- **首登自动引导**：复用语已有的 `user_data_manager.is_first_run()` / `mark_first_run_completed()`，仅在**首次打开应用**时自动触发一次引导，之后本地存储标记（`%APPDATA%/GZ_Monitor/app_info.json` 的 `first_run` 字段），再次打开不再重复
- **本地存储标记**：演示完成或点击「跳过」即写入 `first_run: false` + `onboarding_version`，跨重启/跨会话持久化，纯本地、无需联网
- **8 步产品巡览**：排放口列表 → 实时监测数据 → 切换功能页签 → 开始预测 → 预测结果表 → 对比参数选择器 → 归一化开关 → 对比模式，覆盖核心闭环
- **半透明遮罩 + 聚光灯挖洞 + 脉冲边框高亮**：自绘实现，不修改任何目标控件样式表，避免破坏暗色主题；底部浮层卡片含「上一步 / 跳过 / 下一步」与步骤计数
- **帮助菜单「❓ 重看教学演示」**：可随时强制重看（忽略首登标记，`force=True`）
- **触发位置**：`main.py` 主窗口 `show()` 后延迟 800ms（`QTimer.singleShot`）触发，确保布局稳定后遮罩定位准确

### 🧪 测试
- **新增 `tests/test_onboarding.py`**：首登 gating 纯逻辑（含 `onboarding_version` 写入）、`build_default_steps` 返回 8 步且锚定真实控件、TourGuide 步进/信号/清理、`start_onboarding` gating 与 force 路径 —— **全部通过**
  - 注：offscreen 环境下半透明遮罩子控件的 `show()`/`mapTo` 会触发 Qt 段错误（真实显示器无此问题），测试中对几何相关方法打安全补丁，仅验证逻辑；真实聚光灯/脉冲视觉由用户在本机验收
- **更新 `tests/smoke_main_window.py`**：`required_attrs` 增补 `right_panel` 与 `pred_btn`（引导高亮所需）

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.22_Win7.exe`
- **提交**: (待提交)

---

## v5.21（2026-08-12）

### 🔧 改造（预测页布局）
- **对比参数 / 趋势图改用 `QSplitter(Qt.Vertical)`**：用户可拖拽调大小，解决"趋势图区不能调整大小"的痛点
- **默认趋势图占大头**（比例 ≈ 140:600，约 19% : 81%），首次打开即以图表为主
- **选择器可完全折叠**（`setCollapsible(0, True)`）、趋势图不可折叠（`setCollapsible(1, False)`）；折叠后趋势图占满内容区
- **`ParamPickerPanel` 最小高度从 180 降到 120**：默认展开也不挤压趋势图
- **预测趋势图标题栏新增「已选 N 项」实时统计**：勾选 / 反选 / 清空 / 切模式 / 归一化切换 时同步刷新，折叠选择器后仍可见当前选择
- **新增方法 `_update_selected_count_label()`**：3 处回调（`_on_compare_params_changed` / `_on_pred_mode_changed` / `_on_normalize_toggled`）末尾调用，行为统一

### 🧪 测试
- **新增 `tests/test_chart_splitter.py`**：断言 splitter 方向=Vertical、2 窗格、窗格0=对比参数面板、窗格1=含 `pred_chart` 的 QGroupBox；选择器可折叠、趋势图不可折叠；`param_picker.minimumHeight == 120`；`pred_chart_selected_label` 存在 —— **7 项断言全过**
- **更新 `tests/smoke_main_window.py`**：`required_attrs` 增补 `_pred_chart_splitter` 与 `pred_chart_selected_label`，仍通过
- **更新 `tests/test_param_picker.py`**：原有 9 项全过，未被改动影响
- **新增 `tests/render_pred_layout.py`**：offscreen 渲染 3 张截图 `pred_layout_{default,collapsed,picker_big}.png`，验证默认/全折叠/选择器拉大三种 splitter 状态

### 📦 产物
- **产物**: `dist\GZ_Monitor_v5.21_Win7.exe`（待打包）
- **提交**: (待提交)

---

## v5.20（2026-08-12）

### ✨ 新增
- **指标选择器全面重构**：原"对比参数"为一长条横向滚动（12+ 指标挤一行，难以筛选），重构为**嵌页式双栏选择器**（`ParamPickerPanel`）：
  - **左侧分类导航**：📋 全部指标 / 🔥 废气参数 / 💧 废水参数 / 📊 双轴参数 / ✅ 已选(N) / 🗂️ 其他指标，分类按 `PARAM_CATEGORIES` 自动归类，每个分类后附实时计数（如"🔥 废气参数(6)"）
  - **右侧多选 checklist**：可勾选指标，独立双栏布局，可拖动 splitter 调整左右比例
  - **顶部实时搜索框**：输入关键字即时过滤（模糊匹配："烟" → 烟气温度、烟气流量；"pH" → pH值）
  - **保留**：全选 / 反选 / 清空 / 计数提示
- **新的响应式伸缩**：预测结果区与趋势图区的拉伸比调整为 1:2（趋势图获得更大空间）；分类导航固定 170px，可拖动 splitter 重新分配
- **空态占位**：搜索结果为空时右侧显示"（当前分类下无匹配指标）"占位，避免 UI 错位
- **新增参数分类映射**：`config.PARAM_CATEGORIES`（12 个废气 + 7 个废水参数，含已知的扩展指标如"水温"、"累计流量"）
- **新增 9 项 `ParamPickerPanel` 单测**：实例化、去重保序、分类切换、搜索过滤、全选/反选/清空、信号触发、空态、双轴兜底，全部通过
- **新增 6 张视觉回归截图**：`tests/screenshots/panel_{all,gas,water,selected,search_y烟,narrow}.png`，方便后续改动对比

### 🔧 改造
- `main_window.py`：用 `ParamPickerPanel` 替换原横向滚动 `QListWidget`；7 处回调（`_get_checked_compare_params` / `_on_compare_params_changed` / `_on_pred_mode_changed` / `_on_normalize_toggled` / `_select_all_params` / `_invert_params` / `_clear_params`）改用新接口
- `_on_compare_params_changed` 现在接收 `selected_changed(list[str])` 信号载荷，可空参数仍向后兼容
- `pred_param_list` 属性移除（已被 `param_picker` 取代），冒烟测试同步更新
- `_populate_compare_list` 简化为 `set_available_params + set_selected(prev)`

### 📦 产物
- **提交**: (待提交)
- **产物**: `dist\GZ_Monitor_v5.20_Win7.exe`（待打包）

---

## v5.19.1（2026-08-12）

### 🔧 热修复
- **Bug**: v5.19 启动崩溃。登录后创建主窗口失败，错误 `AttributeError: 'MainWindow' object has no attribute '_pred_chart_mode'`
- **根因**: T01+T02 新增的 `_pred_chart_mode`、`_pred_chart_normalize`、`_history_cache`、`_hist_worker`、`_hist_results`、`_last_pred_horizon`、`_refresh_last_flush`、`_refresh_timer_coalesce` 等状态字段被放在 `__init__` 末尾（在 `_init_ui()` **之后**），但 `_init_ui()` 内部的 `pred_mode_combo.setCurrentText(self._pred_chart_mode)` 需要立即读取 `_pred_chart_mode`，主窗口创建阶段即崩溃。**v5.19 全版本均无法启动**
- **修复**: 把依赖 widget 的 `_rt_diff = TableDiff(self.realtime_table)` 之外的纯状态字段，全部上移到 `_init_ui()` 之前初始化；`TableDiff` 仍保留在 `_init_ui()` 之后（依赖 `_init_ui` 中创建的 `realtime_table`）
- **提交**: `e41f994`
- **产物**: `dist\GZ_Monitor_v5.19.1_Win7.exe`
- **回归守卫**: 新增 `tests/smoke_main_window.py`，用 `QT_QPA_PLATFORM=offscreen` 无头实例化 `MainWindow`，验证启动不抛 `AttributeError` 且关键属性齐备；可直接 `python tests/smoke_main_window.py` 运行

---

## v5.19（2026-08-11）

### ✨ 新增（三项核心优化）
- **多指标对比（T01+T02）**：预测趋势图参数下拉框改为可勾选 `QListWidget`，支持同时选中并对比多个参数指标；新增 全选 / 反选 / 清空 快捷操作、单轴 / 双轴模式切换、归一化对比按钮
- **图表双轴 + 归一化（`chart_widget.plot_series`）**：支持 `right_series_list` 双 Y 轴与 `normalize` 归一化模式，多指标量级差异下仍可同图对比
- **后台历史拉取（`history_fetch_worker.py` + `refresh_utils.py`）**：新增 `HistoryFetchWorker` 线程与 `TableDiff` 差量更新引擎，按需异步拉取历史数据

### ⚡ 性能（T03-T05）
- **表格差量包裹**：实时表 / 历史表 / 排口列表 / 预测表写入循环外包 `setUpdatesEnabled(False/True)`，减少重绘闪烁与卡顿
- **刷新节流（250ms）**：新增 `_schedule_refresh()` / `_flush_refresh()` 统一入口，用 `QTimer` 单发合并短时间内多次刷新请求，降低 UI 抖动
- **预测定时器解耦**：预测由独立 60s `prediction_timer` 统一触发，移除首屏刷新中的预测调用，避免与数据刷新聚集导致卡顿
- **预测表列重建守卫**：horizon 未变化时不重建列，减少无谓的表格重建开销
- **空状态占位**：实时表无数据参数时显示灰色占位提示（`EMPTY_PLACEHOLDER`），避免空表渲染异常

### 📦 构建
- 打包环境：`C:\Python38`（Python 3.8.10 + PyInstaller 5.13.0）
- 产物：`dist\GZ_Monitor_v5.19_Win7.exe`（约 53 MB）

---

## v5.18.1（2026-08-11）

### 🔧 修复
- **预测趋势图参数下拉框缺失指标**：旧逻辑下拉框只显示"预测结果中出现过的参数"，而预测环节会跳过"最近无有效数据"的参数（`if not raw_values: continue`），导致非甲烷总烃、二氧化硫、氮氧化物、颗粒物、烟气温度等废气参数在下拉框里消失（与是否勾选全部参数无关，只取决于该参数此刻是否有数据）
- 新增 `_get_supported_params_for_visible_subs()`：下拉框改为从"可见排口实际支持的监测项目代码"收集完整参数列表（经 `CODE_TO_NAME` 映射），不再依赖预测结果
- 重写 `_draw_pred_chart_for_param()`：切换未预测参数时先画历史曲线，后台异步按需预测（标题显示"预测生成中…"），完成后自动刷新
- 新增 `_request_on_demand_prediction()` / `_on_ondemand_prediction_done()`：按需单参数预测，不改动用户已选指标、不重建预测表

### 📦 构建
- 打包环境：`C:\Python38`（Python 3.8.10 + PyInstaller 5.13.0）
- 产物：`dist\GZ_Monitor_v5.18.1_Win7.exe`（53 MB）

---

## v5.18（2026-06-21）

### 🔧 修复
- **日/月/季/年历史数据查询**：服务端 `HistoryReport.ashx` 不支持 `index=2`（日）/ `index=3`（月），改用客户端聚合方案 —— 以 `index=1`（小时数据）获取后按 `yyyy-MM-dd` 或 `yyyy-MM` 分组取均值
- 新增 `_aggregate_hour_to_day_month()` 方法，统一处理日/月/季/年聚合

### 📁 项目整理
- 删除 `build/` 目录（1.2 GB 中间产物）
- 删除 17 个旧版本 EXE 和 18 个旧 `.spec` 文件
- `src/` 从 `_internal_win7/` 移至项目根目录
- 清理 `src/gz_thresholds.json` 冗余副本

---

## v5.17（2026-06-07）

### 🔄 回滚
- 回滚至 v5.10 基线，仅保留 GET `HistoryData.aspx` 预热
- 日/月查询仍未修复 → 进入 v5.18 最终方案

---

## v5.16（2026-06-07）⚠️ 已废弃

### ⚠️ 回归
- 修改 `data_processor.py` 的 code 转换逻辑导致实时数据不全
- **此版本已废弃**，不建议使用

---

## v5.15（2026-06-07）

### 🔧 尝试修复
- GET `HistoryData.aspx` 预热 Session
- 清理 codes 参数中的 `.0` 后缀
- 日/月查询仍返回 0 条

---

## v5.14（2026-06-07）

### 🔧 修复
- 日/月查询：添加 `X-Requested-With: XMLHttpRequest` 请求头（ASP.NET AJAX 验证必需）
- `query_history()` 增加 NoneType 防御：`result.get('rows') or []`

---

## v5.13（2026-06-07）

### 🔧 尝试修复
- `_norm_time()` 补全秒位（`00:00` → `00:00:00`），对齐浏览器请求格式
- 日/月查询仍未修复

---

## v5.12（2026-06-07）

### 🔧 修复
- **日志路径 PyInstaller 兼容**：修复 `__file__` 在打包后指向 `_MEIxxxx` 临时目录的问题，改用 `sys.executable` 定位
- 涉及文件：`main.py`、`main_window.py`、`api_client.py`、`multi_account_api.py`

---

## v5.11（2026-06-07）

### 🔧 尝试修复
- 移除日/月查询的日期截断处理
- 未解决日/月查询返回 0 的问题

---

## v5.10（2026-06-07）

### 🔧 修复
- **软件卡滞问题**：`get_all_realtime_data()` 从串行遍历 + sleep 改为 `ThreadPoolExecutor` 并发获取（`max_workers=8`），UI 不再冻结

### ⚡ 性能
- 多企业实时数据并发请求，大幅减少等待时间

---

## v5.9（2026-06-07）

### 🔧 修复
- **多企业登录失败**：增加登录重试机制（`MAX_LOGIN_RETRY=3`），每次重试等待 2 秒
- 密码错误/用户不存在不重试，网络错误/超时/验证码失败自动重试
- 日志写入 `logs/login_debug.log`

---

## v5.8（2026-06-07）

### 🔧 修复
- **历史数据时间优化**：补充历史数据改用分钟数据（`index=-1`），查询范围缩小至 2 小时
- **历史参考标记**：显示具体时间（如 `07:23历史`）替代原来的 `历史参考`

---

## v5.5 — v5.7（2026-06-06 ~ 2026-06-07）

### 🔧 修复
- **"历史参考"标记优化**：发现网站数据是周期性产生（1分钟），增加 GET 页面等待 + 重试机制
- 显示 `hist_latest_time` 对应的时间戳

### ⚡ 新增
- `hist_latest_time` 字典存储每个监测代码对应的最新时间

---

## v5.4（2026-05）

### 🧪 测试版本
- 首个实际测试版本，验证实时数据获取流程

---

## v5.2（2026-04 ~ 2026-05）

### ✅ 功能
- 全部 5 家企业账户登录成功
- 基础实时监测、历史数据查询功能正常

---

## v5.0（2026-03）

### 🎯 初始版本
- GZ 安环监测系统初始构建
- 支持多企业账户登录
- 实时数据监测 + 历史数据查询
- 预警系统（阈值/同值/急剧变化）

---

## 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.8.10 |
| GUI 框架 | PyQt5 |
| 打包工具 | PyInstaller 5.13.0（`--onefile` 模式） |
| 并发 | `concurrent.futures.ThreadPoolExecutor` |
| 目标平台 | Windows 7+ |

## 构建命令

```bash
pip install pyinstaller==5.13.0
pyinstaller --onefile src/main.py --name GZ_Monitor_v5.18_Win7
```

输出：`dist/GZ_Monitor_v5.18_Win7.exe`（约 53 MB）
