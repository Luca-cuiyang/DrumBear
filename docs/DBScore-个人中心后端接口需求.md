# DB Score 个人中心 —— 后端接口需求（发给 workbuddy）

> 目标：支撑 DB Score 桌面端「个人中心」的账号、会员、订单、作品、积分、推广、反馈等功能。
> 桌面端统一用 `Authorization: Bearer <token>` 鉴权（与现有 `/api/user` 一致）。
> 统一响应外壳：`{ "success": true, "code": "OK", "message": "", "data": {...} }`；失败 `{ "success": false, "code": "XXX", "error": "提示" }`。

## 一、推广赚佣（佣金比例 15%）

规则：用户 A 邀请用户 B 注册，B 付费成为会员后，A 获得 B 实付金额的 **15%** 佣金。

### 1.1 我的推广信息
`GET /api/invite`

返回：
```json
{
  "success": true,
  "code": "OK",
  "data": {
    "inviteCode": "MAXTANSU",
    "inviteUrl": "https://www.drumbearai.com/?invite=MAXTANSU",
    "commissionBalanceCents": 2985,
    "totalEarnedCents": 5970,
    "inviteeCount": 2,
    "paidInviteeCount": 1
  }
}
```

### 1.2 佣金记录
`GET /api/commission/records?page=1&pageSize=20`

返回 `data.list`：
```json
[
  {
    "id": 1,
    "amountCents": 2985,
    "type": "invite_reward",
    "sourceNickname": "微信昵称或手机号掩码",
    "createdAt": "2026-10-11T12:00:00.000Z"
  }
]
```

### 1.3 提现申请
`POST /api/commission/withdraw`

请求：`{ "amountCents": 2985 }`（单位为分）

返回：`{ "success": true, "code": "OK", "data": { "withdrawalId": 1 } }`

### 1.4 提现记录
`GET /api/commission/withdrawals?page=1&pageSize=20`

返回 `data.list`，每项含：`id`、`amountCents`、`status`（pending/paid/rejected）、`createdAt`。

## 二、订单记录（我的订单）

### 2.1 我的订单列表
`GET /api/orders?page=1&pageSize=20`

返回 `data.list`，每项含：`id`、`orderNo`、`planId`、`planName`、`amountCents`、`status`（pending/paid/cancelled）、`createdAt`。

## 三、积分中心

### 3.1 积分余额与签到
`GET /api/points`

返回 `data`：`{ "balance": 83805, "todayCheckedIn": false }`

### 3.2 每日签到
`POST /api/points/checkin`

返回 `data`：`{ "balance": 83810, "reward": 5 }`；已签到返回 `code:"ALREADY_CHECKED_IN"`。

### 3.3 积分明细
`GET /api/points/records?page=1&pageSize=20`

返回 `data.list`，每项含：`id`、`amount`、`type`、`remark`、`createdAt`。

## 四、我的乐谱（云端）

### 4.1 云端乐谱列表
`GET /api/scores?page=1&pageSize=20`

返回 `data.list`，每项含：
```json
{ "id": 1, "title": "我的作品", "coverUrl": "", "visibility": "public", "updatedAt": "..." }
```

### 4.2 发布乐谱
`POST /api/scores`

请求：`{ "title": "作品名", "fileUrl": "乐谱文件地址", "visibility": "public" }`

### 4.3 删除乐谱
`DELETE /api/scores/{id}`

### 4.4 修改可见性
`PATCH /api/scores/{id}/visibility`，请求 `{ "visibility": "private" }`

## 五、我的工程（云备份）

### 5.1 工程上传
`POST /api/projects/upload`（multipart/form-data，字段 `file`）

返回 `data`：`{ "id": 1, "name": "xxx.db", "size": 12345, "createdAt": "..." }`

### 5.2 云端工程列表
`GET /api/projects?page=1&pageSize=20`

返回 `data.list`，每项含：`id`、`name`、`size`、`createdAt`、`updatedAt`。

### 5.3 下载工程
`GET /api/projects/{id}/download`（返回文件流）

### 5.4 删除工程
`DELETE /api/projects/{id}`

## 六、意见反馈

### 6.1 提交反馈
`POST /api/feedback`

请求：`{ "content": "反馈内容", "contact": "选填联系方式" }`

## 七、通知中心（可选，建议一起做）

### 7.1 通知列表
`GET /api/notifications?page=1&pageSize=20`

返回 `data.list`，每项含：`id`、`title`、`content`、`type`、`createdAt`、`read`。

### 7.2 标记已读
`POST /api/notifications/{id}/read`

## 八、会员购买回调（重点确认）

微信支付成功后，必须把该账号升级为年度会员：
- `member_type` 置为 `standard`
- `member_expire_at` 置为支付成功时间 + 365 天
- 同时写入订单状态为 `paid`

桌面端登录态查询仍走 `/api/user`，返回字段保持 `memberType`、`memberExpireAt`。

## 备注

- 所有接口都需要登录态（`Authorization: Bearer <token>`），未登录返回 `code:"LOGIN_REQUIRED"`。
- 金额一律用「分」为单位（`*Cents`），避免浮点误差。
- 分页统一 `page`、`pageSize`，返回 `data.list` 和 `data.total`。
