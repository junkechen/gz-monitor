# GZ 安环监测 - 移动端（Android APK）

基于电脑端 v5.85 功能的移动端复刻，Flutter 构建，与官网服务端 `http://222.175.25.10:8006` 直连，协议与桌面端完全一致。

## 功能

| 功能 | 说明 |
|---|---|
| 企业登录 | 内置 5 个企业账号，自动完成滑块验证（AES-256-CBC + NCC 缺口求解，同桌面端） |
| 实时数据 | 全部排口实时浓度/限值/超标状态，下拉刷新，超标红色高亮 |
| 历史查询 | 任意排口 × 日/小时粒度 × 日期范围，逐条浓度列表 + **排放量合计** |
| 排放量口径 | 日数据 `ex_` 吨→kg（×1000）与小时数据 `ex_` kg 直读，与官网导出同口径（桌面端 v5.85 修复） |

## 手机端适配

- 竖屏锁定、Material 3 暗色主题（沿用桌面端配色）、中文本地化（日期选择器）
- 底部导航（实时数据 / 历史查询）、卡片式列表替代宽表格、下拉刷新
- 触屏友好的日期选择器与点击目标；`usesCleartextTraffic` 允许 http 明文接口

## 构建与分发

- 产物：`dist/GZ_Monitor_Mobile_v1.0.0.apk`（约 55 MB，直接安装）
- 源码：本目录（`lib/` Dart 代码，`android/` 仅改 label/cleartext/权限）

### 构建步骤（Windows）

```bash
cd mobile
flutter pub get
flutter build apk --release
# 产物 build/app/outputs/flutter-apk/app-release.apk
```

**注意：仓库路径含中文（`新建文件夹`），Gradle/`gen_snapshot` 无法在非 ASCII 路径构建。**
实际构建工作区为 `D:\GZMobile`（ASCII 路径副本）：

```powershell
# 1. 同步源码到 ASCII 工作区
robocopy 'D:\xiaolongxia\新建文件夹\20260328112826\mobile' 'D:\GZMobile' /E /XD build .dart_tool
# 2. 构建
cd D:\GZMobile; flutter build apk --release
# 3. 拷回产物
copy D:\GZMobile\build\app\outputs\flutter-apk\app-release.apk ..\dist\GZ_Monitor_Mobile_v1.0.0.apk
```

已做镜像配置：Gradle wrapper 走腾讯镜像（`gradle-wrapper.properties`），Maven 依赖走阿里云镜像（`settings.gradle.kts` / `build.gradle.kts`）。

## 协议冒烟测试

```bash
cd D:\GZMobile
dart run tool/smoke.dart   # 真实服务端：登录→实时→历史→排放量
```

2026-11-16 实测：鼎鑫账号登录成功；3 个排口实时正常；鼎鑫彩涂4#/彩涂1-3# 日数据吨→kg 合计与官网导出一致。

## 目录

```
lib/core/constants.dart      服务端地址/AES 密钥/账号/代码映射（对齐桌面端 config.py）
lib/core/gz_api.dart         登录(4步)/实时/历史 + 排放量计算（对齐 multi_account_api.py v5.85）
lib/core/slider_solver.dart  滑块 NCC 求解（对齐 slider_solver.py）
lib/pages/                   登录 / 主页 / 实时 / 历史
tool/smoke.dart              全链路冒烟测试
```

## 版本

- v1.0.0（2026-11-16）：首个 APK，对齐桌面端 v5.85 数据口径。
