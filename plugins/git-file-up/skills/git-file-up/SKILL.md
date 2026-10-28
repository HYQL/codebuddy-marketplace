---
name: git-file-up
version: 1.0.0
display_name: Git 文件转外链（临时 URL）
display_name_en: Git File to Public URL (Ephemeral)
description: 把本地文件（图片/视频/音频/文档，单文件 ≤50MB）上传到 GitHub 支持附件端点，返回可直接引用的云端 URL。注意这是临时通道，URL 仅 60 分钟有效。内置串行队列 + 按 ratelimit 响应头自适应等待 + 指数退避 + Retry-After 处理，规避 IP 限流；超时按文件体积自适应。当需要把本地图片变成外链、给 Markdown/网页/API 提供公网图片地址、或批量上传媒体文件时使用。Upload local files to a public URL via the GitHub support-attachment endpoint with adaptive rate-limit control; the URL expires after 60 minutes.
whenToUse: 用户说「上传这张图/这个文件，给我 URL」「转成外链」「图床」「上传到云端」「批量上传图片」，或后续流程（生图、封面、截图、文档配图）需要一个**短期**公网可访问的 URL 时。需要长期托管时上传后立即转存。
---

# git-file-up — 本地文件 → 云端 URL

端点（GitHub 支持工单附件接口，匿名可上传）：

```
POST https://github.zendesk.com/api/v2/uploads.json?filename=<文件名>
```

返回 JSON 里的 `upload.attachment.content_url` 就是公网 URL（脚本已自动提取，还会回带 `token`）。

## 用法

```bash
node "<SKILL_DIR>/scripts/upload.mjs" <file> [file...]
```

`SKILL_DIR` = 本 skill 所在目录（即本仓库 `plugins/git-file-up/skills/git-file-up`）。

每行输出一条 JSON：

```json
{"ok":true,"file":"...","url":"https://github.zendesk.com/attachments/token/xxx/?name=a.png","bytes":11,"token":"...","expiresAt":"2026-10-26T12:42:01Z","expiresInSec":3599}
{"ok":false,"file":"...","status":429,"error":"HTTP 429: ..."}
```

`expiresAt` 是 UTC ISO（响应里的 `upload.expires_at`），`expiresInSec` 是换算出的剩余秒数（实测 3599，即 60 分钟）。**交付 URL 时把过期时间一起给用户。**

退出码：全部成功 `0`，任一失败 `1`。

## 60 分钟有效期 —— 必须遵守

这是**临时**文件通道，不是图床。URL 在 60 分钟后失效。

- 拿到 URL 后**立即**使用，不要存起来当长期资源。
- 交付给用户时，明确写出「此链接 60 分钟内有效」+ 过期时间点。
- 需要长期托管 → 上传后立刻转存到对象存储 / 仓库 / 用户自有 CDN，再引用转存后的地址。
- 文档、README、网页、生产配置里**不要**写这类临时 URL，它们会在 1 小时后变成死链。
- 同一文件需要反复引用 → 转存一次，而不是每次重新上传（重传会再吃一遍限流额度，且大文件要等 10 分钟）。
- 已过期的 URL 表现为 302 跳转到过期提示页或 404；重跑上传即可，不要反复重试旧链接。

## 硬限制

| 项 | 值 |
|---|---|
| **URL 有效期** | **60 分钟**。这是临时文件通道，过期后 URL 无法访问（302 到过期页/404） |
| 单文件大小 | **≤ 50MB**（超出直接判失败，不发请求） |
| 类型 | 图片 / 视频 / 音频 / pdf / zip / txt / md / json / csv 等；未知后缀按 `application/octet-stream` 发 |
| 空文件 | 拒绝 |
| 实测上传带宽 | **约 80KB/s**（本机 2026-10-26 实测：20MB 用时 255s）。50MB 需要 10 分钟以上，属正常，不是卡死 |

超过 50MB 的文件先切分或压缩，不要指望端点兜底。

## 限流规避（按响应头自适应，默认已开）

端点返回 `ratelimit-remaining` / `ratelimit-reset` 头。**实测配额约 2500 点 / 60 秒（≈250 次请求/分钟）**，而单连接带宽只有约 80KB/s —— 带宽才是真瓶颈，配额根本用不完。所以默认**不做固定间隔等待**（那是纯空转：10 个文件 1500ms 间隔要 22.3s，无间隔只要 9.5s），只在配额见底时才等。

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `UPLOAD_MIN_INTERVAL_MS` | `0` | 相邻两次上传的固定间隔。`0` = 纯自适应；需要刻意慢放时才调大 |
| `UPLOAD_RESERVE` | `200` | 配额保留水位：`ratelimit-remaining` 低于此值才等到 reset |
| `UPLOAD_RETRIES` | `4` | 429 / 5xx / 网络错误的重试次数，退避 1s→2s→4s→8s（≤60s） |
| `UPLOAD_TIMEOUT_MS` | `0` | 单次请求超时；`0` = 按体积自适应（保守 40KB/s + 60s 余量，下限 120s） |
| `UPLOAD_ASSUMED_BPS` | `40000` | 自适应超时使用的保守带宽 |
| `UPLOAD_ENDPOINT` | 上述端点 | 换自建/代理端点 |

限流行为要点：

- **严格串行**，不做并发。多文件一次传完时脚本自己排队，不要自己写并行循环。
- 每发一个请求前读上一次响应头：`remaining > RESERVE` 直接过，否则等到 `reset` 再发，并打一行 `[rate] remaining=... 等待 Ns` 到 stderr。
- `429` 时优先读 `Retry-After`，其次按 `ratelimit-reset` 计算等待；两者都没有才走指数退避。
- `413 / 415 / 401 / 404` 不重试，直接失败（重试只会烧更多限流额度）。
- 大文件上传请用后台任务跑（`run_in_background`），不要阻塞对话；10MB 约需 2 分钟，50MB 约需 10 分钟。
- **不要靠并发提速**：实测 4 个 1MB 并发只有 32.5/26.6/22.4/19.9 KB/s，总吞吐约 101KB/s，和单连接差不多，却更容易撞限流。


## 处理返回

1. 只从 `ok:true` 的行里取 `url`，直接用于 Markdown `![](url)`、HTML `<img src>` 或下游 API —— **并在 60 分钟内用完**。
2. 同时把 `expiresAt` 报给用户，别只给裸 URL。
3. `ok:false` 的行带 `error`/`status`：`429` → 脚本已自动按 reset 等待重试，仍失败说明配额被别处占满，隔一分钟再跑；`413` 或 `file too large` → 文件超限；`timeout` → 调大 `UPLOAD_TIMEOUT_MS` 或把 `UPLOAD_ASSUMED_BPS` 调小。
4. 失败的不要静默跳过——把失败清单原样报给用户。

## 不要做

- 不要为多个文件写并发 `Promise.all` 上传：实测并发不提速（总吞吐仍 ~100KB/s），只会更快撞限流。
- 不要在小体积文件上设置超长超时来“保险”，自适应已覆盖。
- 不要把返回的 URL 当长期资源写进代码/文档/配置——**60 分钟后就是死链**。
- 不要为了“图床”反复重传同一文件，转存一次即可。
