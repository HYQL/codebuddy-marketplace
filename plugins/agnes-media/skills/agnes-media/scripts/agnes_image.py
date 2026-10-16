#!/usr/bin/env python3
"""Agnes Image 2.5 Flash 图像生成/图生图/多图合成（同步 API）。

仅依赖 Python 标准库。用法示例：
  python agnes_image.py "提示词" --size 2K --ratio 16:9 --out city.png
  python agnes_image.py "把主体换成橙色" --image ./in.png --b64

API Key 读取顺序：--api-key 参数 > 环境变量 AGNES_API_KEY > ~/.codebuddy/models.json 中 Agnes 模型。
节点：国内 https://api.agnes-ai.cn（默认）与国外 https://api.agnes-ai.com，用 --node com 或环境变量 AGNES_BASE_URL 切换。
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

BASE_URLS = {
    "cn": "https://api.agnes-ai.cn/v1",
    "com": "https://api.agnes-ai.com/v1",
}
AGNES_URL_PREFIXES = ("https://api.agnes-ai.cn", "https://api.agnes-ai.com")
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
    with urllib.request.urlopen(req, timeout=timeout) as resp, out.open("wb") as f:
        f.write(resp.read())


def key_from_models_json() -> tuple[str, str] | None:
    """回退：从 CodeBuddy 自定义模型配置中查找 Agnes 模型（cn/com 节点）的 apiKey 与 Base URL。"""
    candidate = Path.home() / ".codebuddy" / "models.json"
    if not candidate.is_file():
        return None
    try:
        models = json.loads(candidate.read_text(encoding="utf-8")).get("models", [])
        for m in models:
            url = m.get("url", "")
            if url.startswith(AGNES_URL_PREFIXES) and m.get("apiKey"):
                base = url if url.endswith("/v1") else url + "/v1"
                return m["apiKey"], base
    except Exception:
        return None
    return None


def resolve_credentials(cli_key: str | None, node: str) -> tuple[str, str]:
    """返回 (api_key, base_url)。

    Key 优先级：--api-key > 环境变量 AGNES_API_KEY > ~/.codebuddy/models.json 中 Agnes 模型。
    Base URL 优先级：环境变量 AGNES_BASE_URL > models.json 条目自带 url > 节点默认值。
    """
    base = os.environ.get("AGNES_BASE_URL", "").rstrip("/") or BASE_URLS[node]
    if not base.endswith("/v1"):
        base += "/v1"
    if cli_key:
        return cli_key, base
    env_key = os.environ.get("AGNES_API_KEY")
    if env_key:
        return env_key, base
    found = key_from_models_json()
    if found:
        key, file_base = found
        print("[agnes] 未设置 AGNES_API_KEY，已自动使用 ~/.codebuddy/models.json 中 Agnes 模型的 API Key")
        # 显式设置 AGNES_BASE_URL 时以它为准；否则若条目与所选节点一致则跟随条目 host，
        # 不一致（条目为另一节点）则用所选节点默认 Base，避免 Key 与节点不配对
        if os.environ.get("AGNES_BASE_URL"):
            return key, base
        entry_host = file_base.split("/v1", 1)[0]
        if entry_host != BASE_URLS[node]:
            return key, base
        return key, file_base
    sys.exit("缺少 API Key：请设置环境变量 AGNES_API_KEY、使用 --api-key，"
             "或在 ~/.codebuddy/models.json 配置 url 为 https://api.agnes-ai.cn/v1 "
             "或 https://api.agnes-ai.com/v1 的模型")


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
    ap.add_argument("--node", choices=sorted(BASE_URLS), default="cn",
                    help="API 节点：cn=api.agnes-ai.cn（默认，国内）com=api.agnes-ai.com（国外）；"
                         "亦可用环境变量 AGNES_BASE_URL 直接指定 Base URL")
    ap.add_argument("--timeout", type=int, default=300, help="HTTP 超时秒数（默认 300）")
    args = ap.parse_args()

    api_key, base = resolve_credentials(args.api_key, args.node)

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

    print(f"[agnes-image] model={MODEL} base={base} size={args.size} ratio={args.ratio or '1:1'} "
          f"输入图 {len(args.image)} 张 …")
    t0 = time.time()
    resp = http_json(f"{base}/images/generations", api_key, payload, args.timeout)
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
    if item.get("url"):
        print(f"[agnes-image] 远程地址: {item['url']}")
    else:
        print("[agnes-image] 远程地址: （b64 模式无远程 URL，图片已直接落盘）")
    print(f"[agnes-image] 提示词修正: {item.get('revised_prompt') or '（无）'}")


if __name__ == "__main__":
    main()
