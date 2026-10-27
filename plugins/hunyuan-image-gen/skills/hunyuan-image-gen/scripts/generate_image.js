#!/usr/bin/env node
'use strict';
/*
 * 腾讯云 CloudBase 混元生图 —— 官方合规路径
 *
 * 通过 @cloudbase/node-sdk (>= 3.18.3) 初始化云开发环境，调用 AI 图像生成接口
 * （createImageModel("hunyuan-image")），模型 HY-Image-3.0-Plus-4090-Tob-v1.0（已内置 SDK）。
 *
 * 这是官方唯一认可的额度使用方式（消耗 CloudBase AI / Token Credits 资源包）。
 *
 * 两种运行方式：
 *  A) 本地执行（需密钥）：
 *       set TCB_ENV=your-env-id
 *       set TENCENT_SECRET_ID=AKID...
 *       set TENCENT_SECRET_KEY=XXXX
 *       npm install @cloudbase/node-sdk@">=3.18.3"
 *       node generate_image.js --prompt "赛博朋克风格的猫"
 *  B) 作为云函数部署（exports.main）：部署后由云端用环境凭证调用，无需密钥；
 *       调用时通过 event 传入 { prompt, size, ... }。
 */

const fs = require('fs');
const path = require('path');
const https = require('https');

let tcb = null;
try {
  tcb = require('@cloudbase/node-sdk');
} catch (e) {
  // 依赖缺失时不立即退出，便于 --help 等命令可用；实际生图前会再次校验
}

// 官方合规写法：createImageModel('hunyuan-image') 后 generateImage。
// 该能力组后端模型含 HY-Image-3.0-Plus-4090-Tob-v1.0，经网关映射；
// SDK 的 model 字段必须用组规范名 'hunyuan-image'（才能命中 images/generations 路由与同一 AI 生图额度包），
// 直接传 HY-Image-3.0-Plus-4090-Tob-v1.0 会 400。可用 HUNYUAN_MODEL 环境变量覆盖。
const MODEL = process.env.HUNYUAN_MODEL || 'hunyuan-image';

function parseArgs(argv) {
  const opts = {
    prompt: null,
    size: '1024x1024',
    version: undefined,
    negative: '',
    style: '',
    n: 1,
    revise: true,
    out: 'hunyuan_out',
    env: process.env.TCB_ENV || process.env.TCB_ENV_ID || '',
    secretId: process.env.TENCENT_SECRET_ID || '',
    secretKey: process.env.TENCENT_SECRET_KEY || '',
    save: false,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    switch (a) {
      case '--prompt':
        opts.prompt = next();
        break;
      case '--size':
        opts.size = next();
        break;
      case '--version':
        opts.version = next();
        break;
      case '--negative':
        opts.negative = next();
        break;
      case '--style':
        opts.style = next();
        break;
      case '--n':
        opts.n = parseInt(next(), 10) || 1;
        break;
      case '--no-revise':
        opts.revise = false;
        break;
      case '--out':
        opts.out = next();
        break;
      case '--env':
        opts.env = next();
        break;
      case '--secret-id':
        opts.secretId = next();
        break;
      case '--secret-key':
        opts.secretKey = next();
        break;
      case '--save':
        opts.save = true;
        break;
      case '--help':
      case '-h':
        printHelp();
        process.exit(0);
        break;
      default:
        if (!a.startsWith('--') && !opts.prompt) opts.prompt = a;
        break;
    }
  }
  return opts;
}

function printHelp() {
  console.log(`
腾讯云 CloudBase 混元生图（官方合规路径，@cloudbase/node-sdk >= 3.18.3）
用法：
  node generate_image.js --prompt "提示词" [选项]

选项：
  --prompt "文本"              正向提示词（必填）
  --model 默认 ${MODEL}
  --size 1024x1024|768x1024|...  输出尺寸，默认 1024x1024
  --version v1.8.1|v1.9       模型版本（可选）
  --negative "文本"           反向提示词（v1.9）
  --style "文本"              风格（v1.9）
  --n 1                       生成数量
  --no-revise                 关闭提示词改写（默认开启）
  --out <目录>                结果目录，默认 ./hunyuan_out
  --save                      url 模式下额外下载图片到本地
  --env <envId>               环境 ID（也可用 TCB_ENV 环境变量）
  --secret-id / --secret-key  本地运行时的密钥（或用 TENCENT_SECRET_ID/KEY 环境变量）
`);
}

function initApp(opts) {
  if (!tcb) {
    throw new Error('缺少依赖 @cloudbase/node-sdk，请先安装：npm install @cloudbase/node-sdk@">=3.18.3"');
  }
  if (!opts.env) {
    throw new Error('缺少环境 ID：请通过 --env 传入，或设置环境变量 TCB_ENV。');
  }
  const initOpts = { env: opts.env };
  // 本地运行时用密钥；云函数部署后由环境凭证自动注入，无需传密钥
  if (opts.secretId && opts.secretKey) {
    initOpts.secretId = opts.secretId;
    initOpts.secretKey = opts.secretKey;
  }
  return tcb.init(initOpts);
}

function downloadImage(url, dest) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return downloadImage(res.headers.location, dest).then(resolve, reject);
      }
      if (!res.statusCode || res.statusCode >= 400) {
        return reject(new Error('下载失败 HTTP ' + res.statusCode));
      }
      const ws = fs.createWriteStream(dest);
      res.pipe(ws);
      ws.on('finish', () => ws.close(() => resolve(dest)));
      ws.on('error', reject);
    });
    req.on('error', reject);
    req.end();
  });
}

async function generate(opts) {
  if (!opts.prompt) {
    throw new Error('缺少 --prompt 提示词。');
  }
  const app = initApp(opts);
  const imageModel = app.ai().createImageModel('hunyuan-image');

  const params = {
    model: MODEL,
    prompt: opts.prompt,
    size: opts.size,
    n: opts.n,
    revise: opts.revise,
  };
  if (opts.version) params.version = opts.version;
  if (opts.negative) params.negative_prompt = opts.negative;
  if (opts.style) params.style = opts.style;

  console.error('[hunyuan] 调用生图接口，model=' + MODEL + ' ...');
  const res = await imageModel.generateImage(params);

  const items = res && res.data ? res.data : [];
  const urls = items.map((d) => d && d.url).filter(Boolean);
  if (!urls.length) {
    throw new Error('未返回图片 URL，响应: ' + JSON.stringify(res));
  }

  urls.forEach((u, i) => {
    console.log(u);
    if (items[i] && items[i].revised_prompt) {
      console.error('[hunyuan] 改写后提示词: ' + items[i].revised_prompt);
    }
  });

  fs.mkdirSync(opts.out, { recursive: true });
  fs.writeFileSync(path.join(opts.out, 'urls.txt'), urls.join('\n') + '\n');

  if (opts.save) {
    for (let i = 0; i < urls.length; i++) {
      const fp = path.join(opts.out, `hunyuan_${i + 1}.png`);
      try {
        await downloadImage(urls[i], fp);
        console.error('[hunyuan] 已下载: ' + fp);
      } catch (e) {
        console.error('[hunyuan] 下载失败: ' + e.message);
      }
    }
  }
  console.error('[hunyuan] 完成，共 ' + urls.length + ' 张。');
  return res;
}

// A) 云函数入口：event 中传入参数
exports.main = async (event = {}, context) => {
  const opts = Object.assign(
    {
      prompt: null,
      size: '1024x1024',
      version: undefined,
      negative: '',
      style: '',
      n: 1,
      revise: true,
      out: '/tmp/hunyuan_out',
      env: process.env.TCB_ENV || (event && event.env) || '',
      secretId: '',
      secretKey: '',
      save: false,
    },
    event || {}
  );
  try {
    const res = await generate(opts);
    return { ok: true, urls: (res.data || []).map((d) => d.url).filter(Boolean) };
  } catch (e) {
    return { ok: false, error: e.message };
  }
};

// B) 本地 CLI 入口
if (require.main === module) {
  (async () => {
    const opts = parseArgs(process.argv.slice(2));
    try {
      await generate(opts);
    } catch (e) {
      console.error('[hunyuan] 失败: ' + e.message);
      process.exit(1);
    }
  })();
}
