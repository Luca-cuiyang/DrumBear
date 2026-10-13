# DB Score 个人中心接口 —— 后端实现说明（v1.4）

> 对应需求文档：《DBScore-个人中心后端接口需求.md》
> 实现方：鼓乐熊 AI 后端（workbuddy）
> 上线状态：**已上线生产** `https://drumbearai.com`（2026-10-11），8 大模块 21 个端点全部可用
> v1.1 追加：**§9 软件更新接口**（version / notes 字段 + 检查更新）；§10 原「待确认问题」已全部由产品确认闭环
> v1.2 追加：**会员开通双链路改造**（§8.3）——线上购买**支付后直接开通账号会员，不再发激活码**；激活码仅用于线下/抖音/视频号渠道；`/api/user` 新增 **`avatarUrl`** 字段（§8.2）
> v1.3 追加（2026-10-11 已上线生产）：**注册即赠 3 天试用**（§8.2 `trialEndAt`/`trialActive`/`trialDaysLeft`）；**激活码绑定账号**（§8.4）——带 `Authorization: Bearer <token>` 激活时，把激活码绑到该账号并开通会员，客户端刷新 `/api/user` 即见会员态，不再依赖本地激活码缓存
> v1.4 追加（2026-10-12 已上线生产）：**注册/登录来源识别**（软件端 app / 网页版 web，§11）——客户端按 §11.4 上报标识后，运营后台新增的「DB Score 用户管理」（入口在「DB Score 会员管理」下面）即可把软件端用户单独管理：完整手机号、注册/登录时间、会员与试用状态、邀请码、登录记录（IP / 平台 / 版本）
> 本文档面向客户端团队，说明**实际实现的请求/响应契约**，并标出**与需求文档的 3 处偏差**（需客户端配合）。

---

## 1. 通用约定

| 项 | 约定 |
|---|---|
| Base URL | `https://drumbearai.com` |
| 鉴权 | `Authorization: Bearer <token>`（同时兼容 `X-Auth-Token` / cookie `audio_token`） |
| 未登录 | **HTTP 401** + `{ "success": false, "code": "LOGIN_REQUIRED", "error": "请先登录" }` |
| 业务失败 | **HTTP 200** + `{ "success": false, "code": "XXX", "error": "中文提示" }` |
| 成功 | `{ "success": true, "code": "OK", "message": "", "data": { ... } }` |
| 金额单位 | 一律「分」，字段名以 `Cents` 结尾（`amountCents` / `commissionBalanceCents` / `totalEarnedCents`） |
| 分页 | 请求 `?page=1&pageSize=20`（`pageSize` 上限 100，超出自动收敛）；响应 `data.page / data.pageSize / data.total / data.list` |
| 时间格式 | ISO-8601 UTC 字符串，如 `2026-10-11T10:17:38.383Z` |
| 请求体 | `Content-Type: application/json`；文件上传用 `multipart/form-data` |

**关于 HTTP 状态码**：只有「未登录」用 401、「参数非法」在极少数老接口用 400。业务层错误一律 200 + `code`，客户端判定请**以 `success` / `code` 为准，不要只看 HTTP 状态码**。

---

## 2. 错误码表（完整）

| code | HTTP | 含义 | 客户端建议行为 |
|---|---|---|---|
| `OK` | 200 | 成功 | 正常处理 `data` |
| `LOGIN_REQUIRED` | 401 | 未登录 / token 失效 | 清本地 token，跳登录页 |
| `PARAM_ERROR` | 200 | 参数缺失或格式错误 | 提示 `error` 原文 |
| `NOT_FOUND` | 200 | 记录不存在（或不属于当前账号） | 刷新列表 |
| `FILE_NOT_FOUND` | 200 | 云端文件已丢失/失效 | 提示重新上传 |
| `UPLOAD_FAILED` | 200 | 上传失败（含超大文件） | 提示 `error` 原文 |
| `QUOTA_EXCEEDED` | 200 | 云备份空间不足（每人 2GB） | 提示先删除旧备份 |
| `INSUFFICIENT_BALANCE` | 200 | 可提现佣金余额不足 | 提示 `error` 原文 |
| `ALREADY_CHECKED_IN` | 200 | 今日已签到 | 按钮置灰 |

> 授权相关错误码（`INVALID_CODE` / `CODE_USED` / `DEVICE_CONFLICT` 等）见《DBScore-授权接口规范.md》，本文档不含。

---

## 3. 接口总览

| # | 模块 | 方法 | 路径 | 需登录 |
|---|---|---|---|---|
| 1.1 | 推广赚佣 | GET | `/api/invite` | ✅ |
| 1.2 | | GET | `/api/commission/records` | ✅ |
| 1.3 | | POST | `/api/commission/withdraw` | ✅ |
| 1.4 | | GET | `/api/commission/withdrawals` | ✅ |
| 2.1 | 订单 | GET | `/api/orders` | ✅ |
| 3.1 | 积分 | GET | `/api/points` | ✅ |
| 3.2 | | POST | `/api/points/checkin` | ✅ |
| 3.3 | | GET | `/api/points/records` | ✅ |
| 4.1 | 我的乐谱 | GET | `/api/scores` | ✅ |
| 4.2 | | POST | `/api/scores` | ✅ |
| 4.2b | | POST | `/api/scores/upload`（multipart，附加能力）| ✅ |
| 4.3 | | DELETE | `/api/scores/{id}` | ✅ |
| 4.4 | | PATCH | `/api/scores/{id}/visibility` | ✅ |
| 5.1 | 我的工程 | POST | `/api/projects/upload` | ✅ |
| 5.2 | | GET | `/api/projects` | ✅ |
| 5.3 | | GET | `/api/projects/{id}/download` | ✅ |
| 5.4 | | DELETE | `/api/projects/{id}` | ✅ |
| 6.1 | 反馈 | POST | `/api/feedback` | ✅ |
| 7.1 | 通知 | GET | `/api/notifications` | ✅ |
| 7.2 | | POST | `/api/notifications/{id}/read` | ✅ |
| 8.1 | 会员 | POST | `/api/membership/subscribe`（补偿入口）| ✅ |
| 8.2 | | GET | `/api/user`（登录态查询）| ✅ |

---

## 4. 逐模块接口说明

### 一、推广赚佣（佣金 15%）

#### 1.1 `GET /api/invite` — 我的推广信息

```json
{
  "success": true, "code": "OK", "message": "",
  "data": {
    "inviteCode": "MAXTANSU",
    "inviteUrl": "https://www.drumbearai.com/?invite=MAXTANSU",
    "commissionBalanceCents": 2985,
    "totalEarnedCents": 5970,
    "inviteeCount": 2,
    "paidInviteeCount": 1,
    "commissionRate": 0.15
  }
}
```

字段说明：
- `commissionBalanceCents`：**可提现余额**（分）= 累计赚取 − 已申请提现（含待打款/已打款；被驳回的不占额度）
- `totalEarnedCents`：**累计赚取**（分），只增不减
- `inviteeCount`：邀请注册人数；`paidInviteeCount`：其中已产生已支付订单的人数
- `commissionRate`：当前佣金比例，固定 `0.15`（便于客户端展示，不要写死）

> 兼容说明：为兼容网页版/小程序，响应顶层**额外**冗余 `inviteCode` / `inviteUrl` / `commissionTotal` / `commissionBalance` / `invitedUsers`。桌面端只用 `data` 即可。

#### 1.2 `GET /api/commission/records?page=1&pageSize=20`

```json
{
  "success": true, "code": "OK", "message": "",
  "data": {
    "page": 1, "pageSize": 20, "total": 1,
    "list": [
      {
        "id": 1,
        "recordNo": "8f3c...-uuid",
        "amountCents": 2985,
        "type": "invite_reward",
        "sourceNickname": "138****8888",
        "remark": "好友 138****8888 购买 DB Score 年卡返佣",
        "createdAt": "2026-10-11T10:17:38.383Z"
      }
    ]
  }
}
```
- `id`：页内序号；`recordNo`：真实记录 id（稳定，**去重用这个**）
- `sourceNickname`：优先返回好友手机号掩码（`138****8888`），无手机号时返回昵称，再兜底「好友」

#### 1.3 `POST /api/commission/withdraw` — 申请提现

请求：`{ "amountCents": 2985 }`（可选再传 `wechatAccount` / `phone` 覆盖收款信息）

成功：`{ "success": true, "code": "OK", "message": "提现申请已提交...", "data": { "withdrawalId": "uuid" } }`

业务规则：
- 最低 **¥1（100 分）**，低于则 `PARAM_ERROR`「提现金额需不低于 ¥1」
- 超出可提现余额 → `INSUFFICIENT_BALANCE`，`error` 含当前可提现额，如「可提现余额不足（当前可提现 ¥19.85）」
- 账号无手机号且未传 `wechatAccount` / `phone` → `PARAM_ERROR`「请填写微信收款账号或联系手机号」（打款需要）
- 成功后自动写入一条站内通知

#### 1.4 `GET /api/commission/withdrawals?page=1&pageSize=20`

```json
{
  "success": true, "code": "OK", "message": "",
  "data": {
    "page": 1, "pageSize": 20, "total": 1,
    "list": [
      { "id": 1, "withdrawalNo": "uuid", "amountCents": 1000,
        "status": "paid", "createdAt": "2026-10-11T10:21:59.566Z" }
    ]
  }
}
```
- `status`：`pending`（待审核）/ `paid`（已打款）/ `rejected`（已驳回）
- `id` 页内序号、`withdrawalNo` 真实 id

---

### 二、订单记录

#### 2.1 `GET /api/orders?page=1&pageSize=20`

```json
{
  "success": true, "code": "OK", "message": "",
  "data": {
    "page": 1, "pageSize": 20, "total": 3,
    "list": [
      {
        "id": 1,
        "orderNo": "DB1731234567890123",
        "type": "dbscore_membership",
        "planId": "yearly",
        "planName": "年度会员",
        "amountCents": 19900,
        "status": "paid",
        "createdAt": "2026-10-11T10:15:00.000Z",
        "paidAt": "2026-10-11T10:17:38.383Z"
      }
    ]
  }
}
```
- `status`：`pending` / `paid` / `cancelled`
- `paidAt`：权益实际发放时间（未支付为 `null`）
- `type`：`recharge` 积分充值 / `membership` 平台会员 / `dbscore_membership` **DB Score 年卡**
- ⚠️ **`id` 是页内序号，不是订单号**。订单稳定标识用 `orderNo`（见 §6 偏差说明）

---

### 三、积分中心

#### 3.1 `GET /api/points`

```json
{ "success": true, "code": "OK", "data": {
    "balance": 83805, "todayCheckedIn": false,
    "signupBonus": 500, "checkinReward": 5
} }
```
`signupBonus` / `checkinReward` 为附赠字段，客户端可用于展示「注册送 X 分、每日签到 +Y 分」。

#### 3.2 `POST /api/points/checkin`

成功：`{ "success": true, "code": "OK", "data": { "balance": 83810, "reward": 5 } }`

重复签到：`{ "success": false, "code": "ALREADY_CHECKED_IN", "error": "今天已经签到过了", "data": { "balance": 83805, "reward": 0 } }`
（该响应同时保留旧字段 `points` / `balance` / `message` 兼容网页版）

#### 3.3 `GET /api/points/records?page=1&pageSize=20`

```json
{ "success": true, "code": "OK", "data": {
  "page": 1, "pageSize": 20, "total": 42, "balance": 83805,
  "list": [
    { "id": 1, "recordNo": "uuid", "amount": -20, "balanceAfter": 83805,
      "type": "consume", "remark": "歌词创作", "createdAt": "..." }
  ]
} }
```
`type` 取值：`checkin` 签到 / `recharge` 充值 / `reward` 奖励返佣 / `refund` 退款 / `consume` 消耗。
`amount` 为带符号整数（正数入账、负数消耗）。

---

### 四、我的乐谱（云端）

配额：**单文件 ≤ 50MB**。可见性 `public` / `private`（默认 `private`）。

#### 4.1 `GET /api/scores?page=1&pageSize=20`

```json
{ "success": true, "code": "OK", "data": {
  "page": 1, "pageSize": 20, "total": 2,
  "list": [
    { "id": "9f2c-uuid", "seq": 1, "title": "我的作品",
      "coverUrl": "", "fileUrl": "/files/cloud-scores/xxx.dbscore",
      "fileName": "我的作品.dbscore", "size": 20480,
      "visibility": "private", "createdAt": "...", "updatedAt": "..." }
  ]
} }
```
标题、可见性、大小、文件名均按实际入库值返回，`coverUrl` 暂为空串（预留）。

#### 4.2 `POST /api/scores` — 登记乐谱（JSON）

请求：`{ "title": "作品名", "fileUrl": "/files/... 或 外部地址", "visibility": "public" }`
成功：`{ "success": true, "code": "OK", "message": "已保存到云端", "data": { "id": "...", "title": "...", "fileUrl": "...", "visibility": "private", "updatedAt": "..." } }`

规则：`title`（≤120 字）与 `fileUrl` 必填；`fileUrl` 为本站 `/files/` 地址时会校验文件真实存在，否则 `FILE_NOT_FOUND`。

#### 4.2b `POST /api/scores/upload` — 直接上传乐谱文件（本次新增，推荐客户端用）

`multipart/form-data`，字段：`file`（必填）、`title`（可选，默认取文件名）、`visibility`（可选）。
成功：`data` 含 `id / title / fileUrl / size / visibility / updatedAt`。文件超 50MB → `UPLOAD_FAILED`「文件过大（乐谱单文件上限 50MB）」。

#### 4.3 `DELETE /api/scores/{id}`
成功：`{ "success": true, "code": "OK", "message": "已删除", "data": { "deleted": true, "id": "..." } }`
删除时仅当无其他记录引用同一文件才删除磁盘文件。

#### 4.4 `PATCH /api/scores/{id}/visibility`
请求：`{ "visibility": "private" }`；非 `public`/`private` → `PARAM_ERROR`。
成功：`{ "success": true, "code": "OK", "message": "已设为私密", "data": { "id": "...", "visibility": "private" } }`

---

### 五、我的工程（云备份）

配额：**单文件 ≤ 200MB，每人合计 ≤ 2GB**。

#### 5.1 `POST /api/projects/upload`
`multipart/form-data`，字段名 `file`。
成功：
```json
{ "success": true, "code": "OK", "message": "已备份到云端",
  "data": { "id": "uuid", "name": "xxx.dbscore", "size": 1234567,
            "createdAt": "...", "updatedAt": "...",
            "usedBytes": 1234567, "quotaBytes": 2147483648 } }
```
失败：
- 单文件超 200MB → `UPLOAD_FAILED`「文件过大（工程单文件上限 200MB）」
- 超出总配额 → `QUOTA_EXCEEDED`「云备份空间不足（已用 xxMB / 上限 2048MB），请先删除旧备份」（此时已自动清理临时文件，不占空间）

#### 5.2 `GET /api/projects?page=1&pageSize=20`
```json
{ "success": true, "code": "OK", "data": {
  "page": 1, "pageSize": 20, "total": 1,
  "usedBytes": 1234567, "quotaBytes": 2147483648,
  "list": [ { "id": "uuid", "seq": 1, "name": "xxx.dbscore", "size": 1234567,
              "createdAt": "...", "updatedAt": "..." } ] } }
```
`usedBytes` / `quotaBytes` 可**直接用于渲染「已用 1.2MB / 2GB」进度条**。

#### 5.3 `GET /api/projects/{id}/download`
返回**文件流**（`Content-Type: application/octet-stream`，`Content-Disposition: attachment`）。
注意：本接口**不返回 JSON 外壳**，成功即二进制；失败才返回 JSON（`NOT_FOUND` / `FILE_NOT_FOUND`）。客户端需按 `Content-Type` 分支处理。

#### 5.4 `DELETE /api/projects/{id}`
成功：`data = { deleted: true, id, usedBytes, quotaBytes }`（返回删除后的最新占用量，便于直接刷新进度条）

---

### 六、意见反馈

#### 6.1 `POST /api/feedback`
请求：`{ "content": "反馈内容", "contact": "选填联系方式" }`
成功：`{ "success": true, "code": "OK", "message": "反馈已提交，感谢你的建议", "data": { "submitted": true } }`
校验：`content` 必填且 ≤2000 字；`contact` ≤100 字。

---

### 七、通知中心

#### 7.1 `GET /api/notifications?page=1&pageSize=20`
```json
{ "success": true, "code": "OK", "data": {
  "page": 1, "pageSize": 20, "total": 5, "unread": 2,
  "list": [
    { "id": 1, "noticeNo": "uuid", "title": "DB Score 年卡开通成功",
      "content": "你的账号已成为正式会员，有效期至 2027-10-11。在 DB Score 软件内用同一手机号登录即可使用全部功能。",
      "type": "order", "createdAt": "...", "read": false }
  ] } }
```
- 多返回 `unread` 字段，可直接做小红点
- `type` 常见值：`order` 订单 / `commission` 佣金 / `system` 系统 / `points` 积分

#### 7.2 `POST /api/notifications/{id}/read`
`{id}` 可传**真实通知 id（`noticeNo`）**，也可传**列表序号（`id`）**，两种都支持。
成功：`{ "success": true, "code": "OK", "message": "已标记为已读", "data": { "id": "1" } }`
不存在：`NOT_FOUND`

---

### 八、会员购买与发放（重点）

#### 8.0 真实链路（唯一开通路径）

```
客户端/网页下单  POST /api/pay/wechat/create  { type:"membership", planId:"yearly" }
        ↓  返回 { codeUrl, outTradeNo, qrDataUrl }
用户微信扫码支付
        ↓
微信回调         POST /api/pay/wechat/notify  （服务端验签，无需客户端参与）
        ↓  订单置 paid → 自动发放权益（幂等）
客户端轮询       GET /api/user   或   GET /api/orders   → 看到 memberType=standard
```

#### 8.0.1 下单参数（DB Score 年卡）

`POST /api/pay/wechat/create`（需登录）
```json
{ "type": "membership", "planId": "yearly" }
```
- `planId=yearly` 是 **DB Score 制谱大师年卡**：名称「年度会员」、价格 **19900 分（¥199）**、时长 **365 天**
- 服务端自动识别为 `type=dbscore_membership` 订单，**不含平台积分/平台会员权益**（平台会员为 `monthly`，¥99/30 天，逻辑完全独立）
- 响应：`{ "success": true, "codeUrl": "weixin://wxpay/...", "outTradeNo": "DB...", "qrDataUrl": "data:image/png;base64,..." }`
- 支付状态查询：`GET /api/pay/wechat/status/{outTradeNo}`（需登录）

#### 8.1 `POST /api/membership/subscribe` — 补偿入口（不是开通接口）

**该接口已被改造为「支付已完成但权益未到账」的手动补偿入口**，直接裸调不再能开通会员。

请求：`{ "orderId": "<outTradeNo>" }`（`outTradeNo` 亦可）
必须同时满足，否则被拒：
1. 已登录（`Authorization: Bearer <token>`）
2. 携带订单号 → 否则 `400 ORDER_REQUIRED`「会员开通必须完成微信支付，请先下单支付（缺少订单号）」
3. 订单属于**当前账号** → 否则 `400`「订单不属于当前账号」
4. 订单状态为 `paid`（真实支付过）→ 否则 `400`「订单尚未支付完成」
5. `payment_orders.fulfilled_at` 为空（未发放过）→ 否则返回「权益已发放，无需重复操作」且**不重复发放**

成功（DB Score 年卡，v1.2 起）：
```json
{ "success": true, "message": "会员已开通",
  "memberType": "standard",
  "memberExpireAt": "2027-10-11T10:53:07.120Z",
  "commissionCents": 2985 }
```
> 重复调用（`fulfilled_at` 已写入）返回 `{ "success": true, "alreadyFulfilled": true, ... }`，会员期**不会**被重复顺延。

#### 8.2 `GET /api/user`（需登录）— 桌面端登录态/会员态查询

```json
{ "user": {
    "id": "uuid", "nickname": "Luca",
    "avatarUrl": "/files/avatars/1791xxx.png",
    "points": 83805,
    "memberType": "standard",
    "memberExpireAt": "2027-10-11T10:17:38.383Z",
    "currentPlanId": "yearly",
    "inviteCode": "MAXTANSU",
    "commercialRights": false,
    "phone": "13800001111",
    "role": "user",
    "trialEndAt": "2026-10-14T08:30:00.000Z",
    "trialActive": true,
    "trialDaysLeft": 3
  },
  "pointsCost": { "lyrics": 20, "lyricCheck": 10, "songCheck": 20, "voiceClone": 100 }
}
```
- **`avatarUrl`（v1.2 新增）**：用户头像地址；**未上传时为空字符串 `""`**，客户端此时显示昵称首字占位（客户端已做好兼容）。有值时为站内 `/files/avatars/...` 路径（拼在 Base URL 后访问）
- 头像上传走网页端个人中心（`POST /api/user/avatar`，multipart 字段 `file`，jpg/png/webp/gif ≤5MB；`DELETE /api/user/avatar` 恢复默认），桌面端**无需实现上传**，只读 `avatarUrl` 展示即可
- **注册即赠 3 天试用（v1.3 新增）**：
  | 字段 | 说明 |
  |---|---|
  | `trialEndAt` | 试用截止时间（ISO8601）。**新用户注册时 = 注册时间 + 3 天**（写入 `users.trial_end_at`）；历史用户已按各自注册时间回填，通常早已过期 |
  | `trialActive` | 服务端判定当前是否仍在试用期内（`trialEndAt > now`）。**客户端只读展示，不要本地计算/缓存** |
  | `trialDaysLeft` | 试用剩余天数（**向上取整**，已结束返回 `0`）。例如剩余 1.2 天 → `2` |
  - 建议展示：`trialActive === true` → 显示「试用剩余 {trialDaysLeft} 天」；`trialActive === false` 且 `memberType === 'free'` → 显示「免费版」；`memberType !== 'free'`（付费/激活码会员）→ 显示会员有效期
  - **试用必须按账号记录，客户端不可本地重置**：服务端以 `users.trial_end_at` 为准，客户端清缓存/重装不会重新获得试用
未登录：**HTTP 401** `{ "error": "请先登录", "code": "LOGIN_REQUIRED" }`（已彻底关闭「未登录回退本地演示用户」的旧行为）

**发放规则（由微信支付回调触发，严格按此执行，v1.2 起）**：
| 动作 | 结果 |
|---|---|
| `users.member_type` | 置为 `standard` |
| `users.member_expire_at` | 支付成功时间 + **365 天**（若已是会员则**在原到期时间上顺延**，不缩短用户已有权益） |
| `payment_orders.status` | `paid`；同时写 `fulfilled_at`（幂等标记） |
| ~~激活码~~ | **不再生成、不再发放**（v1.2 起线上购买直接开通账号会员） |
| 站内通知 | 买家收到「DB Score 年卡开通成功」（含到期日与「用同一手机号登录软件」指引，**不含激活码**） |
| **邀请人佣金** | 若买家有 `inviter_id`，按其**实付金额 × 15%** 记现金佣金（¥199 → **2985 分**），并通知邀请人 |

> ⚠️ 适用范围（按产品确认）：**上述「15% 现金佣金」与「memberType 置为 standard」仅对 ¥199 DB Score 年卡生效**。平台会员订阅（`monthly` 等 `scope=platform` 的套餐）逻辑保持不变，不参与返佣。

#### 8.3 会员开通双链路（v1.2 改造，重要）

¥199 年卡现在有**两条互不影响**的开通路径：

| 路径 | 入口 | 流程 | 客户端看到的 |
|---|---|---|---|
| **线上购买**（手机号登录） | 软件内登录手机号 → 点「开通会员」→ 跳 `https://drumbearai.com/membership?plan=yearly` → 微信扫码支付 | 支付回调直接把**该手机号账号**升级为会员（`member_type=standard`、`member_expire_at=+365天`），生成 `status=paid` 订单，**不发激活码** | `GET /api/user` 看到 `memberType/memberExpireAt`；`GET /api/orders` 看到订单 |
| **线下 / 抖音 / 视频号** | 后台手动生成激活码发给用户 | 用户在软件里输入激活码 → 走现有 `POST /api/dbscore/activate`（**接口与请求参数不变**） | `/api/dbscore/license` 看到授权状态；**v1.3 起：若请求已登录（带 token），该码同时绑定到账号并开通会员**，`/api/user` 也可见会员态（详见 §8.4） |

- 网页端会员页 `/membership?plan=yearly` 已按此改造：已开通显示「已是正式会员 + 有效期至 X + 用手机号登录软件」；未开通显示「立即购买年卡 · 付款后自动开通，无需激活码」
- 「我的激活码」列表（网页个人中心 / 软件内）只展示**线下渠道**的码；历史 `source=purchase` 的码标注「线上购买（历史）」
- 软件端 `POST /api/dbscore/activate`、`GET /api/dbscore/license`、`heartbeat` 契约**完全不变**；DTO 新增可选 `source` 字段（`manual`=客服发放 / `purchase`=历史线上购买），纯增量、旧客户端不受影响

#### 8.4 激活码绑定账号（v1.3 改造，重要）

**背景**：以前激活码只按「设备」绑定，客户端靠本地缓存的激活码判断会员态；用户重装/换机或换账号后状态容易错乱。v1.3 起激活码**同时绑定账号**，会员态回归账号维度。

**触发条件**：客户端在激活/查询授权时带上登录态（`Authorization: Bearer <token>`，与其它个人中心接口一致）。请求参数**无需新增**，仍是 `code` + `deviceId`。

| 接口 | 行为（v1.3） |
|---|---|
| `POST /api/dbscore/activate` | 先按原逻辑绑定/校验设备；**若已登录** → 把该激活码绑定到 `token` 对应账号，并给该账号开通会员 |
| `GET /api/dbscore/license` | 已登录时对**历史未绑账号的老码**做一次性补绑（老用户升级客户端后自动生效） |
| `POST /api/dbscore/heartbeat` / `verify` | 同上，已登录时补绑 |
| 未登录调用 | **行为完全不变**：只绑设备、不开会员（兼容老客户端） |

**开通规则（与线上购买一致）**：
| 项目 | 结果 |
|---|---|
| `users.member_type` | 置为 `standard`（`member_type` 由激活码携带，默认 standard） |
| `users.member_expire_at` | 激活时间 + `durationDays`（标准年卡 = **365 天**）；**已是会员则在原到期时间上顺延**，不缩短已有权益 |
| 永久码（`durationDays = 0`） | `member_expire_at` 置为 `NULL`，表示长期有效 |
| 激活码记录 | 写 `bound_user_id`（绑定账号）+ `account_granted_at`（发放时间） |
| 订阅记录 | 写一条 `subscriptions`（`plan_id = yearly`） |
| 站内通知 | 走原有激活通知逻辑 |

**`/api/dbscore/activate` 响应新增字段（均为可选增量，旧客户端忽略即可）**：
```json
{ "success": true, "code": "OK", "message": "激活成功",
  "data": {
    "license": { "code": "DBSCORE-XXXX-XXXX-XXXX", "status": "active",
                 "durationDays": 365, "expireAt": "2027-10-11T08:30:00.000Z",
                 "source": "manual", "accountBound": true,
                 "deviceId": "...", "deviceName": "..." },
    "memberType": "standard",              // 账号会员档位
    "memberExpireAt": "2027-10-11T08:30:00.000Z",  // 账号会员到期（永久码为 null）
    "memberAlreadyGranted": true,          // 可选：该码此前已给本账号发过，本次未重复顺延（幂等）
    "memberGrantSkipped": "other_account"  // 可选：该码已绑定其他账号，本次不发放会员
  } }
```

**幂等与防刷（服务端强约束）**：
| 场景 | 表现 |
|---|---|
| 同码 + 同账号**重复激活** | 接口仍返回成功，但不重复顺延会员期，响应带 `memberAlreadyGranted: true` |
| 同码**换设备**激活（未解绑） | 按原逻辑拒绝：`success:false`、`code: "DEVICE_CONFLICT"`（「该激活码已绑定其他设备，请联系客服解绑」） |
| 同码已绑**账号 A**，账号 B 登录后激活 | 若设备已解绑导致激活能过，会员**不发放给 B**，响应带 `memberGrantSkipped: "other_account"`，`bound_user_id` 不被覆盖（防一码多开） |
| 后台解绑设备后换机 | 设备重新绑定；账号绑定关系**保留**，会员期不变 |

> **客户端建议**：激活成功后不必再缓存激活码用于判断会员态，直接重新拉 `GET /api/user` 读 `memberType` / `memberExpireAt` 展示即可；激活码仅作为「设备授权凭证」保留。

> **注意**：v1.3 部署时已为历史用户回填 `users.trial_end_at`（= 各自注册时间 + 3 天，因此**老用户基本都已过期**，显示为免费版属预期）。

---

## 5. 关键设计说明

### 5.1 幂等（防止重复发放 / 重复返佣）

| 场景 | 机制 |
|---|---|
| 微信回调重试 | `payment_orders.fulfilled_at` CAS 空写入：第二次回调直接跳过，不再开通会员/发佣金 |
| 回调 + 补偿接口并发 | 同上，共用一个 `fulfillDbScoreMembership()` 发放函数 |
| 同一订单重复返佣 | `commissions.order_no` 唯一索引 + `INSERT OR IGNORE` |
| 同一订单重复开通会员 | `fulfilled_at` 幂等：重复调用返回 `alreadyFulfilled:true`，会员期不重复顺延（线上实测 ✅） |

### 5.2 「未登录即拒绝」

全部 21 个端点均挂登录校验中间件，未登录统一 401 + `LOGIN_REQUIRED`。
生产环境已关闭历史遗留的 `local-user` 兜底逻辑（旧行为：未登录自动当成本地演示账号，会造成数据串号与白嫖风险）。

### 5.3 提现状态一致性（本轮修复）

历史后台审核写入的状态是 `approved`，与客户端规范的 `paid` 不一致，且未计入「已占用提现额度」，理论上可被重复申请。
本轮已统一：**`pending` / `paid` / `rejected`** 三个值。
- 启动迁移：历史 `approved` → `paid`（已在生产执行，生产原无历史数据，零影响）
- 后台审核接口同时接受 `paid` 与旧值 `approved`（后者自动归一为 `paid`）
- 额度计算同时认 `pending` / `paid` / `approved`（防御历史脏数据）
- 后台提现列表新增 `paid` 状态标签

---

## 6. ⚠️ 与需求文档的偏差（需客户端配合，共 3 处）

### 偏差 1：列表项的 `id` 是「页内序号」，不是数据库主键

需求文档中多处示例把 `id` 写作 `1、2、3…`。为同时满足「示例形状」与「数据可定位」，实现如下：

| 接口 | `id` | 稳定标识字段 |
|---|---|---|
| `/api/commission/records` | 页内序号 | **`recordNo`** |
| `/api/commission/withdrawals` | 页内序号 | **`withdrawalNo`** |
| `/api/orders` | 页内序号 | **`orderNo`** |
| `/api/points/records` | 页内序号 | **`recordNo`** |
| `/api/notifications` | 页内序号 | **`noticeNo`** |
| `/api/scores` | **真实主键（uuid 字符串）** | — |
| `/api/projects` | **真实主键（uuid 字符串）** | — |

**客户端要做的**：需要跨页/持久化定位记录时，请使用上表的「稳定标识字段」；仅做列表展示时用 `id` 即可。

### 偏差 2：乐谱 / 工程的 `id` 是 uuid 字符串，不是数字

`/api/scores`、`/api/projects` 的 `id`（以及 `DELETE /api/{scores,projects}/{id}` 的路径参数）是 **uuid 字符串**（如 `9f2c1a3e-...`），请勿按数字解析或拼接。

同时，为兼容「按序号操作」的写法，删除/改可见性/下载接口**同时支持传入 uuid 或列表序号**（纯数字按序号处理，从 1 开始，与当下分页参数相关）。
> 建议客户端一律用 uuid，避免分页变化导致误删。

### 偏差 3：新增「直接上传」接口（非需求文档要求）

需求文档中 `/api/scores` 只接收 `fileUrl`。实际客户端若不便自建上传通道，可改用：
- `POST /api/scores/upload`（multipart，字段 `file`）— 一次完成上传 + 入库
- `/api/projects/upload` 本就支持 multipart，字段名 `file`

---

## 7. 快速自测（curl）

```bash
BASE=https://drumbearai.com
TOKEN=<登录后拿到的 token>
AUTH="Authorization: Bearer $TOKEN"

# 1. 推广
curl -s -H "$AUTH" $BASE/api/invite
curl -s -H "$AUTH" "$BASE/api/commission/records?page=1&pageSize=20"
curl -s -H "$AUTH" -H 'Content-Type: application/json' -X POST \
     -d '{"amountCents":1000}' $BASE/api/commission/withdraw
curl -s -H "$AUTH" "$BASE/api/commission/withdrawals?page=1&pageSize=20"

# 2. 订单 / 3. 积分
curl -s -H "$AUTH" "$BASE/api/orders?page=1&pageSize=20"
curl -s -H "$AUTH" $BASE/api/points
curl -s -H "$AUTH" -X POST $BASE/api/points/checkin
curl -s -H "$AUTH" "$BASE/api/points/records?page=1&pageSize=20"

# 4. 乐谱
curl -s -H "$AUTH" -F "file=@/path/to/score.dbscore" -F "title=测试乐谱" \
     $BASE/api/scores/upload
curl -s -H "$AUTH" "$BASE/api/scores?page=1&pageSize=20"
curl -s -H "$AUTH" -H 'Content-Type: application/json' -X PATCH \
     -d '{"visibility":"public"}' $BASE/api/scores/<uuid>/visibility
curl -s -H "$AUTH" -X DELETE $BASE/api/scores/<uuid>

# 5. 工程
curl -s -H "$AUTH" -F "file=@/path/to/project.dbscore" $BASE/api/projects/upload
curl -s -H "$AUTH" "$BASE/api/projects?page=1&pageSize=20"
curl -s -H "$AUTH" -o out.dbscore $BASE/api/projects/<uuid>/download
curl -s -H "$AUTH" -X DELETE $BASE/api/projects/<uuid>

# 6. 反馈 / 7. 通知
curl -s -H "$AUTH" -H 'Content-Type: application/json' -X POST \
     -d '{"content":"桌面端很好用","contact":"13800001111"}' $BASE/api/feedback
curl -s -H "$AUTH" "$BASE/api/notifications?page=1&pageSize=20"
curl -s -H "$AUTH" -X POST $BASE/api/notifications/1/read

# 8. 登录态
curl -s -H "$AUTH" $BASE/api/user
# 未登录应得 401 + LOGIN_REQUIRED
curl -s -i $BASE/api/user | head -1
```

---

## 8. 上线状态与验证记录（2026-10-11）

**已上线**：`https://drumbearai.com`（生产库已迁移，新表 `cloud_scores` / `cloud_projects`、新列 `commissions.amount_cents/kind/order_no`、`withdrawals.amount_cents/phone`、`payment_orders.fulfilled_at` 齐备）

线上实测通过项（节选）：

| 用例 | 结果 |
|---|---|
| 年卡发放（回调/补偿） | `memberType=standard`、到期日 +365 天、`currentPlanId=yearly`、**不再发激活码** ✅（v1.2 双链路改造后生产实测） |
| 15% 现金佣金 | ¥199 → `commissionCents: 2985`、`kind=cash_cents`、`order_no` 幂等 ✅ |
| 会员开通幂等 | 重复调 subscribe → `alreadyFulfilled:true`，到期日不变 ✅ |
| 线下激活码链路 | 后台生成（`source=manual`）→ 软件激活 365 天 → 同设备重复激活幂等 → 换设备 `DEVICE_CONFLICT` ✅ |
| 佣金记录 | `recordNo` 稳定 id + 手机号掩码 `138****8888` ✅ |
| 提现 | 余额校验（超额 → `INSUFFICIENT_BALANCE`）、成功后余额归零、生成记录与通知 ✅ |
| 提现状态归一 | 历史 `approved` 落库为 `paid`，客户端读到 `paid` ✅ |
| 订单分页 | 统一外壳 + `orders` 旧字段兼容 ✅ |
| 积分 | 签到 `{balance,reward}`、重复签到 `ALREADY_CHECKED_IN` ✅ |
| 云乐谱 | 上传/列表/改可见性/删除；越权访问他人记录 → `NOT_FOUND` ✅ |
| 云工程 | 上传/下载（字节一致）/超配额 `QUOTA_EXCEEDED`/删除 ✅ |
| 反馈 / 通知 | 提交成功；分页 + 单条已读 + `NOT_FOUND` ✅ |
| 未登录拦截 | 16 项接口全部 401 + `LOGIN_REQUIRED` ✅ |
| Cookie 鉴权 | `audio_token` 方式同样 200 ✅ |
| PATCH / DELETE 经 nginx | 正常转发 ✅ |

**数据安全**：上线前已用 SQLite backup API 完整备份至 `/opt/backups/`（v1.2 改造部署前备份 `chat.db.20261011105110`；**v1.3 部署前备份 `chat.db.before-trial-activation-20261011-1940`**）；全部验证账号与数据已清理，生产用户数不变（56）。

### 8.1 v1.3 上线验证记录（2026-10-11 晚，已上线）

生产库迁移：`users.trial_end_at` / `dbscore_licenses.bound_user_id` / `dbscore_licenses.account_granted_at` 三个新列已加；**56 个用户全部回填 `trial_end_at`（= 注册时间 + 3 天，偏差为 0）**，`login_type` 55/56 已回填。

| 用例 | 结果 |
|---|---|
| 注册即赠试用 | 新用户注册即写 `trial_end_at` = 注册时间 + 3 天 ✅（本地真实注册链路实测） |
| `/api/user` 试用字段 | `trialEndAt` / `trialActive=true` / `trialDaysLeft=3` ✅；剩余 1.2 天 → `2`（向上取整）✅；试用过期 → `trialActive=false`、`trialDaysLeft=0`、`memberType` 仍 `free` ✅ |
| 激活码绑定账号 | 带 token 激活 → 账号 `member_type=standard`、`member_expire_at` = 激活时间 + 365 天、`bound_user_id` 与 `account_granted_at` 落库、生成 `subscriptions(plan_id=yearly)`；响应带 `memberType`/`memberExpireAt` ✅（**生产实测**） |
| 客户端即时可见 | 激活后 `GET /api/user` 立即返回会员态，与库内一致 ✅ |
| 重复激活幂等 | 同码同账号再激活 → 成功但 `memberAlreadyGranted:true`，到期日**未被顺延** ✅ |
| 设备绑定仍生效 | 同码换设备 → `DEVICE_CONFLICT`「该激活码已绑定其他设备，请联系客服解绑」，会员期不变 ✅ |
| 防一码多开 | 解绑设备后由**另一账号**激活 → 接口成功但 `memberGrantSkipped:"other_account"`，另一账号仍为 `free`，`bound_user_id` 未被覆盖 ✅ |
| 永久激活码 | `durationDays=0` → `member_type=standard` 且 `member_expire_at = NULL`，响应 `memberExpireAt: null` ✅ |
| 老数据补绑 | 历史未绑账号的激活码，登录后调 `/api/dbscore/license` / `heartbeat` → 自动补绑并开通；**已是会员则顺延 365 天**；再次调用幂等不再顺延；DTO 返回 `accountBound: true` ✅ |
| 未登录兼容 | 未登录激活 / 查询授权**行为不变**（只绑设备、不开会员、不误绑）✅ |
| 后台回归 | `/api/admin/users` 列表与 `/api/admin/user/:id` 详情正常，列表已含 `trial_end_at`/`phoneMasked`/`avatarUrl`/`last_login_at`/`last_active_at`/`login_type`/`commissionBalanceCents`/`remark` ✅ |
| 页面回归 | `https://drumbearai.com/`、`/admin`、`/dbscore` 均 200；`/api/software` 仍返回 `latestVersion: 5.0.0` ✅ |

> 生产验证用的临时账号 / 激活码 / token / 订阅已全部删除（残留计数均为 0）。

---

## 9. 软件更新接口（v1.1，2026-10-11 追加）

客户端「检查更新」已就绪，读取 `/api/software` 各平台对象的 `version` 字段。本轮后端已支持**后台显式维护版本号与更新说明**。

### 9.1 `/api/software` 返回结构（新增字段）

```json
{
  "success": true,
  "latestVersion": "5.0.1",
  "mac": {
    "url": "/files/DBscore_5.0.1.dmg",
    "name": "DB score制谱大师.dmg",
    "size": 201401296,
    "version": "5.0.1",
    "notes": "修复若干问题，新增个人中心"
  },
  "win":   { "url": "", "name": "", "size": 0, "version": "", "notes": "" },
  "macArm":   { "……同 mac" },
  "macIntel": { "……同 mac" },
  "player": { "win": { "……" }, "mac": { "……" } },
  "course": { "url": "", "name": "" }
}
```

- `version`：**三段式字符串**（`5.0.1`），供客户端数值比对；无包/未填时为空串
- `notes`：本次更新说明（可空），客户端可在更新弹窗里展示
- `latestVersion`：win/mac 两者中的较大值（附赠字段，可不使用）
- 兼容性：新增字段纯增量，旧客户端不受影响；`arm`/`intel`/`macArm`/`macIntel` 与 `mac` 同对象

### 9.2 版本号来源与优先级

`后台显式填写的版本号` > `安装包文件名解析`（如 `DBScore-4.5.0.dmg` → `4.5.0`）
> ⚠️ 文件名解析只是兜底。**正式发版必须在后台填版本号**，否则客户端拿到的 version 可能为空。

### 9.3 版本号规则（后端已做规范化）

- 接受 2~4 段数字，**自动补齐为三段**：`5.1` → `5.1.0`；兼容前缀 `v`（`v5.0.1` → `5.0.1`）
- 非法格式（`abc`、`5．0．1` 全角等）直接拒绝，不会写入脏值
- 客户端比对建议按**数值分段**比较（`5.0.10 > 5.0.9`），不要按字符串比较

### 9.4 后台操作方式

| 方式 | 说明 |
|---|---|
| 上传安装包时填写 | 后台「软件与课程」每个平台卡片有「版本号 + 更新说明」输入框，随上传一并保存 |
| **只改版本号**（推荐） | 卡片内改完点「保存版本信息」即可，**无需重新上传安装包** |

对应后台接口（客户端无需关心，仅备查）：
- `POST /api/admin/software/upload`（multipart 新增可选字段 `version`、`notes`）
- `POST /api/admin/software/version`（body `{ platform, version?, notes? }`，platform: `win`/`mac`/`player_win`/`player_mac`；只传一个字段时另一个不变）

### 9.5 检查更新辅助接口（可选，附赠）

客户端已按 `/api/software` 实现即可。如需后端直接判定，另提供：

`GET /api/software/check?platform=mac&version=5.0.0`（公开，无需登录）

```json
{
  "success": true, "platform": "mac",
  "localVersion": "5.0.0", "latestVersion": "5.0.1",
  "hasUpdate": true, "url": "/files/DBscore_5.0.1.dmg",
  "name": "DB score制谱大师.dmg", "size": 201401296,
  "notes": "修复若干问题，新增个人中心",
  "message": "发现新版本 5.0.1"
}
```
`hasUpdate=false` 时 `message` 为「已是最新版本」、`url` 为空串。

### 9.6 下载页

`https://drumbearai.com/dbscore` 各平台卡片现在会显示 **`v版本号`** 徽章与「更新说明」一行，与 `/api/software` 同一数据来源。

### 9.7 当前生产状态（2026-10-11）

| 平台 | 安装包 | version | 说明 |
|---|---|---|---|
| Mac | `DB score制谱大师.dmg`（192MB） | **5.0.0** | 从包内 `Info.plist` 的 `CFBundleShortVersionString` 实测读出，已如实写入 |
| Windows | 未上传 | — | — |

> **重要**：当前线上 Mac 包**实际就是 5.0.0**，因此 5.0.0 客户端会正确提示「已是最新版本」。
> 等 5.0.1 构建完成后，在后台「软件与课程 → Mac 版」上传新包并填 `5.0.1`（更新说明如「修复若干问题，新增个人中心」），5.0.0 客户端即会提示「发现新版本 5.0.1」并给出下载按钮。
> 请勿把旧包的版本号改成 5.0.1——那会让 5.0.0 客户端反复提示「有新版本」却下载到同一个 5.0.0 包。

---

## 10. 原有待确认问题（已全部闭环）

| # | 问题 | 结论（产品确认） |
|---|---|---|
| 1 | `/api/orders` 的 `id` 是页内序号，可否接受（用 `orderNo` 定位）？ | ✅ 接受，订单稳定标识用 `orderNo` |
| 2 | 乐谱/工程 `id` 用 uuid 字符串可否接受？ | ✅ 接受，客户端用 uuid 字符串 id |
| 3 | 桌面端支付页形式？ | ✅ 跳转浏览器（不开内嵌二维码） |
| 4 | 云备份是否做「保留最近 N 个版本」？ | ✅ 不做版本管理，同名多次上传各存一份 |

---

## 11. 注册/登录来源识别 与 后台「DB Score 用户管理」（v1.4，2026-10-12 上线）

### 11.1 是什么

- 后端在**每次注册与登录**时识别请求来自「DB Score 软件端」还是「网页版」，写入账号（`reg_source` 注册来源 / `last_login_source` 最近登录来源），并留一条**登录记录**（时间、事件、方式、来源、IP、平台、客户端版本）。
- 运营后台新增 **「DB Score 用户管理」**（入口：后台侧边栏「DB Score 会员管理」下面）：软件端用户单独成列，含完整手机号（未脱敏，便于客服跟进）、昵称、头像、注册时间、最近登录/活跃、会员类型与到期、试用状态、邀请码、注册来源；顶部有统计卡（软件端用户 / 试用中 / 正式会员 / 今日新增 / 网页端 / 全站）。
- 后台「用户管理」主列表同步补齐这些列；用户详情抽屉新增「登录记录」卡片。**现有 8 大模块 21 个端点的请求/响应契约均不变**，本节对客户端是**纯增量建议**。

### 11.2 软件端用户如何被识别（满足任一即可）

| 方式 | 说明 | 建议 |
|---|---|---|
| UA 带 `DBScore/<version> (macos|windows)` | 《授权接口规范》§1 本就要求 | ✅ 已实现的客户端无需改动 |
| 请求头 `X-DBScore-Version: <version>` | 授权接口规范要求的头 | ✅ 已实现的客户端无需改动 |
| 请求体 / 头显式 `source` | 请求体传 `"source": "app"`（或头 `X-Client-Source: app`），取值 `app` / `web` / `miniapp` | 软件端**注册/登录接口**建议显式带上，最稳 |
| UA 含 `Electron` | 兜底：Electron 壳的默认 UA 也会被识别为软件端 | 无需处理 |

> 识别优先级：显式 `source` > DBScore 标识 > Electron > 小程序 UA（miniapp）> 其余一律 `web`。
> 手机号登录（`/api/auth/register`、`/api/auth/login`）与微信登录（网页扫码）**三条链路都已覆盖**；后台开通的账号 `reg_source = admin`。

### 11.3 客户端需要配合什么

**唯一建议**：软件端调 `/api/auth/register` / `/api/auth/login` 时，在请求体加 `"source": "app"`（或确保 UA / `X-DBScore-Version` 头按规范带上）。不带也能正常注册登录，只是会被归到「网页端用户」。

### 11.4 登录记录（后台可见，客户端无需上报额外数据）

每次注册/登录写一条，含：时间、事件（注册/登录）、方式（手机号/微信）、来源（软件端/网页版/小程序/后台）、IP、平台（macos/windows）、客户端版本、User-Agent。**每人只保留最近 50 条**，超出的自动清理。

### 11.5 上线验证记录（2026-10-12，生产实测）

| 用例 | 结果 |
|---|---|
| 软件端注册（UA `DBScore/5.0.1 (macos)` + `X-DBScore-Version`） | `reg_source=app`、登录记录含 `macos / 5.0.1 / IP` ✅ |
| 显式 `source: "app"`（普通浏览器 UA） | 识别为 app（显式声明优先）✅ |
| 无标识注册 | 识别为 web ✅ |
| 软件端再次登录 | 追加「登录」记录、更新 `last_login_at` ✅ |
| 微信登录链路 | 注册/登录均写「注册/登录」记录、来源正确（数据层实测）✅ |
| 后台列表 | 完整手机号 / 昵称 / 头像 / 注册时间 / 最近登录 / 会员 / 试用状态 / 邀请码 / 注册来源 全部返回 ✅ |
| 搜索 | 完整手机号 / 昵称 / 用户 ID / 邀请码 全部命中 ✅ |
| 筛选 | 软件端 / 网页端 / 试用中 / 正式会员 / 试用已到期 / 今日新增 均按口径返回 ✅ |
| 统计卡 | `stats: {total, app, web, trial, member, today}` ✅ |
| 详情 | 登录记录（近 30 条）+ 订单 + 激活码/设备 + 最近活跃 ✅ |
| 生产数据安全 | 验证账号与登录记录已全部清理（残留 0），用户数 56→57（自然增长）✅ |

> 本地同步验证 49 项全过（含软件端/网页端/显式来源/微信链路/搜索/筛选/统计/详情）。
