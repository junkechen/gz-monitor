# GZ 安环监测 - 移动端（Android APK）

基于电脑端 v5.85 功能的移动端复刻，Flutter 构建，与官网服务端 `http://222.175.25.10:8006` 直连，协议与桌面端完全一致。

## 功能

| 功能 | 说明 |
|---|---|
| 多账号合并登录 | 内置 5 个企业账号，勾选后一键全部登录（账号间随机 2-5s 间隔防风控，确定性失败跳过重试），多企业数据合并展示 |
| 实时数据 | 全部企业全部排口实时浓度/限值/超标状态，按企业分组展示，下拉刷新 + 60s 自动刷新开关，超标红色高亮 |
| 预警 | 移植桌面端三类规则：**阈值超标**（本地上下限 + 服务端 CBBS 标记）、**同值检测**（废气 30min/废水 180min）、**急剧变化**（急升/急降，10min 去重），底部导航红色角标 + 新预警 SnackBar，预警持久化（重启不丢失，上限 300 条） |
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
| `dist/GZ_Monitor_Mobile_v1.1.0_arm64-v8a.apk` | arm64-v8a | 18 MB | **推荐**，2017 年后绝大多数手机 |
| `dist/GZ_Monitor_Mobile_v1.1.0_armeabi-v7a.apk` | armeabi-v7a | 16 MB | 早期 32 位安卓机 |

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
copy D:\GZMobile\build\app\outputs\flutter-apk\app-arm64-v8a-release.apk ..\dist\GZ_Monitor_Mobile_v1.1.0_arm64-v8a.apk
copy D:\GZMobile\build\app\outputs\flutter-apk\app-armeabi-v7a-release.apk ..\dist\GZ_Monitor_Mobile_v1.1.0_armeabi-v7a.apk
```

已做镜像配置：Gradle wrapper 走腾讯镜像（`gradle-wrapper.properties`），Maven 依赖走阿里云镜像（`settings.gradle.kts` / `build.gradle.kts`）。

## 测试

```bash
cd D:\GZMobile
dart run tool/smoke.dart          # 真实服务端：多账号登录→合并实时→跨企业历史→排放量
flutter test test/smoke_test.dart # 预警引擎：超标/同值/急变/去重/持久化（离线）
```

2026-11-16 实测（v1.1.0）：2 账号登录成功；5 排口/2 企业合并正常；跨企业日数据 7 天排放量 13.030 kg；预警引擎 6 项单测全过。

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

## 版本

- v1.1.0（2026-11-16）：多账号合并登录与数据合并；新增预警功能（阈值超标/同值检测/急剧变化，角标与持久化）；历史查询跨企业路由；APK 按 ABI 拆分 + 混淆，单包体积 55MB→16~18MB。
- v1.0.0（2026-11-16）：首个 APK，对齐桌面端 v5.85 数据口径。
