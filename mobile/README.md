# GZ 安环监测 - 移动端（Android APK）

基于电脑端 v5.85 功能的移动端复刻，Flutter 构建，与官网服务端 `http://222.175.25.10:8006` 直连，协议与桌面端完全一致。

## 功能

| 功能 | 说明 |
|---|---|
| 多账号合并登录 | 内置 5 个企业账号，勾选后一键全部登录（账号间随机 2-5s 间隔防风控，确定性失败跳过重试），多企业数据合并展示 |
| 实时数据 | 全部企业全部排口实时浓度/限值/超标状态，按企业分组展示，下拉刷新 + 60s 自动刷新开关，超标红色高亮 |
| 预警 | 移植桌面端三类规则：**阈值超标**（本地上下限 + 服务端 CBBS 标记）、**同值检测**（废气 30min/废水 180min）、**急剧变化**（急升/急降，10min 去重），底部导航红色角标 + 新预警 SnackBar，预警持久化（重启不丢失，上限 300 条） |
| 预警设置 | **自定义阈值范围**（每参数上下限可改、一键恢复默认）、**声音报警**（系统通知提示音+震动开关）、**后台监测**（前台服务 specialUse，退出 APP 仍每分钟拉数报警）、**微信推送**（Pushplus 群组/单推、Server酱，带测试按钮） |
| 历史查询 | 跨企业任意排口 × 日/小时粒度 × 日期范围，逐条浓度列表 + **排放量合计**（subid 自动路由到对应账号会话） |
| 排放量口径 | 日数据 `ex_` 吨→kg（×1000）与小时数据 `ex_` kg 直读，与官网导出同口径（桌面端 v5.85 修复） |

## 手机端适配

- 竖屏锁定、Material 3 暗色主题（沿用桌面端配色）、中文本地化（日期选择器）
- 底部三导航（实时数据 / 预警 / 历史查询）、卡片式列表替代宽表格、下拉刷新
- 触屏友好的日期选择器与点击目标；`usesCleartextTraffic` 允许 http 明文接口

## 构建与分发

按 ABI 拆分 + 混淆剥离符号，避免 55MB 的全 ABI 胖包。手机只需按架构装对应分包：

| 产物 | 架构 | 体积 | 适用 |
|---|---|---|---|
| `dist/GZ_Monitor_Mobile_v1.4.0_arm64-v8a.apk` | arm64-v8a | 18 MB | **推荐**，2017 年后绝大多数手机 |
| `dist/GZ_Monitor_Mobile_v1.4.0_armeabi-v7a.apk` | armeabi-v7a | 16 MB | 早期 32 位安卓机 |

（x86_64 模拟器包仅调试用，未分发。）最低 Android 7.0（API 24）。
优化手段：① `--split-per-abi` 只打单一架构 native 库；② `--obfuscate --split-debug-info` 混淆 Dart 代码并剥离符号；③ 移除未使用的 cupertino_icons；④ 图标 tree-shaking。相比全 ABI 单包（55.5MB）缩减约 67%。

- 源码：本目录（`lib/` Dart 代码，`android/` 仅改 label/cleartext/权限）

### 构建步骤（Windows）

```bash
cd mobile
flutter pub get
flutter build apk --release --split-per-abi --obfuscate --split-debug-info=build/app/symbols
# 产物 build/app/outputs/flutter-apk/app-{armeabi-v7a,arm64-v8a,x86_64}-release.apk
```

**注意：仓库路径含中文（`新建文件夹`），Gradle/`gen_snapshot` 无法在非 ASCII 路径构建。**
实际构建工作区为 `D:\GZMobile`（ASCII 路径副本）：

```powershell
# 1. 同步源码到 ASCII 工作区
robocopy 'D:\xiaolongxia\新建文件夹\20260328112826\mobile' 'D:\GZMobile' /E /XD build .dart_tool
# 2. 构建（ABI 分包 + 混淆）
cd D:\GZMobile; flutter build apk --release --split-per-abi --obfuscate --split-debug-info=build/app/symbols
# 3. 拷回产物（两个手机架构）
copy D:\GZMobile\build\app\outputs\flutter-apk\app-arm64-v8a-release.apk ..\dist\GZ_Monitor_Mobile_v1.4.0_arm64-v8a.apk
copy D:\GZMobile\build\app\outputs\flutter-apk\app-armeabi-v7a-release.apk ..\dist\GZ_Monitor_Mobile_v1.4.0_armeabi-v7a.apk
```

已做镜像配置：Gradle wrapper 走腾讯镜像（`gradle-wrapper.properties`），Maven 依赖走阿里云镜像（`settings.gradle.kts` / `build.gradle.kts`）。

## 测试

```bash
cd D:\GZMobile
dart run tool/smoke.dart          # 真实服务端：多账号登录→合并实时→跨企业历史→排放量
flutter test test/smoke_test.dart # 预警引擎：超标/同值/急变/去重/持久化（离线）
```

2026-11-16 实测（v1.1.0）：2 账号登录成功；5 排口/2 企业合并正常；跨企业日数据 7 天排放量 13.030 kg；预警引擎 6 项单测全过。
2026-11-28（v1.3.0）：预警引擎 11 项单测全过（含 4 项真实接口参数名回归）；`flutter analyze` 无问题。
2026-11-28（v1.4.0）：14 项单测全过（新增自定义阈值/配置持久化/推送文本 3 项）；`flutter analyze` 0 error。

## 后台监测与微信推送（v1.4.0）

- **后台监测**：`flutter_foreground_task` 前台服务，类型 `specialUse`（避开 Android 15+ `dataSync` 每天 6 小时上限）。后台 isolate 每 60s：按需自动登录（内置账号+自动滑块，会话过期自动重登）→ 合并实时数据 → 预警引擎 → 系统通知 + 微信推送。配置每轮重读，前台改阈值/开关立即生效。需允许通知权限，建议加入电池优化白名单、勿从最近任务划掉 APP。
- **声音报警**：`flutter_local_notifications` 双通知渠道（有声/静默），预警汇总 Inbox 通知，前台后台一致。
- **微信推送**：普通微信群聊无官方机器人接口（第三方 hook 有封号风险，不采用）。走公众号消息提醒通道：
  - **Pushplus（推荐）**：token 单推；填 `topic` 群组码则群推——创建群组后把二维码发到微信群，成员扫码加入，之后每位成员的普通微信都收到「pushplus 推送加」公众号提醒（有提示音）。
  - **Server酱 Turbo**：SendKey 单推到「方糖服务号」。
  - 一批预警合并一条推送（8 条截断 + 超出计数），推送失败不阻断本地预警。

## 目录

```
lib/core/constants.dart      服务端地址/AES 密钥/账号/代码映射/预警阈值（对齐桌面端 config.py）
lib/core/gz_api.dart         登录(4步)/实时/历史 + 排放量计算（对齐 multi_account_api.py v5.85）
lib/core/slider_solver.dart  滑块 NCC 求解（对齐 slider_solver.py）
lib/core/account_manager.dart 多账号会话管理：顺序登录/数据合并/subid 路由
lib/core/warning_engine.dart 预警引擎：超标/同值/急变规则 + 持久化
lib/pages/                   登录 / 主页 / 实时 / 预警 / 历史
tool/smoke.dart              真实服务端全链路冒烟测试（dart run）
test/smoke_test.dart         预警引擎单元测试（flutter test）
```

## 数据来源原则（重要）

- **历史数据**：一律取官网服务端返回的权威字段 `ex_{code}`（日/月为吨→kg、小时为 kg 直读），**禁止本地计算/推导/重算**（官网会对维护/标记数据修正，本地重算会把脏值算进去）。
- **预测/预警**：允许基于已获取的数据做必要计算。
- 与桌面端 v5.89 同口径。

## 版本

- v1.4.0（2026-11-28）：预警设置页上线——**自定义阈值范围**（WarnConfig 持久化，覆盖默认 kWarnThresholds，前台/后台共用）；**声音报警**（系统通知提示音+震动，可关）；**后台监测**（specialUse 前台服务，60s 轮询，自动登录/重登，退出 APP 持续预警）；**微信推送**（Pushplus token/topic 群组推送 + Server酱，配置测试按钮）。新增 3 项单测，共 14 项全过。
- v1.3.0（2026-11-28）：**修复本地预警从未真正生效**（与桌面端 v5.90 同源 bug）：实时接口参数名带单位后缀（`氨氮(mg/L)`、`PH`、`非甲烷总烃(mg/m3)`），与阈值表无单位键不匹配 → 本地阈值/同值/急变检测全部静默跳过（仅剩服务端 CBBS 标记兜底）。新增 `normParamName()` 归一化（code 优先反查 `kCodeToName`，无映射剥括号后缀）；新增 4 项真实参数名回归测试。
- v1.2.0（2026-11-21）：历史排放量改为服务端 `ex_` 权威值直读，去掉 dayEmissionKg 的本地重算回退，加脏数据上限防护；与桌面端 v5.89 数据来源原则一致。
- v1.1.0（2026-11-16）：多账号合并登录与数据合并；新增预警功能（阈值超标/同值检测/急剧变化，角标与持久化）；历史查询跨企业路由；APK 按 ABI 拆分 + 混淆，单包体积 55MB→16~18MB。
- v1.0.0（2026-11-16）：首个 APK，对齐桌面端 v5.85 数据口径。
