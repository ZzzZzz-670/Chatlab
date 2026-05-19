import json
import argparse
import requests

# ── 配置 ──────────────────────────────────────────────
TOKEN = "pat_Id8whVrK8pZEUnj6jdHItdGHzJZZXcwbmpucloZhjclvmAyoF3dlkvsJBPqc3rYc"
QUERY = "孩子不想写作业怎么办？"  # 在此填入查询内容
OUTPUT_FILE = "response.txt"
SAVE_AS_TEXT = True    # True: 写入拼接后的纯文本；False: 写入原始 JSON 分片
# ──────────────────────────────────────────────────────

parser = argparse.ArgumentParser()
parser.add_argument("--terminal", action="store_true", help="流式输出到终端，不写入文件")
args = parser.parse_args()

url = "https://4vd6j8c98y.coze.site/stream_run"
headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "text/event-stream",
}
payload = {
    "content": {
        "query": {
            "prompt": [
                {
                    "type": "text",
                    "content": {"text": QUERY}
                }
            ]
        }
    },
    "type": "query",
    "session_id": "voUcOYEiyB6rO8bhDSUHU",
    "project_id": "7641269679604039732"
}

response = requests.post(url, headers=headers, json=payload, stream=True)
response.raise_for_status()

def handle_line(parsed, f=None):
    if args.terminal:
        if parsed.get("type") == "answer":
            answer = parsed.get("content", {}).get("answer") or ""
            print(answer, end="", flush=True)
    else:
        if SAVE_AS_TEXT:
            if parsed.get("type") == "answer":
                answer = parsed.get("content", {}).get("answer") or ""
                f.write(answer)
                f.flush()
        else:
            f.write(json.dumps(parsed, ensure_ascii=False, indent=2) + "\n")
            f.flush()

if args.terminal:
    for line in response.iter_lines(decode_unicode=True):
        if line and line.startswith("data:"):
            try:
                parsed = json.loads(line[5:].strip())
            except Exception:
                continue
            handle_line(parsed)
    print()  # 输出结束后换行
else:
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for line in response.iter_lines(decode_unicode=True):
            if line and line.startswith("data:"):
                try:
                    parsed = json.loads(line[5:].strip())
                except Exception:
                    continue
                handle_line(parsed, f)