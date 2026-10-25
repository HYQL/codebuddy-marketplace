#!/usr/bin/env python3
"""Agnes Image 2.5 Flash 图像生成/图生图/多图合成（同步 API）。

仅依赖 Python 标准库。用法示例：
  python agnes_image.py "提示词" --size 2K --ratio 16:9 --out city.png
  python agnes_image.py "把主体换成橙色" --image ./in.png --b64

API Key 读取顺序：--api-key 参数 > 环境变量 AGNES_API_KEY。
"""
import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = "https://api.agnes-ai.cn/v1"
MODEL = "agnes-image-2.5-flash"
MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}


def http_json(url: str, api_key: str, payload: dict | None, timeout: int,
               method: str = "POST") -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"[API {e.code}] {url}\n{body}")
    except urllib.error.URLError as e:
        sys.exit(f"[网络错误] 无法连接 Agnes API（{url}）: {e.reason}")
    except json.JSONDecodeError as e:
        sys.exit(f"[响应解析失败] 服务未返回合法 JSON: {e}")


def to_image_ref(ref: str) -> str:
    """支持本地文件路径（自动转 Data URI）或 URL / 已有 Data URI。"""
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    p = Path(ref)
    if not p.is_file():
        sys.exit(f"输入图既不是 URL 也不是存在的本地文件: {ref}")
    mime = MIME_BY_EXT.get(p.suffix.lower(), mimetypes.guess_type(p.name)[0] or "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def download(url: str, out: Path, api_key: str, timeout: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, out.open("wb") as f:
            f.write(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        sys.exit(f"[下载失败 {e.code}] {url}\n{body}")
    except urllib.error.URLError as e:
        sys.exit(f"[网络错误] 无法下载结果（{url}）: {e.reason}")


def key_from_models_json() -> str | None:
    """回退：从 CodeBuddy 自定义模型配置中查找 Agnes 模型的 apiKey。"""
    candidate = Path.home() / ".codebuddy" / "models.json"
    if not candidate.is_file():
        return None
    try:
        models = json.loads(candidate.read_text(encoding="utf-8")).get("models", [])
        for m in models:
            if m.get("url", "").startswith("https://api.agnes-ai.cn") and m.get("apiKey"):
                return m["apiKey"]
    except Exception:
        return None
    return None


def resolve_api_key(cli_key: str | None) -> str:
    """优先级：--api-key > 环境变量 AGNES_API_KEY > ~/.codebuddy/models.json 中的 Agnes 模型。"""
    if cli_key:
        return cli_key
    env_key = os.environ.get("AGNES_API_KEY")
    if env_key:
        return env_key
    from_file = key_from_models_json()
    if from_file:
        print("[agnes] 未设置 AGNES_API_KEY，已自动使用 ~/.codebuddy/models.json 中 Agnes 模型的 API Key")
        return from_file
    sys.exit("缺少 API Key：请设置环境变量 AGNES_API_KEY、使用 --api-key，"
             "或在 ~/.codebuddy/models.json 配置 url 为 https://api.agnes-ai.cn/v1 的模型")


def main() -> None:
    ap = argparse.ArgumentParser(description="Agnes Image 2.5 Flash 图像生成")
    ap.add_argument("prompt", help="文生图/图生图提示词")
    ap.add_argument("--size", default="1K", help="1K/2K/3K/4K 或精确写法如 1024x768（默认 1K）")
    ap.add_argument("--ratio", default=None,
                    help="宽高比 1:1|3:4|4:3|16:9|9:16|2:3|3:2|21:9（默认 1:1）")
    ap.add_argument("--image", action="append", default=[],
                    help="输入图：公共 HTTPS URL 或本地文件路径（自动转 Data URI），可重复（图生图/多图合成）")
    ap.add_argument("--b64", action="store_true", help="以 b64_json 取图并直接落盘")
    ap.add_argument("--out", default=None, help="输出文件路径（默认 agnes_out/image_<ts>.png）")
    ap.add_argument("--api-key", default=None, help="Agnes API Key（默认取环境变量 AGNES_API_KEY）")
    ap.add_argument("--timeout", type=int, default=300, help="HTTP 超时秒数（默认 300）")
    args = ap.parse_args()

    api_key = resolve_api_key(args.api_key)

    extra_body: dict = {"response_format": "b64_json" if args.b64 else "url"}
    if args.image:
        extra_body["image"] = [to_image_ref(r) for r in args.image]

    payload = {
        "model": MODEL,
        "prompt": args.prompt,
        "size": args.size,
        "extra_body": extra_body,
    }
    if args.ratio:
        payload["ratio"] = args.ratio

    print(f"[agnes-image] model={MODEL} size={args.size} ratio={args.ratio or '1:1'} "
          f"输入图 {len(args.image)} 张 …")
    t0 = time.time()
    resp = http_json(f"{BASE_URL}/images/generations", api_key, payload, args.timeout)
    item = (resp.get("data") or [{}])[0]
    out = Path(args.out) if args.out else Path("agnes_out") / f"image_{int(time.time())}.png"

    if item.get("b64_json"):
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        download(item["url"], out, api_key, args.timeout)
    else:
        sys.exit(f"响应缺少 url/b64_json: {json.dumps(resp, ensure_ascii=False)[:500]}")

    print(f"[agnes-image] 完成（{time.time() - t0:.1f}s），已保存: {out.resolve()}")
    print(f"[agnes-image] 提示词修正: {item.get('revised_prompt') or '（无）'}")


if __name__ == "__main__":
    main()
