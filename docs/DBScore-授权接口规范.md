# DB Score 客户端授权接口规范（v1.3）

> 本文件是 DB Score 桌面客户端与鼓乐熊后端之间的对接约定。
> 由客户端团队（DB Score）制定，后端按本规范实现即可。
>
> **v1.3 变更（2026-10-11 已上线，均为增量、旧客户端不受影响）**
> 1. **激活码绑定账号**：客户端在激活/查询授权时带 `Authorization: Bearer <token>`（登录后拿到的 token），后端会把该激活码绑定到账号并开通会员 → 客户端刷新 `GET /api/user` 即可拿到会员态，**不必再依赖本地激活码缓存**（§4.1）。
> 2. **试用改为服务端计时**：`GET /api/user` 新增 `trialEndAt` / `trialActive` / `trialDaysLeft`，试用期按账号记录、不可本地重置（§5 已改写）。
> 3. License 对象新增可选字段 `source`、`accountBound`（§3.1）。
>
> **v1.4 变更（2026-10-12 已上线，纯增量）**
> 4. **注册/登录来源上报**：软件端调 `/api/auth/register` / `/api/auth/login` 时，请求体加 `"source": "app"`（或确保 UA 带 `DBScore/<version> (<platform>)`、请求头带 `X-DBScore-Version`，规范 §1 本就要求）。这样运营后台「DB Score 用户管理」能把软件端用户单独管理（完整手机号、注册/登录时间、试用与会员状态、登录记录含 IP/平台/版本）。**不带也能正常注册登录**，只是会被归到「网页端用户」。详见《DBScore-个人中心接口-后端实现说明》§11。

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
  "deviceName": "Luca 的 MacBook Pro",
  "source": "manual",
  "accountBound": true
}
```

字段说明：

- `code`：激活码（必须）
- `status`：`active`（有效）/ `expired`（已过期）/ `revoked`（已停用）。客户端只把 `active` 且未过期视为“有效会员”。
- `memberType`：会员类型，当前只用 `standard`（年度会员）。后台如扩展会员档位，客户端按 `memberType != "free"` 判定是否拥有付费权益。
- `durationDays`：授权总天数；`0` 表示永久（后台可选）。
- `activatedAt` / `expireAt`：ISO-8601 UTC 时间字符串（必须）。`expireAt` 为空且 `durationDays == 0` 表示永久。
- `deviceId` / `deviceName`：绑定的设备指纹与设备名，仅激活后的记录会返回。
- `source`（v1.3，可选）：`manual`=客服/线下发放；`purchase`=历史线上购买遗留的码。
- `accountBound`（v1.3，可选）：`true` 表示该激活码**已绑定平台账号**（会员态以账号为准，见 §4.1）。客户端可忽略。

### 3.2 设备标识（deviceId）

- 客户端在首次运行时生成一个**稳定、不可变**的设备指纹：
  - macOS：基于 `IOPlatformUUID`（硬件 UUID）生成
  - Windows：基于 `MachineGuid`（注册表 `HKLM\SOFTWARE\Microsoft\Cryptography\MachineGuid`）生成
- 指纹算法：对上述原始值取小写，去掉连字符后做 SHA-256，取前 32 个十六进制字符。
- 该值跨重启、跨应用更新保持不变；同一台机器重装软件后仍应相同（所以不能使用随机数或应用沙盒路径）。

## 4. 接口列表

### 4.1 激活激活码

`POST /api/dbscore/activate`

请求体（v1.3 参数不变，只需额外带上登录态请求头）：

```json
{
  "code": "DBSCORE-XXXX-XXXX-XXXX",
  "deviceId": "machine-fingerprint-hash",
  "deviceName": "Luca 的 MacBook Pro",
  "appVersion": "5.0.1"
}
```
> 请求头（v1.3 新增，建议带上）：`Authorization: Bearer <token>`（用户登录后由 `/api/auth/login` 返回）。不带也能激活（只绑设备），但**不会开通账号会员**。

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
      "deviceName": "Luca 的 MacBook Pro",
      "accountBound": true
    },
    "memberType": "standard",
    "memberExpireAt": "2027-10-11T08:00:00.000Z",
    "memberAlreadyGranted": false,
    "memberGrantSkipped": null
  }
}
```

`data` 顶层新增字段（v1.3，可选，旧客户端可忽略）：

| 字段 | 说明 |
|---|---|
| `memberType` | 该账号当前会员档位（`standard` / `free`） |
| `memberExpireAt` | 账号会员到期时间；**永久码为 `null`** |
| `memberAlreadyGranted` | `true` = 该码此前已给本账号发过会员，本次未重复顺延（幂等），仅出现于重复激活 |
| `memberGrantSkipped` | `"other_account"` = 该码已绑定**其他账号**，本次不给本账号发放会员 |

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
6. **（v1.3）账号绑定**：请求带 `Authorization` 时，把该码绑定到该账号，并给账号开通会员——`member_type=standard`、`member_expire_at = 激活时间 + durationDays`（已是会员则**在原到期时间上顺延**）；永久码到期时间为 `NULL`。
7. **（v1.3）幂等与防刷**：同一激活码对**同一账号**只发一次，重复激活不顺延；已绑定**其他账号**的码不再给新账号发放会员（`memberGrantSkipped: "other_account"`），绑定关系不被覆盖。
8. **（v1.3）客户端建议**：激活成功后直接重新拉 `GET /api/user` 读取 `memberType` / `memberExpireAt` 展示会员态，激活码只作为设备授权凭证保留。

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

客户端收到 `license: null` 时，清除本地设备授权状态（**会员态请以 `GET /api/user` 为准**，见 §5）。

> **（v1.3）老数据补绑**：若该设备上的激活码是历史遗留、尚未绑定平台账号，则**已登录**时调用本接口（或 `heartbeat`）会自动补绑当前账号并开通会员。客户端无需额外处理，下一次启动/刷新授权即生效。

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

## 5. 试用与会员状态（v1.3：改为**服务端计时**）

**3 天免费试用由服务端计时、按账号记录**（写入 `users.trial_end_at` = 注册时间 + 3 天）。客户端**只读展示**，不做本地计时、不做本地重置。

数据来源：`GET /api/user`（需登录，`Authorization: Bearer <token>`）

```json
{ "user": {
    "id": "uuid", "nickname": "Luca",
    "avatarUrl": "/files/avatars/xxx.png",
    "points": 83805,
    "memberType": "standard",
    "memberExpireAt": "2027-10-11T08:00:00.000Z",
    "trialEndAt": "2026-10-14T08:30:00.000Z",
    "trialActive": true,
    "trialDaysLeft": 3
  } }
```

| 字段 | 说明 |
|---|---|
| `trialEndAt` | 试用截止时间（ISO8601）。新用户注册时 = 注册时间 + 3 天；历史用户按各自注册时间回填（通常已过期） |
| `trialActive` | 服务端判定是否仍在试用期内。**客户端只读，不要自行用 `trialEndAt` 与本地时间比较后覆盖** |
| `trialDaysLeft` | 剩余天数（**向上取整**，已结束为 `0`）。剩余 1.2 天 → `2` |

客户端展示建议：

| 条件 | 展示 |
|---|---|
| `memberType !== "free"` | 正式会员（有效期至 `memberExpireAt`；`memberExpireAt === null` 表示长期有效） |
| `memberType === "free"` 且 `trialActive === true` | 「试用剩余 {trialDaysLeft} 天」 |
| `memberType === "free"` 且 `trialActive === false` | 「免费版」 |

其余规则：

- 试用结束后，增值功能锁定；基础编辑、排版、PDF 打印永久免费。
- **试用不可本地重置**：清缓存、重装软件、换设备都不重新获得试用（服务端按账号判定）。
- 离线宽限：当本地已有有效会员缓存但暂时无法联网时，允许继续使用，最长宽限 7 天；超过 7 天仍无法联网校验，则暂停增值功能直到下一次联网校验成功。

## 6. 增值功能锁定范围（客户端判断）

以下三项为会员专属，未激活且试用已结束时锁定：

1. 导入音频并与曲谱 AI 对齐
2. 生成并导出动态 `.dbscore` 工程文件
3. 导出 MP4 视频（无水印）；免费用户导出的 MP4 带“鼓乐熊”水印

基础功能永久免费：新建/编辑乐谱、排版、PDF 打印、文件保存。

## 7. 附：客户端“检查更新”接口（复用现有）

客户端复用已有的 `GET /api/software`（返回 mac/win/arm/intel 最新安装包地址），用于“检查更新”与下载。本规范不新增该接口。
