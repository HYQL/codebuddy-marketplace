# 腾讯云 CloudBase 混元生图 API 参考（@cloudbase/node-sdk >= 3.18.3）

本文件为 `hunyuan-image-gen` 技能的权威参考，覆盖官方合规路径：通过 CloudBase Node SDK 调用 AI 图像生成接口。适用于"在云函数/Node 服务里间接生图、拿到图片 URL"的工作流。

## 依赖与初始化

```bash
npm install @cloudbase/node-sdk@">=3.18.3"
```

```js
const tcb = require('@cloudbase/node-sdk');

// 云函数内（环境凭证由云端自动注入，无需密钥）
const app = tcb.init({ env: '<YOUR_ENV_ID>' });

// 本地/普通 Node 服务（用密钥）
const app = tcb.init({
  env: '<YOUR_ENV_ID>',
  secretId: '<YOUR_SECRET_ID>',
  secretKey: '<YOUR_SECRET_KEY>',
});
```

> 图像生成仅在 **Node SDK** 中可用，Web JS SDK 与微信小程序 SDK 不支持。

## 生图接口 generateImage()

```js
const imageModel = app.ai().createImageModel('hunyuan-image');

const res = await imageModel.generateImage({
  model: 'hunyuan-image', // 能力组规范名（命中 images/generations 路由与 AI 生图额度包）；HY-Image-3.0-Plus-4090-Tob-v1.0 为组内后端模型，经网关映射
  prompt: 'A cute kitten playing on the grass',
  size: '1024x1024',
  // version: 'v1.9',
  // negative_prompt: 'blurry',   // v1.9 支持
  // style: '...',                // v1.9 支持
  // n: 1,
  // revise: true,
});

console.log(res.data[0].url);            // 图片 URL（有效期 24 小时）
console.log(res.data[0].revised_prompt); // 改写后的提示词（revise=true 时）
```

### 输入参数（HunyuanGenerateImageInput）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model` | string | 是 | 图像模型标识，**用能力组规范名 `hunyuan-image`**（命中 `images/generations` 路由与同一 AI 生图额度包）。`HY-Image-3.0-Plus-4090-Tob-v1.0` 是该组内置后端模型，经网关映射，不应直接作为 `model` 字段值传入（会落到默认 `images/ar/generations` 并返回 400）。可用 `HUNYUAN_MODEL` 环境变量覆盖 |
| `prompt` | string | 是 | 正向提示词 |
| `size` | string | 否 | 输出尺寸，默认 `1024x1024` |
| `version` | `"v1.8.1"` \| `"v1.9"` | 否 | 模型版本，默认 `v1.8.1` |
| `negative_prompt` | string | 否 | 反向提示词（v1.9） |
| `style` | string | 否 | 风格（v1.9） |
| `revise` | boolean | 否 | 是否改写提示词，默认 `true` |
| `n` | number | 否 | 生成数量，默认 1 |
| `footnote` | string | 否 | 水印文字，最多 16 字符 |
| `seed` | number | 否 | 随机种子，范围 `[1, 4294967295]` |

### 输出结构（HunyuanGenerateImageOutput）

```ts
interface HunyuanGenerateImageOutput {
  id: string;
  created: number;
  data: Array<{
    url: string;             // 图片 URL（24 小时有效）
    revised_prompt?: string; // 改写后的提示词
  }>;
}
```

## 云函数部署与 exports.main 契约

脚本内置 `exports.main`，可直接作为事件型云函数部署（无需密钥，由环境凭证调用）：

```js
exports.main = async (event = {}, context) => {
  // event 即下方 opts 的同名字段：{ prompt, size, version, negative, style, n, revise, out, env }
  const res = await generate(opts);
  return { ok: true, urls: res.data.map(d => d.url) };
};
```

部署要点：
- 云函数运行时选 **Node.js ≥ 14**，依赖安装 `@cloudbase/node-sdk >= 3.18.3`（在云函数 package.json 声明，或用云端依赖安装）。
- **超时设为 900s**（生图耗时较长；HTTP 函数网关上限 60s，故生图类用事件型云函数，不要走 60s 受限的 HTTP 网关）。
- 部署后通过 MCP `manageFunctions(action="invokeFunction")` 或控制台/SDK 触发，传入 `{ prompt, size, ... }` 即可。

## 两步预检（消耗 CloudBase AI 额度前的强制校验）

生图消耗 CloudBase AI（Token Credits）资源包，调用前必须完成：

**预检 ① — 额度包（Token Credits）：**
```
callCloudApi(service="tcb", action="DescribeEnvPostpayPackage", params={ EnvId })
```
通过条件：`envPostpayPackageInfoList` 中存在 `postpayPackageId` 以 `pkg_hunyuan_ai_image_` 开头（**生图 10 万张资源包**，即"一万额度"）或以 `pkg_hunyuan_token_` 开头（Token Credits 统一额度），且 `status` 不在 `[3,4]`。本场景关键校验生图包 `pkg_hunyuan_ai_image_*`（实际观测：`pkg_hunyuan_ai_image_la_inspire_100k`）。
不通过 → 返回购买链接（替换 `{envId}`）：
`https://buy.cloud.tencent.com/lowcode?buyType=resPack&envId={envId}&resourceType=token`

**预检 ② — 图像模型就绪：**
```
callCloudApi(service="tcb", action="DescribeAIModels", params={ EnvId })
```
确认 `hunyuan-image` 能力已就绪（`HY-Image-3.0-Plus-4090-Tob-v1.0` 经 `model` 字段指定，SDK 内置）。未就绪时用 `DescribeManagedAIModelList` 取权威目录 + 计费，再以 `UpdateAIModel`（`Status:1`，`Models` 全量替换）启用。

> 参数 PascalCase；`InvalidParameter` 时退化为 camelCase（`envId`）。

## 错误处理

- `res.data` 为空或 `url` 缺失 → 视为失败，检查提示词合规性（涉政/违规内容会被拒）。
- 额度不足 → 引导用户在 CloudBase 控制台续费 AI 资源包。
- SDK 抛错多为鉴权/环境配置问题：确认 `env` 正确、本地调试密钥有效、SDK 版本 ≥ 3.18.3。
- 已成功生图才计费；参数/鉴权类失败（4xx）通常不扣额度。

## 与"直连混元生图 REST API"的区别

直连腾讯云 `hunyuan` 服务（`SubmitHunyuanImageJob`/`QueryHunyuanImageJob`，自签 TC3）属另一套额度体系（直接的混元生图资源包），**不是** CloudBase AI 资源的官方使用方式。本技能坚持 CloudBase Node SDK 通道以匹配用户持有的合规额度。

### 实战要点（已验证）

- **只能用云开发 SDK 通道**：在"小程序成长计划"等套餐下，AI 网关仅放行云开发 SDK 通道（`app.ai().createImageModel("hunyuan-image").generateImage(...)`，运行于云函数、由环境凭证调用）。用 `fetch` 直接带 Bearer Token 打 `/v1/ai/...` 会返回 **403 `AI_CHANNEL_NOT_ALLOWED`**："小程序成长计划仅支持小程序 SDK 和云开发 SDK 调用"。故必须用 SDK 的 `generateImage`，不可裸 HTTP 调用。
- **model 用 `hunyuan-image`**：该能力组后端模型含 `HY-Image-3.0-Plus-4090-Tob-v1.0`（经网关映射），`model` 字段传 `hunyuan-image` 才命中正确路由与额度包；直接传 `HY-Image-3.0-Plus-4090-Tob-v1.0` 会落到默认 `images/ar/generations` 并返回 400。
- **部署后调用的传播延迟**：`updateFunctionCode` 后立刻 `invokeFunction` 可能仍跑旧代码（差一版），再调用一次即可命中新代码。
