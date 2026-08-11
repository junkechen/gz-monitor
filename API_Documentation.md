# GZ 安环监测系统 - API 接口文档

> 基于 GZ_Monitor v5.18 源码提取，服务端：`http://222.175.25.10:8006`

---

## 目录

1. [认证流程](#认证流程)
2. [实时数据接口](#实时数据接口)
3. [历史数据接口](#历史数据接口)
4. [数据字段说明](#数据字段说明)
5. [参数代码映射](#参数代码映射)

---

## 认证流程

### 登录流程（4步）

```
步骤1: GET  /                          获取 ASP.NET_SessionId
步骤2: GET  /ajax/SliderValidImg.ashx?method=GetSliderImg  获取滑块验证码
步骤3: GET  /ajax/SliderValidImg.ashx?method=CheckSliderImg&p={enc_trail}
      遍历 trail=40~200(步长3)，AES加密后提交，Code=0 为验证成功
步骤4: POST /Ajax/Login.ashx?Method=CheckLogin
      参数: p1={enc_user}&p2={enc_pass}&p3={enc_trail2}
```

### AES 加密说明

| 参数 | 值 |
|------|-----|
| 算法 | AES-256-CBC |
| KEY | `1234567890abcdefghijklmnopqrstuv` (32字节) |
| IV | `1234567890abcdef` (16字节) |
| 输出 | Hex 字符串 |

### 登录返回码

| 返回值 | 含义 |
|--------|------|
| `ok` | 登录成功 |
| `errorvalid` | 验证码错误 |
| `errorpassword` | 密码错误 |
| `usernotexist` | 用户不存在 |

---

## 实时数据接口

### 1. 获取企业排口列表

```
POST /Web6/ajax/MonitorControl/Enterprise/EnterPriseRealTimeData.ashx?Method=GetEnterPriseTotalSubs
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Referer: {BASE_URL}/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx
Body: (空)
```

**返回示例：**
```json
[
  {
    "SubId": 12345,
    "SubName": "废水排口1",
    "SubType": 51,
    "EnterPriseId": 1001,
    "EnterPriseName": "山东冠洲股份有限公司"
  }
]
```

---

### 2. 获取实时监测数据

```
POST /Web6/ajax/MonitorControl/Enterprise/EnterPriseRealTimeData.ashx?Method=GetEnterpriseRealtimeData
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Referer: {BASE_URL}/Web6/MonitorControl/Enterprise/EnterPriseRealTimeData.aspx
Body: (空)
```

**返回结构：**
```json
{
  "total": 100,
  "rows": [
    {
      "id": 123,
      "name": "非甲烷总烃",
      "code": "383",
      "value": "9.40",
      "standard": "50.0",
      "iscvt": "1",
      "cvt": "8.50",
      "time": "2026-04-24 10:00:00",
      "status": "1"
    }
  ],
  "sRows": [ /* 同值检测结果 */ ]
}
```

**字段说明：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 监测项ID |
| `name` | string | 监测项名称 |
| `code` | string | 监测项代码 |
| `value` | string | 实测值 |
| `standard` | string | 标准值/告警阈值 |
| `iscvt` | string | 是否折算：`"0"`=否，`"1"`=是 |
| `cvt` | string | 折算值（iscvt="1"时有值） |
| `time` | string | 数据时间 |
| `status` | string | 状态：`"1"`=正常 |

---

## 历史数据接口

### 3. 获取历史数据（分页）

```
POST /ajax/WasteGas/QueryAnalysis/HistoryReportQUIDYN/HistoryReport.ashx
Content-Type: application/x-www-form-urlencoded
Referer: {BASE_URL}/Web6/MonitorControl/Enterprise/HistoryData.aspx
```

**请求参数：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `Method` | string | ✓ | 固定值：`QueryHistoryReport` |
| `subid` | int | ✓ | 排口ID |
| `subtype` | string | ✓ | 排口类型：`51`=废水，`64`=VOCs |
| `index` | int | ✓ | 时间类型：`-1`=分钟，`1`=小时，`2`=日，`3`=月 |
| `start` | string | ✓ | 开始时间，格式：`2026-04-24 00:00` |
| `end` | string | ✓ | 结束时间，格式：`2026-04-24 23:59` |
| `codes` | string | ✓ | 监测项目代码，逗号分隔，如：`"302,311,316"` |
| `sort` | int | | 排序：固定 `1` |
| `showValidate` | int | | 固定 `1` |
| `showUpload` | int | | `0`=实测数据，`1`=折算数据 |
| `selectcity` | int | | 固定 `0` |
| `page` | int | | 页码，默认 `1` |
| `rows` | int | | 每页条数，默认 `1000` |

**返回结构：**
```json
{
  "total": 1440,
  "rows": [
    {
      "time": "2026-04-24 10:00:00",
      "val_302": "7.50",
      "val_311": "2.30",
      "val_316": "45.20",
      "cvt_302": "7.10",
      "standard_302": "9.0"
    }
  ]
}
```

> **注意**：`val_{code}` 为实测值，`cvt_{code}` 为折算值（仅 `showUpload=1` 时返回）

---

### 4. 获取历史查询企业列表

```
GET /Web6/ajax/MonitorControl/Enterprise/historydata.ashx?Method=GetEnterprise&subtype={subtype}&selectcity=0&menuid=2
Referer: {BASE_URL}/Web6/MonitorControl/Enterprise/HistoryData.aspx
```

---

### 5. 获取排口列表（含 itemCode）

```
GET /Web6/ajax/MonitorControl/Enterprise/historydata.ashx?Method=GetSubs&subtype={subtype}&entid={entid}&menuid=2
Referer: {BASE_URL}/Web6/MonitorControl/Enterprise/HistoryData.aspx
```

---

## 数据字段说明

### 排口类型（subtype）

| 值 | 含义 |
|-----|------|
| `51` | 废水 |
| `64` | VOCs（废气/挥发性有机物） |

### 时间类型（index）

| 值 | 含义 | 服务端支持 | 说明 |
|-----|------|-----------|------|
| `-1` | 分钟数据 | ✅ | 用于实时监控 |
| `1` | 小时数据 | ✅ | 用于日报表 |
| `2` | 日数据 | ❌ | **服务端不支持**，v5.18 改用 index=1 客户端聚合 |
| `3` | 月数据 | ❌ | **服务端不支持**，v5.18 改用 index=1 客户端聚合 |

> **v5.18 重要变更**：服务端 `HistoryReport.ashx` 的 `index=2`/`index=3` 始终返回空数据。
> 客户端改用 `index=1`（小时数据）获取后，按 `yyyy-MM-dd` 或 `yyyy-MM` 分组取均值，
> 实现日/月/季/年数据的等效查询。

### showUpload 参数

| 值 | 含义 | 适用场景 |
|-----|------|----------|
| `0` | 实测数据 | 普通企业 |
| `1` | 折算数据 | 热电厂（企业名含"热电"） |

---

## 参数代码映射

### 废气参数（VOCs / 排口类型 64）

| 代码 | 名称 | 单位 | 折算值 |
|------|------|------|--------|
| `201` | 非甲烷总烃 | mg/m³ | 有 |
| `203` | 二氧化硫 | mg/m³ | 有 |
| `207` | 氮氧化物 | mg/m³ | 有 |
| `209` | 烟气含氧量 | % | 无 |
| `210` | 烟气流量 | m³/h | 无 |
| `211` | 流速 | m/s | 无 |
| `220` | 碳氢化合物总烃 | mg/m³ | 无 |
| `299` | 甲烷 | mg/m³ | 无 |
| `525` | 烟气温度 | ℃ | 无 |
| `526` | 烟气压力 | kPa | 无 |
| `527` | 烟气湿度 | % | 无 |

### 废水参数（排口类型 51）

| 代码 | 名称 | 单位 | 折算值 |
|------|------|------|--------|
| `302` | pH值 | 无量纲 | 无 |
| `311` | 氨氮 | mg/L | 无 |
| `316` | 化学需氧量 | mg/L | 无 |
| `492` | 废水流量 | m³/h | 无 |
| `494` | 流量 | m³/h | 无 |
| `495` | 累计流量 | m³ | 无 |
| `301` | 水温 | ℃ | 无 |

---

## 内置企业账户

| 企业名称 | 密码 |
|----------|------|
| 山东冠洲股份有限公司 | `Gzgfah@163.com1` |
| 山东冠洲鼎鑫板材科技有限公司 | `Gzgfah@163.com` |
| 冠县恒润热电有限公司 | `Gzgfah@163.com` |
| 山东冠县冠锌金属材料科技有限公司 | `Gzgfah@163.com` |
| 聊城东舜涂料科技有限公司 | `lCdstl5289099@1` |

---

## 注意事项

1. **AES加密**：所有请求参数（用户名、密码、滑块偏移量）都需要 AES-256-CBC 加密后转 Hex 字符串
2. **Session保持**：登录后使用同一 Session 发起后续请求
3. **Referer校验**：部分接口会校验 Referer 头，需按文档填写
4. **分页获取**：历史数据可能超过1000条，需循环获取（`page=1,2,3...`）
5. **折算数据**：仅热电厂需要使用 `showUpload=1`，其他企业用 `showUpload=0`
6. **时间格式**：`start`/`end` 格式为 `YYYY-MM-DD HH:MM`，注意空格需 URL 编码

---

*文档生成时间：2026-06-21*
*基于 GZ_Monitor v5.18 源码提取*
