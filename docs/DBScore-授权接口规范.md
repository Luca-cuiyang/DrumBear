# DB Score 客户端授权接口规范（v1）

> 本文件是 DB Score 桌面客户端与鼓乐熊后端之间的对接约定。
> 由客户端团队（DB Score）制定，后端按本规范实现即可。

## 1. 基本约定

- 生产环境 Base URL：`https://drumbearai.com`
- 所有接口统一使用 HTTPS + JSON，请求头：
  - `Content-Type: application/json`（带 body 的请求必须带）
  - `User-Agent: DBScore/<version> (<platform>)`，其中 `<platform>` 为 `macos` / `windows`
  - 客户端应在请求头带 `X-DBScore-Version: <软件版本号>`，方便后台统计
- 统一响应外壳（所有接口一致）：

```json
{
  "success": true,
  "code": "OK",
  "message": "",
  "data": { }
}
```

字段说明：

- `success`：`true` 表示业务成功，`false` 表示失败（必须）
- `code`：机器可读错误码，成功时为 `"OK"`（必须）
- `message`：给人看的中文错误提示（可选，失败时建议给）
- `data`：业务数据（可选，无数据时省略）

## 2. 错误码（code）

| code | 含义 | 客户端行为 |
|------|------|-----------|
| `OK` | 成功 | 正常处理 |
| `INVALID_CODE` | 激活码不存在 | 提示“激活码无效” |
| `CODE_USED` | 激活码已被使用 | 提示“激活码已被使用”，引导换机解绑 |
| `CODE_REVOKED` | 激活码已被后台停用/作废 | 提示“激活码已失效”，将本地状态置为已过期 |
| `CODE_EXPIRED` | 激活码已过期 | 提示“激活码已过期”，将本地状态置为已过期 |
| `DEVICE_CONFLICT` | 激活码已绑定其他设备 | 提示“该激活码已绑定其他设备，请联系客服解绑” |
| `DEVICE_LIMIT` | 激活设备数超限 | 提示“激活设备数已达上限” |
| `PARAM_ERROR` | 参数缺失或格式错误 | 提示“参数错误，请升级软件后重试” |
| `SERVER_ERROR` | 服务端内部错误 | 提示“服务器繁忙，请稍后重试” |

## 3. 公共数据结构

### 3.1 License（会员授权对象）

```json
{
  "code": "DBSCORE-XXXX-XXXX-XXXX",
  "status": "active",
  "memberType": "standard",
  "durationDays": 365,
  "activatedAt": "2026-10-11T08:00:00.000Z",
  "expireAt": "2027-10-11T08:00:00.000Z",
  "deviceId": "machine-fingerprint-hash",
  "deviceName": "Luca 的 MacBook Pro"
}
```

字段说明：

- `code`：激活码（必须）
- `status`：`active`（有效）/ `expired`（已过期）/ `revoked`（已停用）。客户端只把 `active` 且未过期视为“有效会员”。
- `memberType`：会员类型，当前只用 `standard`（年度会员）。后台如扩展会员档位，客户端按 `memberType != "free"` 判定是否拥有付费权益。
- `durationDays`：授权总天数；`0` 表示永久（后台可选）。
- `activatedAt` / `expireAt`：ISO-8601 UTC 时间字符串（必须）。`expireAt` 为空且 `durationDays == 0` 表示永久。
- `deviceId` / `deviceName`：绑定的设备指纹与设备名，仅激活后的记录会返回。

### 3.2 设备标识（deviceId）

- 客户端在首次运行时生成一个**稳定、不可变**的设备指纹：
  - macOS：基于 `IOPlatformUUID`（硬件 UUID）生成
  - Windows：基于 `MachineGuid`（注册表 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`）生成
- 指纹算法：对上述原始值取小写，去掉连字符后做 SHA-256，取前 32 个十六进制字符。
- 该值跨重启、跨应用更新保持不变；同一台机器重装软件后仍应相同（所以不能使用随机数或应用沙盒路径）。

## 4. 接口列表

### 4.1 激活激活码

`POST /api/dbscore/activate`

请求体：

```json
{
  "code": "DBSCORE-XXXX-XXXX-XXXX",
  "deviceId": "machine-fingerprint-hash",
  "deviceName": "Luca 的 MacBook Pro",
  "appVersion": "4.5.0"
}
```

成功响应：

```json
{
  "success": true,
  "code": "OK",
  "message": "激活成功",
  "data": {
    "license": {
      "code": "DBSCORE-XXXX-XXXX-XXXX",
      "status": "active",
      "memberType": "standard",
      "durationDays": 365,
      "activatedAt": "2026-10-11T08:00:00.000Z",
      "expireAt": "2027-10-11T08:00:00.000Z",
      "deviceId": "machine-fingerprint-hash",
      "deviceName": "Luca 的 MacBook Pro"
    }
  }
}
```

失败响应示例：

```json
{ "success": false, "code": "CODE_USED", "message": "激活码已被使用" }
```

后端规则：

1. 激活码为 `unused` 状态时，校验通过后立即将状态置为 `active`（或后台已有的“已激活”状态）。
2. 记录 `activatedAt`（首次激活时间）、`expireAt`（按 `durationDays` 或后台时长配置计算）。
3. 记录绑定设备：`deviceId` + `deviceName`。
4. 已激活且 `deviceId` 相同，视为同一设备重复激活，直接返回当前 license（幂等，不报错）。
5. 已激活且 `deviceId` 不同，返回 `DEVICE_CONFLICT`（除非后台已对该码执行“换机解绑”）。

### 4.2 查询授权状态

`GET /api/dbscore/license?deviceId=<deviceId>`

成功响应：

```json
{
  "success": true,
  "code": "OK",
  "data": {
    "license": { "……": "同上 License 对象" }
  }
}
```

说明：

- 该接口用于：启动时同步、用户点击“刷新授权”时同步、以及检测后台是否停用/续期。
- 未查询到该设备任何授权时，返回：

```json
{ "success": true, "code": "OK", "data": { "license": null } }
```

客户端收到 `license: null` 时，清除本地会员状态（保留试用期状态）。

### 4.3 授权心跳（可选，建议实现）

`POST /api/dbscore/heartbeat`

请求体：

```json
{
  "code": "DBSCORE-XXXX-XXXX-XXXX",
  "deviceId": "machine-fingerprint-hash",
  "appVersion": "4.5.0"
}
```

成功响应：

```json
{
  "success": true,
  "code": "OK",
  "data": {
    "license": { "……": "同上 License 对象" }
  }
}
```

说明：

- 客户端在**联网状态下每 24 小时**调用一次，用于让后台获得最新在线时间、并同步会员状态变化（续期 / 停用 / 到期）。
- 若返回 `CODE_REVOKED` 或 `CODE_EXPIRED`，客户端立即将本地状态置为“已过期/已停用”，并锁定增值功能。
- 该接口失败（网络错误）不应影响会员状态，客户端使用本地缓存并进入宽限期。

## 5. 客户端本地状态与试用规则（客户端自行实现，后端无需处理）

- **3 天免费试用**由客户端本地计时：首次运行记录时间戳，3 天（72 小时）内拥有全部增值功能。
- 试用结束后，增值功能锁定；基础编辑、排版、PDF 打印永久免费。
- 有效会员（`status == active` 且未过期）永久解锁全部增值功能。
- 离线宽限：当本地已有有效会员缓存但暂时无法联网时，允许继续使用，最长宽限 7 天；超过 7 天仍无法联网校验，则暂停增值功能直到下一次联网校验成功。

## 6. 增值功能锁定范围（客户端判断）

以下三项为会员专属，未激活且试用已结束时锁定：

1. 导入音频并与曲谱 AI 对齐
2. 生成并导出动态 `.dbscore` 工程文件
3. 导出 MP4 视频（无水印）；免费用户导出的 MP4 带“鼓乐熊”水印

基础功能永久免费：新建/编辑乐谱、排版、PDF 打印、文件保存。

## 7. 附：客户端“检查更新”接口（复用现有）

客户端复用已有的 `GET /api/software`（返回 mac/win/arm/intel 最新安装包地址），用于“检查更新”与下载。本规范不新增该接口。
