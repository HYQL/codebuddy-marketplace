# CodeBuddy Marketplace（社区市场）

本仓库是一个 [CodeBuddy 插件市场（Plugin Marketplace）](https://www.codebuddy.ai/docs/zh/cli/plugin-marketplaces)，用于分发和管理 CodeBuddy 扩展插件。市场名：**`admin-marketplace`**。

## 市场内容

| 插件 | 版本 | 说明 |
|---|---|---|
| `agnes-media` | 1.3.0 | Agnes AI 图像与视频生成技能，支持国内/国外双节点，完成后输出远程媒体地址，`--model` 可切换模型版本，图生视频一步流 / 任务恢复 / 429 自动退避（详见下文） |
| `agnes-media-flash` | 1.1.0 | Agnes AI 图像与视频生成技能（agnes-image-2.5-flash / agnes-video-2.5-flash），支持文生图、图生图、多图合成、文生视频、首尾帧与参考图音频生视频（详见下文） |

## 安装插件

### 方式 1：CodeBuddy Code CLI 插件市场安装（推荐，可自动更新）

先添加市场，再安装插件：

```
/plugin marketplace add HYQL/codebuddy-marketplace
/plugin install agnes-media@admin-marketplace
/plugin install agnes-media-flash@admin-marketplace
/reload-plugins
```

- 安装后技能以命名空间加载：`/agnes-media:agnes-media` 与 `/agnes-media-flash:agnes-media-flash`
- 也可在 CodeBuddy Code 中运行 `/plugin`，进入「发现」标签页交互式安装（默认用户作用域，支持项目/本地作用域）

### 方式 2：手动拷贝到技能目录（IDE / 无 CLI 用户）

```powershell
git clone https://github.com/HYQL/codebuddy-marketplace
Copy-Item -Recurse codebuddy-marketplace\plugins\agnes-media\skills\agnes-media $env:USERPROFILE\.codebuddy\skills\
Copy-Item -Recurse codebuddy-marketplace\plugins\agnes-media-flash\skills\agnes-media-flash $env:USERPROFILE\.codebuddy\skills\
```

重启 CodeBuddy 后技能自动可用。项目级共享则拷到项目根目录 `.codebuddy\skills\` 随仓库提交。

### 安装前提（任一方式都需）

1. **Python 3.10+**（脚本仅标准库）
2. **Agnes API Key**：在 <https://platform.agnes-ai.cn>（国内）创建，配置方式见下文「API Key 配置」

### 常用管理命令


```
/plugin marketplace list            # 列出已配置市场
/plugin marketplace update admin-marketplace   # 刷新插件列表
/plugin disable agnes-media@admin-marketplace  # 禁用（不卸载）
/plugin uninstall agnes-media@admin-marketplace
/plugin disable agnes-media-flash@admin-marketplace
/plugin uninstall agnes-media-flash@admin-marketplace
```

## agnes-media 技能说明

调用 [Agnes AI](https://platform.agnes-ai.cn) 官方模型生成媒体内容（模型归属 Agnes，Sapiens AI 旗下）：

| 能力 | 模型（请求 `model` 字段） | 说明 |
|---|---|---|
| 文生图 / 图生图 / 多图合成 | `agnes-image-2.5-flash` | 同步调用，1K–4K，8 种宽高比 |
| 文生视频 / 首尾帧 / 参考图音频生视频 | `agnes-video-2.5-flash` | 异步任务（建任务 → 轮询 → 下载），720P，4–12s |

包含零依赖 Python 脚本（仅标准库，需 Python 3.10+）与完整 API 参考文档。

### API 节点（国内 / 国外）

| 节点 | 服务 host | 切换方式 |
|---|---|---|
| `cn`（默认） | `https://api.agnes-ai.cn` | 默认值，无需指定 |
| `com` | `https://api.agnes-ai.com` | 脚本传 `--node com`；或设环境变量 `AGNES_BASE_URL`（如 `https://api.agnes-ai.com`，带/不带 `/v1` 均可） |

走 `models.json` 回退取 Key 时，节点自动按该条目 url 的 host 配对，避免跨节点鉴权失败。

### API Key 配置

脚本按以下优先级自动解析 Key，通常无需手动配置：

1. `--api-key` 参数
2. 环境变量 `AGNES_API_KEY`
3. `~/.codebuddy/models.json` 中 `url` 以 `https://api.agnes-ai.cn` 或 `https://api.agnes-ai.com` 开头的自定义模型的 `apiKey`

三者都缺失时，请到 <https://platform.agnes-ai.cn> 控制台创建 Key 并设置：

```powershell
setx AGNES_API_KEY "sk-你的Key"
```

### 使用方式

在 CodeBuddy 中直接用自然语言触发，例如：

> 用 Agnes 生成一张图：玩耍的熊猫，2K 竖版
> 用 Agnes 生成一段视频：雨夜的城市街道，8 秒
> 基于「竹林里的熊猫」画面生成 4 秒视频（图生视频一步流）

常用脚本参数（详见技能内 `SKILL.md`）：

- `--from-image-prompt 提示词`：**图生视频一步流**——先文生图拿 Agnes 远程地址作首帧（keyframe），无需自备公共素材 URL
- `--resume VIDEO_ID` / `--status VIDEO_ID`：轮询超时或进程中断后，对已有任务继续下载或查状态，**不要重复创建任务**
- `--model 模型名`：模型升级（如 3.0）后直接传新模型名，无需改代码

注意：免费额度下 Agnes 接口有限流（查询任务可能 429），脚本轮询遇 429 会自动退避（2×间隔）重试，任务不会丢；轮询间隔默认 10s，请勿调小。

## agnes-media-flash 技能说明

调用 [Agnes AI](https://platform.agnes-ai.cn) 官方 Flash 模型生成媒体内容（模型归属 Agnes，Sapiens AI 旗下）：

| 能力 | 模型（请求 `model` 字段） | 说明 |
|---|---|---|
| 文生图 / 图生图 / 多图合成 | `agnes-image-2.5-flash` | 同步调用，8 种宽高比 |
| 文生视频 / 首尾帧 / 参考图音频生视频 | `agnes-video-2.5-flash` | 异步任务（建任务 → 轮询 → 下载），720P，4–12s |

包含零依赖 Python 脚本（仅标准库，需 Python 3.10+）与完整 API 参考文档（`references/api-spec.md`）。

### API Key 配置

脚本按以下优先级自动解析 Key，通常无需手动配置：

1. `--api-key` 参数
2. 环境变量 `AGNES_API_KEY`
3. `~/.codebuddy/models.json` 中 `url` 以 `https://api.agnes-ai.cn` 开头的自定义模型的 `apiKey`

### 使用方式

在 CodeBuddy 中直接用自然语言触发，例如：

> 用 Agnes 生成一张图：玩耍的熊猫，2K 竖版
> 用 Agnes 生成一段视频：雨夜的城市街道，8 秒
> 给这张图做图生视频：竹林里的熊猫

## 版本与更新

- 市场/插件版本以 `marketplace.json` 与 `plugin.json` 中的 `version`（语义化版本）跟踪
- 更新插件内容后重新推送本仓库，安装方执行 `/plugin marketplace update admin-marketplace` 同步，并 `/reload-plugins` 生效

## 安全说明

插件和 CodeBuddy 市场是高度受信任的组件，会以你的用户权限执行代码。安装前请审查 `plugins/` 目录中的脚本内容（本市场含 `agnes-media` 与 `agnes-media-flash` 两个插件，每个插件各含两个仅调用 Agnes API 的 Python 标准库脚本，不含其他可执行逻辑）。

## 许可证

`agnes-media` / `agnes-media-flash` 插件：MIT（见 `marketplace.json` 中 `license` 字段）。
