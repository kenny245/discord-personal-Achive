"""Double-click-friendly launcher for the localhost GUI."""

from __future__ import annotations

import argparse
import threading
import webbrowser

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Discord Personal Archive local service")
    parser.add_argument("--no-browser", action="store_true", help="Do not open browser automatically")
    args = parser.parse_args()
    url = "http://127.0.0.1:8765"
    print(f"Discord Personal Archive: {url}")
    print("安全提示：仅监听本机地址。关闭此窗口即停止服务。")
    if not args.no_browser:
        threading.Timer(1.3, lambda: webbrowser.open(url)).start()
    uvicorn.run("backend.app:app", host="127.0.0.1", port=8765,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
