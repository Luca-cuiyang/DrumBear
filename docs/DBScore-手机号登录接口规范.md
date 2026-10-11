# DB Score 手机号登录接口规范（桌面端，v1）

> 桌面端（DB Score）新增「手机号验证码登录」为主力登录方式。
> 复用鼓乐熊网站已有的 `/api/auth/*` 接口，补充桌面端所需的鉴权与会员状态返回约定。
> 后端（workbuddy）按本规范调整/确认即可。

## 1. 基本约定

- Base URL：`https://www.drumbearai.com`（与网页端一致）
- 请求体：`Content-Type: application/json`
- 登录成功后，客户端本地保存 `token`，并在后续请求中通过请求头携带：
  `Authorization: Bearer <token>`
- 网页端用 cookie（`audio_token`）鉴权；桌面端统一用 `Authorization` 头。请后端同时兼容两种方式。
- 统一成功外壳：`{ "success": true, "message": "...", "token": "...", "user": {...} }`
- 统一失败外壳：`{ "success": false, "error": "错误提示" }`（沿用网页端现有格式）

## 2. 接口

### 2.1 发送验证码

`POST /api/auth/send-code`

请求：
```json
{ "phone": "13800138000" }
```

成功：
```json
{ "success": true, "message": "验证码已发送" }
```

失败：`{ "success": false, "error": "请输入正确的手机号" }`

要求：60 秒内同号码限发一次，验证码有效期 5 分钟。

### 2.2 登录（已注册用户）

`POST /api/auth/login`

请求：
```json
{ "phone": "13800138000", "code": "123456" }
```

成功：
```json
{
  "success": true,
  "token": "<token>",
  "user": {
    "id": 123,
    "phone": "138****0000",
    "nickname": "微信昵称",
    "memberType": "standard",
    "expireAt": "2027-10-11T00:00:00.000Z"
  }
}
```

失败：`{ "success": false, "error": "验证码错误" }`

### 2.3 注册（未注册手机号自动注册）

`POST /api/auth/register`

请求：
```json
{ "phone": "13800138000", "code": "123456", "nickname": "昵称（可选）", "inviteCode": "邀请码（可选）" }
```

成功：与登录成功同构，返回 `token` + `user`。

### 2.4 查询当前用户与会员状态

`GET /api/user`

请求头：`Authorization: Bearer <token>`

成功：
```json
{
  "success": true,
  "user": {
    "id": 123,
    "phone": "138****0000",
    "nickname": "微信昵称",
    "memberType": "standard",
    "expireAt": "2027-10-11T00:00:00.000Z"
  }
}
```

说明：客户端启动或刷新时调用，据此判断会员是否有效；未登录/token 失效返回 `success:false` 与 `"请先登录"`。

### 2.5 会员购买（客户端不做收银）

客户端通过内置浏览器打开 `https://www.drumbearai.com/` 的会员购买页，用户在网页完成支付。
支付完成后，客户端调用 `/api/user` 刷新会员状态即可。

## 3. memberType 约定

- `free`：免费用户
- `standard`：年度会员（¥199/年）
- 客户端只把 `memberType != "free"` 且 `expireAt` 未过期视为有效会员。

## 4. 客户端行为

1. 登录/注册成功后保存 token，立即调用 `/api/user` 拉取会员状态。
2. 每次启动、每 24 小时、以及用户点击「刷新授权」时调用 `/api/user` 同步会员状态。
3. 3 天免费试用仍由客户端本地计时（未登录时可用，登录后按后端会员状态为准）。
4. 功能锁定、无水印、到期提醒逻辑与激活码模式完全一致。
