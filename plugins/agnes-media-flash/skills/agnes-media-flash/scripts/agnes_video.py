#!/usr/bin/env python3
"""Agnes Video 2.5 Flash 视频生成（异步任务：建任务 → 轮询 → 下载）。

仅依赖 Python 标准库。用法示例：
  python agnes_video.py "雨后未来城市街道" --seconds 5 --aspect-ratio 16:9
  python agnes_video.py "角色转身走向窗边" --mode keyframe \
      --first-frame https://example.com/f.png --last-frame https://example.com/l.png
  python agnes_video.py "以 <Picture 1> 的角色在花田奔跑" --mode reference \
      --images https://example.com/char.png

API Key 读取顺序：--api-key 参数 > 环境变量 AGNES_API_KEY。
媒体 URL（首尾帧/参考图/参考音频）必须可被 Agnes 服务公开访问，且任务完成前保持有效。
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CREATE_URL = "https://api.agnes-ai.cn/v1/videos"
QUERY_URL = "https://api.agnes-ai.cn/agnesapi"
MODEL = "agnes-video-2.5-flash"
POLL_STATUSES_DONE = {"completed", "failed"}


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


def build_payload(args) -> dict:
    payload: dict = {
        "model": MODEL,
        "prompt": args.prompt,
        "mode": args.mode,
        "seconds": str(args.seconds),
        "size": "720P",
    }
    if args.aspect_ratio:
        payload["aspect_ratio"] = args.aspect_ratio
    if args.seed is not None:
        payload["seed"] = args.seed

    if args.mode == "keyframe":
        frames = [u for u in (args.first_frame, args.last_frame) if u]
        if not frames:
            sys.exit("keyframe 模式至少需要 --first-frame 或 --last-frame 之一")
        if args.first_frame:
            payload["first_frame"] = args.first_frame
        if args.last_frame:
            payload["last_frame"] = args.last_frame
    elif args.mode == "reference":
        if not (args.images or args.audios):
            sys.exit("reference 模式至少需要 --images 或 --audios 之一")
        if args.images:
            if len(args.images) > 5:
                sys.exit("Flash 模型参考图最多 5 张")
            payload["images"] = args.images
        if args.audios:
            if len(args.audios) > 3:
                sys.exit("Flash 模型参考音频最多 3 段")
            payload["audios"] = args.audios
    elif args.images or args.audios or args.first_frame or args.last_frame:
        sys.exit("text 模式不能传媒体字段（--first-frame/--last-frame/--images/--audios）")
    return payload


def poll(video_id: str, mode: str, api_key: str, interval: float, timeout: int) -> dict:
    # keyframe/reference 模式查询必须带 model_name；text 模式裸 video_id 也可
    params = {"video_id": video_id, "model_name": MODEL} if mode != "text" else {"video_id": video_id}
    url = f"{QUERY_URL}?{urllib.parse.urlencode(params)}"
    deadline = time.time() + timeout
    last_status = ""
    while time.time() < deadline:
        resp = http_json(url, api_key, None, timeout=30, method="GET")
        status = str(resp.get("status", ""))
        if status != last_status:
            progress = resp.get("progress")
            print(f"[agnes-video] status={status} progress={progress}")
            last_status = status
        if status == "completed":
            return resp
        if status == "failed":
            sys.exit(f"视频任务失败: {json.dumps(resp, ensure_ascii=False)[:800]}")
        time.sleep(interval)
    sys.exit(f"轮询超时（{timeout}s），video_id={video_id}，可稍后手动查询: {url}")


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
    ap = argparse.ArgumentParser(description="Agnes Video 2.5 Flash 视频生成")
    ap.add_argument("prompt", help="视频描述；reference 模式可用 <Picture N>/<Audio N> 指代素材")
    ap.add_argument("--mode", choices=["text", "keyframe", "reference"], default="text")
    ap.add_argument("--seconds", type=int, default=5, help="时长 4~12（默认 5）")
    ap.add_argument("--aspect-ratio", default="16:9",
                    help="21:9|16:9|4:3|1:1|3:4|9:16（默认 16:9）；Flash 仅 720P")
    ap.add_argument("--first-frame", default=None, help="keyframe 模式首帧公共 URL")
    ap.add_argument("--last-frame", default=None, help="keyframe 模式尾帧公共 URL")
    ap.add_argument("--images", action="append", default=[], help="reference 参考图 URL，可重复，最多 5 张")
    ap.add_argument("--audios", action="append", default=[], help="reference 参考音频 URL，可重复，最多 3 段")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--out", default=None, help="输出文件路径（默认 agnes_out/video_<ts>.mp4）")
    ap.add_argument("--poll-interval", type=float, default=10.0, help="轮询间隔秒（默认 10，免费额度查询频繁会 429）")
    ap.add_argument("--timeout", type=int, default=600, help="总轮询超时秒（默认 600）")
    ap.add_argument("--api-key", default=None, help="Agnes API Key（默认取环境变量 AGNES_API_KEY）")
    args = ap.parse_args()

    if not 4 <= args.seconds <= 12:
        sys.exit("seconds 必须为 4~12")
    api_key = resolve_api_key(args.api_key)

    payload = build_payload(args)
    print(f"[agnes-video] 创建任务 mode={args.mode} seconds={args.seconds} "
          f"aspect_ratio={args.aspect_ratio} …")
    resp = http_json(CREATE_URL, api_key, payload, timeout=60)

    video_id = resp.get("video_id") or resp.get("task_id") or resp.get("id")
    if not video_id:
        sys.exit(f"创建任务响应缺少 video_id: {json.dumps(resp, ensure_ascii=False)[:500]}")
    print(f"[agnes-video] 任务已创建 video_id={video_id}")

    done = poll(video_id, args.mode, api_key, args.poll_interval, args.timeout)
    url = done.get("url")
    if not url:
        sys.exit(f"completed 状态但缺少 url: {json.dumps(done, ensure_ascii=False)[:500]}")

    out = Path(args.out) if args.out else Path("agnes_out") / f"video_{int(time.time())}.mp4"
    download(url, out, api_key, timeout=300)
    print(f"[agnes-video] 完成，已保存: {out.resolve()}")


if __name__ == "__main__":
    main()
