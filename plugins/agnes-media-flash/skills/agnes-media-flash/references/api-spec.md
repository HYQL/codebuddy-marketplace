# Agnes AI 图像/视频 API 参考（抓取自官方文档 2026-10）

来源：
- https://www.agnes-ai.cn/zh-Hans/docs/overview
- https://www.agnes-ai.cn/zh-Hans/docs/agnes-image-25-flash
- https://www.agnes-ai.cn/zh-Hans/docs/agnes-video-25-flash

## 通用

| 项 | 值 |
|---|---|
| Base URL | `https://api.agnes-ai.cn/v1` |
| 认证 | 请求头 `Authorization: Bearer YOUR_API_KEY`（平台 https://platform.agnes-ai.cn 控制台创建） |
| Content-Type | `application/json` |
| 兼容性 | OpenAI 风格（修改 base_url + key + 模型名即可迁移） |

## 图像：Agnes Image 2.5 Flash（同步）

- 模型：`agnes-image-2.5-flash`
- 端点：`POST https://api.agnes-ai.cn/v1/images/generations`
- 每次返回 1 张图；客户端超时建议 60–360 s

### 请求参数

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model` | string | 是 | 固定 `agnes-image-2.5-flash` |
| `prompt` | string | 是 | 文本指令（文生图/图生图/多图合成） |
| `size` | string | 是 | 档位 `1K`/`2K`/`3K`/`4K`；也接受 `1024x768` 等精确写法（自动映射最近档位） |
| `ratio` | string | 否（默认 `1:1`） | `1:1` `3:4` `4:3` `16:9` `9:16` `2:3` `3:2` `21:9` |
| `return_base64` | boolean | 否（默认 false） | 文生图时 true 以 Base64 返回 |
| `extra_body.image` | string[] | 图生图/多图合成必填 | 输入图：公共 HTTPS URL 或 Data URI（`data:image/png;base64,...`），多图合成传多张 |
| `extra_body.response_format` | string | 否 | `"url"` 或 `"b64_json"`；**必须放 extra_body 内，不能放顶层** |

易错点：图生图**不需要** `tags: ["img2img"]`；输入图 URL 必须可公开访问，否则用 Data URI。

### size × ratio → 像素

| ratio | 1K | 2K | 3K | 4K |
|---|---|---|---|---|
| 1:1 | 1024×1024 | 2048×2048 | 3072×3072 | 4096×4096 |
| 3:4 | 864×1152 | 1728×2304 | 2592×3456 | 3456×4608 |
| 4:3 | 1152×864 | 2304×1728 | 3456×2592 | 4608×3456 |
| 16:9 | 1312×736 | 2624×1472 | 3936×2208 | 5248×2944 |
| 9:16 | 736×1312 | 1472×2624 | 2208×3936 | 2944×5248 |
| 2:3 | 832×1248 | 1664×2496 | 2496×3744 | 3328×4992 |
| 3:2 | 1248×832 | 2496×1664 | 3744×2496 | 4992×3328 |
| 21:9 | 1568×672 | 3136×1344 | 4704×2016 | 6272×2688 |

### 响应

```json
{ "created": 1780000000,
  "data": [ { "url": "https://.../xxx.png", "b64_json": null, "revised_prompt": null } ] }
```
b64 模式则 `url` 为 null、`b64_json` 有值。

### 定价（刊例价，当前限时免费）

| 项 | 刊例价 | 当前 |
|---|---|---|
| 1K 输出 | ¥0.07/张 | ¥0 |
| 2K 输出 | ¥0.12/张 | ¥0 |
| 3K 输出 | ¥0.14/张 | ¥0 |
| 4K 输出 | ¥0.16/张 | ¥0 |
| 第 4 张起输入参考图 | ¥0.02/张 | ¥0 |

## 视频：Agnes Video 2.5 Flash（异步任务）

- 模型：`agnes-video-2.5-flash`
- 创建任务：`POST https://api.agnes-ai.cn/v1/videos` → 响应含 `id` / `task_id` / `video_id`
- 查询任务（推荐）：`GET https://api.agnes-ai.cn/agnesapi?video_id=<VIDEO_ID>&model_name=agnes-video-2.5-flash`
- 查询（仅 text 模式可用）：`GET https://api.agnes-ai.cn/agnesapi?video_id=<VIDEO_ID>`
- 轮询建议间隔 1–2 s，直至 `status` 为 `completed` 或 `failed`；`internal_status`/`internal_progress` 是内部字段，**以顶层 `status` 和 `progress` 为准**；completed 时视频地址在顶层 `url`

### 请求参数

公共：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model` | string | 是 | 固定 `agnes-video-2.5-flash` |
| `prompt` | string | 是 | reference 模式可用 `<Picture N>` / `<Audio N>` 指代素材 |
| `mode` | string | 是 | `text` / `keyframe` / `reference` |
| `seconds` | string | 否（默认 `"5"`） | `"4"`–`"12"`（字符串） |
| `size` | string | 否 | Flash 仅 `"720P"`，其他值 HTTP 400 |
| `aspect_ratio` | string | 否（默认 `"16:9"`） | `21:9` `16:9` `4:3` `1:1` `3:4` `9:16` |
| `seed` | int | 否 | 随机种子 |
| `n` | int | 否（默认 1） | 仅支持 1 |

模式专用：

| 字段 | 适用 mode | 说明 |
|---|---|---|
| `first_frame` / `last_frame` | keyframe | 公共 HTTPS URL，至少传一个；该模式禁传 images/audios/videos |
| `images` | reference | URL 列表，最多 5 张；与 audios 至少一类非空；禁传 first_frame/last_frame/videos |
| `audios` | reference | URL 列表，最多 3 段 |
| `videos` | — | Flash 不支持，传有效内容 → 400 |
| text 模式 | 禁传 | `first_frame`、`last_frame`、`images`、`audios`、`videos` |

所有媒体 URL 必须可被 Agnes 服务公开访问，且任务完成前保持有效。

### aspect_ratio → 像素（720P）

| 画幅 | 像素 |
|---|---|
| 21:9 | 1680×720 |
| 16:9 | 1280×704（实测） |
| 4:3 | 960×720 |
| 1:1 | 720×720 |
| 3:4 | 720×960 |
| 9:16 | 720×1280 |

### 查询响应示例（completed）

```json
{ "id": "task_XXX", "object": "video", "status": "completed", "progress": 100,
  "seconds": "4", "size": "720P", "url": "https://.../video.mp4",
  "created_at": 1790062812, "started_at": 1790062812, "completed_at": 1790062857,
  "error": null, "quality": "standard", "internal_status": "pending", "internal_progress": 0 }
```

### 校验错误（均在创建/排队/计费/推理前执行，失败不产生费用，HTTP 400）

| 触发条件 | 响应体 |
|---|---|
| `size` 非 `"720P"` | `{"detail": "size must be 720P"}` |
| `images` 超 5 张 | `{"detail": "images length must not exceed 5"}` |
| `audios` 超 3 段 | `{"detail": "audios length must not exceed 3"}` |
| 传入有效 `videos` | `{"detail": "videos is not supported"}` |

### 定价（原价 ¥0.15/秒，当前限时免费）

```
金额 = 输出秒数×分辨率单价 + 输入视频秒数×分辨率单价 + max(0, 图片数−5)×图片超额单价
```
免费图片 5 张；免费期内各项均为 ¥0。

## curl 快查

```bash
# 文生图
curl -sS https://api.agnes-ai.cn/v1/images/generations \
  -H "Authorization: Bearer $AGNES_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"agnes-image-2.5-flash","prompt":"...","size":"2K","ratio":"16:9","extra_body":{"response_format":"url"}}'

# 创建视频任务
curl -sS -X POST https://api.agnes-ai.cn/v1/videos \
  -H "Authorization: Bearer $AGNES_API_KEY" -H "Content-Type: application/json" \
  -d '{"model":"agnes-video-2.5-flash","prompt":"...","mode":"text","seconds":"5","size":"720P","aspect_ratio":"16:9"}'

# 查询视频
curl -sS "https://api.agnes-ai.cn/agnesapi?video_id=VIDEO_ID&model_name=agnes-video-2.5-flash" \
  -H "Authorization: Bearer $AGNES_API_KEY"
```
