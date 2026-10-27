---
name: hunyuan-image-gen
description: 腾讯云 CloudBase 混元生图（模型 HY-Image-3.0-Plus-4090-Tob-v1.0，已内置 @cloudbase/node-sdk）。当用户要求通过腾讯云/CloudBase 生图、调用混元图像模型、或"在云函数里用 Node SDK 间接生图、拿到图片 URL"时触发。提供官方合规路径：@cloudbase/node-sdk 3.18.3 及以上版本初始化云开发环境，调用 AI 图像生成接口消耗 CloudBase AI 额度。
---

# 腾讯云 CloudBase 混元生图（官方合规路径）

本技能封装了**官方唯一认可的额度使用方式**：在云函数中通过 `@cloudbase/node-sdk >= 3.18.3` 初始化云开发环境，再调用 AI 能力接口完成生图请求。模型 `HY-Image-3.0-Plus-4090-Tob-v1.0` 已内置在该 SDK 中。

> ⚠️ 不要改用直连腾讯云混元生图 REST API 的自签脚本——那不是官方认可的额度通道。务必走 `@cloudbase/node-sdk` 的 `app.ai().createImageModel("hunyuan-image").generateImage(...)`。

## 前置条件

1. **CloudBase 环境**：拥有一个云开发环境（envId）。
2. **AI 额度资源包**：账号已购买/开通 CloudBase AI（Token Credits）资源包——这是生图消耗的额度（用户的"一万额度"在此）。
3. **SDK 版本**：`@cloudbase/node-sdk >= 3.18.3`（生图能力从该版本起稳定内置，旧版本可能缺模型）。
4. **本地 Node.js** ≥ 14（若本地调试执行脚本）。

## 强制两步预检（任何调用前必做）

生图消耗 CloudBase AI 资源包，必须先用 MCP 工具确认额度与模型可用，再写代码。

**第 0 步 — 取环境 ID：**
```
queryEnv(action=info)  → 读取 EnvId
```

**预检 ① — 额度包（Token Credits）：**
```
callCloudApi(service="tcb", action="DescribeEnvPostpayPackage", params={ EnvId })
```
满足全部条件方可继续：返回的 `envPostpayPackageInfoList` 中存在 `postpayPackageId` 以 `pkg_hunyuan_ai_image_` 开头（**生图 10 万张资源包**，即用户的"一万额度"）或以 `pkg_hunyuan_token_` 开头（Token Credits 统一额度），且 `status` 不在 `[3,4]`（过期/停用）。本场景关键校验 **生图包 `pkg_hunyuan_ai_image_*`**（实际观测到 `pkg_hunyuan_ai_image_la_inspire_100k`）。
- 不满足 → **停止写代码**，返回购买链接（把 `{envId}` 替换为真实值）：
  `https://buy.cloud.tencent.com/lowcode?buyType=resPack&envId={envId}&resourceType=token`

**预检 ② — 图像模型就绪：**
```
callCloudApi(service="tcb", action="DescribeAIModels", params={ EnvId })
```
确认 `hunyuan-image` 能力组 `Status:1`（已启用），其模型列表含 `HY-Image-3.0-Plus-4090-Tob-v1.0`。注意：`HY-Image-3.0-Plus-4090-Tob-v1.0` 是**组内后端模型**（经网关映射），SDK 调用时 `model` 字段传组规范名 `hunyuan-image` 即可命中同一生图额度包（详见下方"实战已验证要点"）。若未启用，列出来自 `DescribeManagedAIModelList` 的权威目录与计费后，用 `UpdateAIModel`（`Status:1`，`Models` 全量替换）启用。

> 参数 PascalCase；若 `InvalidParameter` 则退化为 camelCase（`envId`）。

## 工作流（CodeBuddy 调用时遵循）

1. **预检**：按上文跑 queryEnv → DescribeEnvPostpayPackage → DescribeAIModels，确认额度与模型就绪。
2. **写/复用脚本**：使用本技能 `scripts/generate_image.js`（已就绪，封装了 SDK 初始化与 `generateImage` 调用，勿重写）。
3. **执行**：
   - **本地调试**：设 `TCB_ENV` + `TENCENT_SECRET_ID/KEY`，`node scripts/generate_image.js --prompt "..."`。
   - **正式使用（推荐）**：将 `generate_image.js` 作为云函数部署（含 `exports.main`），由云端环境凭证调用，无需密钥；详情见 `references/api-spec.md` 的"云函数部署"。
4. **取回结果**：`generateImage` 返回 `res.data[].url`（**有效期 24 小时**），脚本打印 URL 并写入 `<out>/urls.txt`。把 URL 反馈给用户查看。

> 生图耗时数秒到数十秒，单次消耗高于文本。云函数超时务必设为 **900s**（HTTP 函数网关 60s 上限，故生图类用事件型云函数 + 异步查询/回调，不要走 60s 受限的 HTTP 网关）。

## 运行示例

```bash
# 本地调试：赛博朋克风格的猫
set TCB_ENV=your-env-id
set TENCENT_SECRET_ID=AKID...
set TENCENT_SECRET_KEY=XXXX
node "{baseDir}/scripts/generate_image.js" --prompt "一只赛博朋克风格的猫，霓虹灯光，电影感"

# 指定尺寸与反向提示词
node "{baseDir}/scripts/generate_image.js" --prompt "清晨山谷中的悬浮城市" --size 768x1024 --negative "模糊, 畸变" --save --out ./output
```

`{baseDir}` 为本技能目录绝对路径（CodeBuddy 自动解析）。

## 参数速查（generate_image.js）

| 参数 | 说明 | 默认 |
|---|---|---|
| `--prompt` | 正向提示词（必填） | — |
| `--model` | 组规范名 `hunyuan-image`（内置后端模型为 `HY-Image-3.0-Plus-4090-Tob-v1.0`，经网关映射；可用 `HUNYUAN_MODEL` 环境变量覆盖） | `hunyuan-image` |
| `--size` | 输出尺寸，如 `1024x1024` `768x1024` | `1024x1024` |
| `--version` | 模型版本 `v1.8.1`/`v1.9`（可选） | SDK 默认 |
| `--negative` | 反向提示词（v1.9） | 空 |
| `--style` | 风格（v1.9） | 空 |
| `--n` | 生成数量 | 1 |
| `--no-revise` | 关闭提示词改写（默认开启） | 开启 |
| `--out` | 结果目录 | `./hunyuan_out` |
| `--save` | url 模式下额外下载图片到本地 | 关闭 |
| `--env` / `TCB_ENV` | 环境 ID | — |
| `--secret-id`/`--secret-key` 或 `TENCENT_SECRET_ID`/`KEY` | 本地调试密钥 | 环境变量 |

## 易错点 / 注意事项（必须遵守）

- **唯一合规通道**：必须走 `@cloudbase/node-sdk` 的 `createImageModel("hunyuan-image").generateImage`，不得直连腾讯云混元生图 REST API（不走该额度通道、不被官方认可）。
- **SDK 版本**：`@cloudbase/node-sdk >= 3.18.3`；本地先 `npm install @cloudbase/node-sdk@">=3.18.3"`。低版本可能无此内置模型。
- **额度**：消耗 CloudBase AI（Token Credits）资源包，与文本共用；已成功生图才计费，调用前务必完成预检 ①②。
- **URL 有效期**：`res.data[].url` 仅 **24 小时**有效。需长期保存时务必 `--save` 下载到本地或转存云存储。
- **密钥**：本地调试用环境变量注入，勿硬编码进脚本；云函数部署后由环境凭证自动注入，无需密钥。
- **超时**：云函数超时设为 900s；生图类优先用事件型云函数，避免 60s HTTP 网关限制。
- **地域/环境**：`--env` 必须指向已开通 AI 额度的环境。

## 实战已验证要点（重要）

- **只能用云开发 SDK 通道**：在"小程序成长计划"等部分套餐下，AI 网关仅允许**云开发 SDK 通道**（`app.ai().createImageModel("hunyuan-image").generateImage(...)`，运行于云函数内，由环境凭证调用）。用 `fetch` 直接带 Bearer Token 打 `/v1/ai/...` 会被拒，返回 **403 `AI_CHANNEL_NOT_ALLOWED`**："小程序成长计划仅支持小程序 SDK 和云开发 SDK 调用"。因此**必须用 SDK 的 `generateImage`，不能自签/裸 HTTP 调用**。
- **model 字段用组规范名 `hunyuan-image`**：`generateImage({ model: "hunyuan-image", ... })` 才能命中正确的 `images/generations` 路由与同一 AI 生图额度包。`HY-Image-3.0-Plus-4090-Tob-v1.0` 是该能力组的**后端模型**（经网关映射），直接作为 `model` 字段值传入会落到默认 `images/ar/generations` 并返回 400。脚本默认 `hunyuan-image`（可用 `HUNYUAN_MODEL` 覆盖）。
- **部署后调用的传播延迟**：`updateFunctionCode` 后立刻 `invokeFunction` 可能仍跑旧代码（差一版）。若结果形态异常，再调用一次即可命中新代码。

## 与"直连混元生图 REST API"的区别

直连腾讯云 `hunyuan` 服务的 `SubmitHunyuanImageJob`/`QueryHunyuanImageJob`（自签 TC3）属于另一套额度体系（直接的混元生图资源包），**不是** CloudBase AI 资源的官方使用方式。本技能面向"CloudBase 环境 + @cloudbase/node-sdk + CloudBase AI 额度"的场景——即用户所持有的合规通道。

## 详细参考

SDK 图像接口字段、`exports.main` 云函数契约、云函数部署步骤、预检 MCP 调用细节见 `references/api-spec.md`。
