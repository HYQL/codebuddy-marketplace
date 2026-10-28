#!/usr/bin/env node
/**
 * git-file-up — 把本地文件上传到 GitHub 支持附件端点，返回云端 URL。
 *
 * 用法:
 *   node upload.mjs <file> [file...]
 *   node upload.mjs --help
 *
 * 环境变量（都可选）:
 *   UPLOAD_ENDPOINT     默认 https://github.zendesk.com/api/v2/uploads.json
 *   UPLOAD_MIN_INTERVAL_MS  两次请求最小间隔，默认 0 = 按 ratelimit 响应头自适应
 *   UPLOAD_RESERVE      配额保留水位，默认 200（remaining 低于此值才等 reset）
 *   UPLOAD_RETRIES      429/5xx 重试次数，默认 4
 *   UPLOAD_TIMEOUT_MS   单次请求超时，默认 0 = 按体积自适应
 *   UPLOAD_ASSUMED_BPS  自适应超时用的保守上传带宽，默认 40000 (40KB/s)
 *
 * 输出: 每个文件一行 JSON  {"ok":true,"file":...,"url":...,"bytes":...,"token":...,"expiresAt":...,"expiresInSec":...}
 *       失败      {"ok":false,"file":...,"error":...,"status":...}
 * 退出码: 全部成功 0，任一失败 1。
 *
 * 重要: 该端点是临时文件通道，URL 60 分钟后失效（响应里 upload.expires_at）。
 *       拿到 URL 就要立刻用；需要长期托管先转存到对象存储。
 *
 * 设计: 单并发串行队列 + 按 ratelimit 响应头自适应等待 + 指数退避（尊重 Retry-After）。
 *       实测该端点配额约 2500 点 / 60s（约 250 次/分钟），单连接带宽 ~80KB/s，
 *       带宽才是真瓶颈，固定间隔纯空转（10 个文件 1500ms 间隔 22.3s vs 0 间隔 9.5s）。
 *       ponytail: 全局串行，吞吐优先场景再按目标端点的并发额度改并发池。
 */
import { readFile, stat } from 'node:fs/promises';
import { basename, extname, resolve } from 'node:path';

const ENDPOINT = process.env.UPLOAD_ENDPOINT || 'https://github.zendesk.com/api/v2/uploads.json';
const MIN_INTERVAL = Number(process.env.UPLOAD_MIN_INTERVAL_MS ?? 0);
/** remaining 低于此值就等 reset，留出余量给同 IP 的其他进程。 */
const RESERVE = Number(process.env.UPLOAD_RESERVE ?? 200);
const RETRIES = Number(process.env.UPLOAD_RETRIES ?? 4);
/** 0 = 按体积自适应。本机实测该端点上传带宽约 80KB/s。 */
const TIMEOUT_ENV = Number(process.env.UPLOAD_TIMEOUT_MS ?? 0);
const MAX_BYTES = 50 * 1024 * 1024; // 端点硬上限 50MB
const ASSUMED_BPS = Number(process.env.UPLOAD_ASSUMED_BPS ?? 40000); // 保守带宽假设

/** 按体积估算超时：保守带宽 + 60s 余量。 */
function timeoutFor(bytes) {
  if (TIMEOUT_ENV > 0) return TIMEOUT_ENV;
  return Math.max(120000, Math.ceil(bytes / ASSUMED_BPS) * 1000 + 60000);
}

const MIME = {
  '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png',
  '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.avif': 'image/avif',
  '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.webm': 'video/webm',
  '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.m4a': 'audio/mp4',
  '.pdf': 'application/pdf', '.zip': 'application/zip',
  '.txt': 'text/plain', '.md': 'text/markdown', '.json': 'application/json',
  '.csv': 'text/csv', '.html': 'text/html', '.log': 'text/plain',
};
const mimeOf = (p) => MIME[extname(p).toLowerCase()] ?? 'application/octet-stream';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const jitter = (ms) => ms + Math.floor(Math.random() * Math.min(800, Math.max(1, ms * 0.3)));

/** 最近一次响应里的限流状态，用于决定下一次请求要不要等。 */
const rate = { remaining: Infinity, resetAt: 0 };

/** 从响应头更新限流状态。端点用 ratelimit-remaining / ratelimit-reset（秒）。 */
function trackRateLimit(res) {
  const remaining = Number(res.headers.get('ratelimit-remaining'));
  const reset = Number(res.headers.get('ratelimit-reset'));
  if (Number.isFinite(remaining)) rate.remaining = remaining;
  if (Number.isFinite(reset)) rate.resetAt = Date.now() + reset * 1000;
}

/**
 * 发请求前的闸门：配额够就直接过，不够就等到 reset。
 * 端点实际额度约 250 次/分钟，远高于单连接带宽能跑出的吞吐，所以正常情况下不等待。
 */
async function rateGate() {
  if (MIN_INTERVAL > 0) await sleep(jitter(MIN_INTERVAL));
  if (rate.remaining > RESERVE) return;
  const wait = rate.resetAt - Date.now();
  if (wait > 0) {
    process.stderr.write(`[rate] remaining=${rate.remaining} <= reserve=${RESERVE}，等待 ${Math.ceil(wait / 1000)}s 到配额重置\n`);
    await sleep(wait + 250);
  }
  rate.remaining = Infinity; // 重置窗口已过，乐观放行，让响应头重新校准
}

/** 取 endpoint 返回里的 URL，兼容不同字段命名。 */
function extractUrl(body) {
  if (!body || typeof body !== 'object') return undefined;
  const upload = body.upload ?? body;
  const att = upload.attachment
    ?? upload.attachments?.[0]
    ?? body.attachment
    ?? body.file
    ?? body;
  return att?.content_url ?? att?.mapped_content_url ?? att?.url
    ?? body.content_url ?? body.url;
}

/** 取 endpoint 返回里的 token，便于后续复用。 */
function extractToken(body) {
  return body?.upload?.token ?? body?.token;
}

/**
 * 取附件过期时间（UTC ISO）。实测该通道是临时文件通道，有效期 60 分钟。
 * @returns {{ expiresAt?: string, expiresInSec?: number }} 过期信息。
 */
function extractExpiry(body) {
  const raw = body?.upload?.expires_at ?? body?.expires_at;
  if (typeof raw !== 'string') return {};
  const at = Date.parse(raw);
  if (!Number.isFinite(at)) return { expiresAt: raw };
  return { expiresAt: raw, expiresInSec: Math.max(0, Math.round((at - Date.now()) / 1000)) };
}

async function uploadOnce(file, bytes, timeoutMs) {
  const name = basename(file);
  const url = `${ENDPOINT}?filename=${encodeURIComponent(name)}`;
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        accept: '*/*',
        'accept-language': 'zh-CN,zh;q=0.9',
        'content-type': mimeOf(file),
        origin: 'https://help.github.com',
        referer: 'https://help.github.com/',
      },
      body: bytes,
      credentials: 'omit',
      signal: ac.signal,
    });
    const text = await res.text();
    trackRateLimit(res);
    let body;
    try { body = text ? JSON.parse(text) : {}; } catch { body = { raw: text.slice(0, 500) }; }
    return { res, body };
  } finally {
    clearTimeout(timer);
  }
}

async function uploadFile(file) {
  const abs = resolve(file);
  let info;
  try { info = await stat(abs); } catch (e) {
    return { ok: false, file: abs, error: `stat failed: ${e.message}` };
  }
  if (!info.isFile()) return { ok: false, file: abs, error: 'not a regular file' };
  if (info.size === 0) return { ok: false, file: abs, error: 'empty file' };
  if (info.size > MAX_BYTES) {
    return { ok: false, file: abs, error: `file too large: ${(info.size / 1048576).toFixed(1)}MB > 50MB` };
  }

  const bytes = await readFile(abs);
  const timeoutMs = timeoutFor(info.size);
  let lastError = 'unknown error';
  let lastStatus;
  let pendingWait = 0;

  for (let attempt = 0; attempt <= RETRIES; attempt++) {
    if (attempt > 0) {
      const backoff = Math.min(60000, 1000 * 2 ** (attempt - 1));
      await sleep(jitter(Math.max(backoff, pendingWait)));
      pendingWait = 0;
    }
    try {
      const { res, body } = await uploadOnce(abs, bytes, timeoutMs);
      lastStatus = res.status;
      if (res.ok) {
        const url = extractUrl(body);
        if (!url) return { ok: false, file: abs, status: res.status, error: 'no url in response', body };
        return {
          ok: true,
          file: abs,
          url,
          bytes: info.size,
          token: extractToken(body),
          ...extractExpiry(body),
        };
      }
      lastError = `HTTP ${res.status}: ${typeof body?.error === 'string' ? body.error : JSON.stringify(body).slice(0, 300)}`;
      // 413 / 415 / 401 等重试无意义，直接失败
      if (res.status === 413 || res.status === 415 || res.status === 401 || res.status === 404) break;
      const retryAfter = Number(res.headers.get('retry-after'));
      if (Number.isFinite(retryAfter) && retryAfter > 0) {
        pendingWait = Math.min(retryAfter * 1000, 60000);
      } else if (res.status === 429) {
        // 撞到限流：等配额窗口重置，而不是盲目指数退避
        const wait = rate.resetAt - Date.now();
        pendingWait = Math.min(Math.max(wait, 1000), 120000);
      }
    } catch (e) {
      lastError = e.name === 'AbortError'
        ? `timeout after ${timeoutMs}ms (${(info.size / 1048576).toFixed(1)}MB)`
        : `${e.name}: ${e.message}`;
    }
  }
  return { ok: false, file: abs, status: lastStatus, error: lastError };
}

const args = process.argv.slice(2);
if (!args.length || args.includes('-h') || args.includes('--help')) {
  console.log('usage: node upload.mjs <file> [file...]\n'
    + 'env: UPLOAD_RETRIES(4) UPLOAD_TIMEOUT_MS(0=按体积自适应) UPLOAD_ASSUMED_BPS(40000)\n'
    + '     UPLOAD_MIN_INTERVAL_MS(0=自适应) UPLOAD_RESERVE(200) UPLOAD_ENDPOINT\n'
    + 'limit: 单文件 <= 50MB；URL 仅 60 分钟有效（输出带 expiresAt/expiresInSec）\n'
    + '       串行上传，按 ratelimit-remaining 响应头自适应等待（配额约 250 次/分钟）\n'
    + 'note: 该端点实测上传带宽约 80KB/s，50MB 需 10 分钟以上，属正常');
  process.exit(args.length ? 0 : 2);
}

let failed = 0;
for (const file of args) {
  await rateGate();
  const out = await uploadFile(file);
  if (!out.ok) failed++;
  console.log(JSON.stringify(out));
}
process.exit(failed ? 1 : 0);
