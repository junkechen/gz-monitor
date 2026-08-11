# GZ 安环监测系统 — 版本更新日志

## v5.18.1（2026-08-11）✅ 当前版本

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
