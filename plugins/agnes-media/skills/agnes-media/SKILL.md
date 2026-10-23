---
name: agnes-media
version: 1.3.0
display_name: Agnes AI 图像与视频生成
display_name_en: Agnes AI Image & Video Generation
description: Agnes AI 图像与视频生成。调用 Agnes 官方模型 Agnes Image 2.5 Flash（model=agnes-image-2.5-flash，文生图/图生图/多图合成）与 Agnes Video 2.5 Flash（model=agnes-video-2.5-flash，文生视频/首尾帧/参考图音频生视频）API。当用户要求使用 Agnes 生成图片、生成视频、图生图、图生视频、AI 绘画（Agnes）时触发。
description_zh: Agnes AI 图像与视频生成技能。调用 Agnes 官方模型 Agnes Image 2.5 Flash 与 Agnes Video 2.5 Flash，支持文生图、图生图、多图合成、文生视频、首尾帧视频、参考图音频生视频，以及图生视频一步流与任务恢复。当用户要求使用 Agnes 生成图片、生成视频、图生图、图生视频或 AI 绘画时触发。
description_en: Agnes AI image and video generation skill. Calls Agnes official models Agnes Image 2.5 Flash and Agnes Video 2.5 Flash, supporting text-to-image, image-to-image, multi-image composition, text-to-video, keyframe video, and reference image/audio-to-video, plus one-shot image-to-video and task resume. Triggers when the user asks to generate images, videos, image-to-image, video-to-video, or AI painting with Agnes.
---

# Agnes Media（图像 + 视频生成）

Agnes AI 官方 API（https://platform.agnes-ai.cn 获取 Key，Bearer 认证）。支持两个节点：

| 节点 | 服务 host | 说明 | 切换方式 |
|---|---|---|---|
| `cn`（默认） | `https://api.agnes-ai.cn` | 国内节点 | 默认值，无需指定 |
| `com` | `https://api.agnes-ai.com` | 国外节点 | 脚本传 `--node com`，或设环境变量 `AGNES_BASE_URL`（如 `https://api.agnes-ai.com`，带/不带 `/v1` 均可） |

**模型归属**：本 Skill 使用的模型均属于 **Agnes AI**（Sapiens AI 旗下，国内节点 agnes-ai.cn / 国外节点 agnes-ai.com）：

| 能力 | 模型名称（请求 `model` 字段值） | 端点 |
|---|---|---|
| 图像生成/编辑 | `agnes-image-2.5-flash` | `POST /v1/images/generations` |
| 视频生成 | `agnes-video-2.5-flash` | `POST /v1/videos` + `GET /agnesapi` 轮询 |

调用结果（回复用户时）应说明所用模型为 Agnes 的 `agnes-image-2.5-flash` / `agnes-video-2.5-flash`。

## 前置条件

API Key 解析优先级（脚本自动处理，通常无需手动配置）：

1. `--api-key` 参数
2. 环境变量 `AGNES_API_KEY`
3. `~/.codebuddy/models.json` 中 `url` 以 `https://api.agnes-ai.cn` 或 `https://api.agnes-ai.com` 开头的自定义模型的 `apiKey`（插件可直接读取该文件）

三者都缺失时脚本会报错提示；此时向用户索要 Key 并设置：`setx AGNES_API_KEY "sk-..."`（新开终端生效）。

**节点选择**（两个脚本通用）：

- `--node cn|com`（默认 cn）：显式指定国内/国外节点
- 环境变量 `AGNES_BASE_URL` 优先级最高：如 `AGNES_BASE_URL=https://api.agnes-ai.com`（带/不带 `/v1` 均可）
- 走 `models.json` 回退时：条目与所选节点一致则跟随该条目 host；条目属于另一节点则改用所选节点的默认 Base，保证 Key 与节点配对

## 图像生成 / 编辑（Agnes Image 2.5 Flash，同步）

运行脚本：

```bash
python scripts/agnes_image.py "提示词" [选项]
```

- `--size 1K|2K|3K|4K`（默认 1K，也接受 `1024x768` 等精确写法，非标准尺寸会自动映射）
- `--ratio 1:1|3:4|4:3|16:9|9:16|2:3|3:2|21:9`（默认 1:1）
- `--image <URL或本地文件>` 可重复；图生图/多图合成时必填。本地文件会自动转成 Data URI（Base64）；也可传公共 HTTPS URL。最多传 5 张（前 3 张免费）
- `--b64` 以 Base64 形式取图并直接落盘；默认取 URL 后下载
- `--out 文件路径` 输出路径（默认 `agnes_out/image_<时间戳>.png`）
- `--model 模型名`（默认 `agnes-image-2.5-flash`；官方发布 3.0 后可直接传新模型名，无需改脚本）

示例：

```bash
python scripts/agnes_image.py "清晨山谷中的悬浮城市，电影感写实" --size 2K --ratio 16:9 --out city.png
python scripts/agnes_image.py "把主体换成橙色，保持构图" --image https://example.com/in.png --size 1K
```

## 视频生成（Agnes Video 2.5 Flash，异步任务）

运行脚本（内部完成建任务 → 轮询 → 下载）：

```bash
python scripts/agnes_video.py "提示词" [选项]
```

- `--mode text|keyframe|reference`（默认 text；text 模式禁止传任何媒体字段）
- `--seconds 4~12`（字符串，默认 5）；`--aspect-ratio`（默认 16:9）；分辨率仅支持 720P
- `--first-frame URL` / `--last-frame URL`：keyframe 模式，至少传一个；两个 URL 必须可公开访问
- `--images URL`（可重复，最多 5 张）/ `--audios URL`（可重复，最多 3 段）：reference 模式，prompt 中用 `<Picture N>`、`<Audio N>` 指代素材；videos 参考不支持
- `--out 文件路径`（默认 `agnes_out/video_<时间戳>.mp4`）；`--poll-interval`（默认 10s；429 会自动退避重试，勿调小）；`--timeout`（默认 600s）
- `--model 模型名`（默认 `agnes-video-2.5-flash`；官方发布 3.0 后可直接传新模型名，轮询 `model_name` 会自动跟随；无需改脚本）
- `--from-image-prompt 提示词`（可选配 `--from-image-model`，默认 `agnes-image-2.5-flash`）：**图生视频一步流**——先调图像接口生成关键帧图，其 Agnes 远程地址自动作为 `first_frame`（自动进入 keyframe 模式），无需自备公共素材 URL；也可与显式 `--first-frame` 并用（显式优先，跳过生成）
- `--resume VIDEO_ID`：跳过创建，对已有任务继续轮询并下载（轮询超时/中断后恢复用；keyframe/reference 任务需同时传 `--mode`）
- `--status VIDEO_ID`：只查询任务状态/进度与远程地址，不下载

示例：

```bash
python scripts/agnes_video.py "雨后未来城市街道，霓虹倒影，银色跑车驶过" --seconds 5 --aspect-ratio 16:9
python scripts/agnes_video.py "角色从首帧姿态转身走向窗边" --mode keyframe --first-frame https://example.com/f.png --last-frame https://example.com/l.png
python scripts/agnes_video.py "以 <Picture 1> 的角色在花田奔跑" --mode reference --images https://example.com/char.png
# 图生视频一步流（本地没有可用素材 URL 时首选）：
python scripts/agnes_video.py "熊猫在竹林里打滚" --from-image-prompt "可爱熊猫在竹林，写实" --seconds 4
# 轮询超时/中断后恢复（勿重新建任务）：
python scripts/agnes_video.py --resume task_XXX
python scripts/agnes_video.py --status task_XXX
```

> 视频参考图/音频必须是可公开访问的 URL，且任务完成前保持有效。本地文件无法直接作为视频参考（不像图片可转 Data URI）——需要"基于某画面出视频"时用 `--from-image-prompt` 一步流（先文生图拿远程 URL，再作首帧）。

## 规则与易错点（必须遵守）

- 图像 API 的 `response_format` 必须放在 `extra_body` 内，**不要**放顶层；图生图**不需要**传 `tags: ["img2img"]`
- 视频 Flash 模型 `size` 只能传 `"720P"`（字符串），传其他值返回 HTTP 400；`n` 只能为 1
- 模式字段互斥：text 不带媒体；keyframe 不带 images/audios/videos；reference 不带 first_frame/last_frame/videos
- 图像为同步调用（耗时数秒到数十秒，脚本超时默认 300s）；视频为异步任务，完成前反复轮询，勿重复创建任务
- 成功后脚本会额外打印**远程地址**（`[agnes-image] 远程地址: <url>` / `[agnes-video] 远程地址: <url>`，Agnes CDN 媒体链接）；该远程地址有有效期，交付用户时优先给本地文件，远程链接仅作补充（b64 模式无远程 URL）
- 免费额度下视频查询接口有频率限制（429"查询过于频繁"）：脚本轮询遇 429 会自动退避（2×间隔）重试，任务不会丢；间隔默认 10s 勿调小到 2s
- 轮询超时或进程被中断后，任务仍在服务端运行：用 `--resume <video_id>` 继续轮询下载、`--status <video_id>` 查状态，**不要重新建任务**
- 校验失败（400）不产生费用；鉴权失败（401/403）检查 Key 与账户余额

## 详细参考

完整参数表、像素映射表、响应字段、curl 示例、定价与错误处理见 `references/api-spec.md`。
