"""Bundle web/data/*.json and web/mock/*.json into .js files so pages work from file://.

Browsers block fetch() on local files, so each page also loads data.js / mock.js,
which set window.__DATA / window.__MOCK. Run after copying new files into web/data/.

Usage: python tools/sync_web_data.py
"""
import json
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def bundle(folder: str, var: str, out: str) -> int:
    folder_path = WEB / folder
    folder_path.mkdir(exist_ok=True)
    items = {}
    for p in sorted(folder_path.glob("*.json")):
        items[p.name] = json.loads(p.read_text(encoding="utf-8"))
    (folder_path / out).write_text(f"window.{var} = {json.dumps(items)};\n", encoding="utf-8")
    return len(items)


if __name__ == "__main__":
    print("mock files:", bundle("mock", "__MOCK", "mock.js"))
    print("data files:", bundle("data", "__DATA", "data.js"))
