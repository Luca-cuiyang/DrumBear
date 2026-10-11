# DB Score 授权接口 —— 后端实现说明（回执）

> 对应《DBScore 客户端授权接口规范（v1）》
> 后端：鼓乐熊AI 平台（`https://drumbearai.com`）
> 状态：**已按规范实现并上线**，可直接联调。

## 1. 已实现的接口

| 规范章节 | 接口 | 状态 |
|---|---|---|
| §4.1 | `POST /api/dbscore/activate` | ✅ 已实现 |
| §4.2 | `GET /api/dbscore/license?deviceId=<deviceId>` | ✅ 已实现 |
| §4.3 | `POST /api/dbscore/heartbeat` | ✅ 已实现 |
| §7 | `GET /api/software`（检查更新，复用） | ✅ 已补 `version` 与 `arm` / `intel` 别名 |

另保留 `POST /api/dbscore/verify` 作为 §4.3 的等价别名（只读校验，便于过渡期使用）。

**统一响应外壳**：所有接口均返回 `{ success, code, message?, data? }`。
业务失败一律 **HTTP 200** + `success:false` + 具体 `code`（便于客户端直接读 `message` 提示）；仅服务端内部异常返回 `SERVER_ERROR`。

## 2. 请求头

- `Content-Type: application/json`（带 body 的请求）
- `User-Agent: DBScore/<version> (<macos|windows>)` —— 后端会解析其中的平台信息用于统计
- `X-DBScore-Version: <版本号>` —— 与 body 里的 `appVersion` 二选一即可（后者优先）

## 3. 激活（§4.1）

请求：

```bash
curl -X POST https://drumbearai.com/api/dbscore/activate \
  -H "Content-Type: application/json" \
  -H "User-Agent: DBScore/4.5.0 (macos)" \
  -d '{"code":"DBSCORE-XXXX-XXXX-XXXX","deviceId":"<sha256前32位>","deviceName":"Luca 的 MacBook Pro","appVersion":"4.5.0"}'
```

成功（HTTP 200）：

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
      "activatedAt": "2026-10-11T07:41:12.345Z",
      "expireAt": "2027-10-11T07:41:12.345Z",
      "deviceId": "<sha256前32位>",
      "deviceName": "Luca 的 MacBook Pro",
      "lastSeenAt": "2026-10-11T07:41:12.345Z"
    }
  }
}
```

失败（HTTP 200）：

```json
{ "success": false, "code": "CODE_USED", "message": "该激活码已绑定其他设备，请联系客服解绑" }
```

后端规则（与规范一致）：

1. `unused` 激活码 → 校验通过后立即置为已激活，写入 `activatedAt`、`expireAt`（按后台配置天数计算；`durationDays=0` 为永久，此时 `expireAt` 返回 `null`）。
2. 记录设备绑定：`deviceId` + `deviceName`（另存平台与客户端版本，便于后台排查）。
3. **同设备**重复激活 → 幂等，直接返回当前 license，不会重复计时、不报错。
4. **不同设备** → `CODE_USED` / `DEVICE_CONFLICT`；后台执行「解绑」后，新设备可重新激活（`activatedAt` 与 `expireAt` 保持原值不变，即解绑不影响会员期）。

## 4. 查询授权（§4.2）

```bash
curl "https://drumbearai.com/api/dbscore/license?deviceId=<deviceId>"
```

- 有授权：`{ "success": true, "code": "OK", "data": { "license": { ... } } }`
- 无授权：`{ "success": true, "code": "OK", "data": { "license": null } }` → 客户端清除本地会员状态（保留试用期状态）

说明：该接口按 **deviceId** 查询，不需要激活码；status 为 `revoked` / `expired` 时也会返回 license（客户端据此同步为失效/过期）。

## 5. 心跳（§4.3）

```bash
curl -X POST https://drumbearai.com/api/dbscore/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"code":"DBSCORE-XXXX-XXXX-XXXX","deviceId":"<deviceId>","appVersion":"4.5.0"}'
```

- 成功：返回最新 license（含续期后的新 `expireAt`、被停用后的 `status`）。
- 失败：`CODE_REVOKED` / `CODE_EXPIRED` / `DEVICE_CONFLICT` / `INVALID_CODE` 等，客户端按规范锁定增值功能。
- 后端会记录 `lastSeenAt`（后台可见「最后在线」，用于售后与异常排查）。心跳失败不影响既有会员状态，客户端按规范走本地缓存 + 7 天宽限。

## 6. 检查更新（§7）

`GET /api/software` 返回结构（节选）：

```json
{
  "success": true,
  "win":      { "url": "...", "name": "DBScore-4.5.0-Setup.exe", "size": 123456789, "version": "4.5.0" },
  "mac":      { "url": "...", "name": "DB score制谱大师.dmg", "size": 201326592, "version": "" },
  "arm":      { "同 mac" },
  "intel":    { "同 mac" },
  "macArm":   { "同 mac" },
  "macIntel": { "同 mac" },
  "player":   { "win": { ... }, "mac": { ... } },
  "course":   { "url": "...", "name": "..." }
}
```

- `arm` / `intel` 为兼容别名，与 `mac` 同值（Mac 已合并为一个通用安装包，同时支持 M 芯片与 Intel 芯片）。
- `version` 由安装包文件名中的版本号自动提取（如 `DBScore-4.5.0.dmg` → `4.5.0`）。**建议安装包命名带版本号**，客户端即可用于版本比对；无版本号时该字段为空字符串。
- 下载地址含中文/空格时会做一次 URL 编码，客户端直接使用即可。

## 7. 激活码格式与容错

- 后台生成的激活码格式：`DBSCORE-XXXX-XXXX-XXXX`（字符集去掉了易混淆的 `0 O 1 I L`）。
- 后端做**宽松匹配**：大小写、连字符、空格差异均可命中（`dbscore-xxxx-xxxx-xxxx`、`DBSCORExxxxxxxx` 都能激活）。
- 建议客户端也做同样的规范化后再提交（去掉空格、转大写）。

## 8. 后台（供客服/运营使用）

平台运营后台 →「软件与课程」→「DB Score 会员管理」：

- 生成激活码（1~500 个 / 按年或自定义天数 / 永久），可登记客户名、联系方式、备注（如抖店订单号），生成后支持「复制全部」
- 列表可见激活状态、到期时间、**绑定设备名与机器码、最后在线时间**；支持搜索、状态筛选、导出 CSV、续期（从原到期日顺延）、解绑（换机）、作废/恢复

## 9. 联调建议

拿到激活码后按顺序验证 4 步即可覆盖规范语义：

1. 激活 → 期望 `OK` + `status: "active"` + `expireAt` 正确
2. 同一 `deviceId` 再激活一次 → 期望仍 `OK`（幂等，`expireAt` 不变）
3. 换一个 `deviceId` 激活 → 期望 `CODE_USED`；后台「解绑」后同一设备再激活 → 期望 `OK`
4. 心跳 → 期望 `OK` 且后台「最后在线」刷新

如需联调账号或批量测试激活码，联系平台方在后台生成即可。
