"""Decide expensive gates from the verified event base; unknown changes run both."""
import json
import os
from pathlib import Path
import subprocess


def classify(paths):
    benchmark = browser = False
    for path in paths:
        if path.endswith(".md") or path == "LICENSE":
            continue
        browser = True
        if not path.startswith("frontend/") or path == "frontend/package-lock.json":
            benchmark = True
    return benchmark, browser


def main():
    benchmark = browser = True
    event = os.environ["GITHUB_EVENT_NAME"]
    payload = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    if event in {"push", "pull_request"}:
        base = payload.get("before") if event == "push" else payload["pull_request"]["base"]["sha"]
        if base and base.strip("0"):
            diff = subprocess.run(["git", "diff", "--name-only", "--no-renames", "-z", base, "HEAD"], capture_output=True)
            if diff.returncode == 0:
                benchmark, browser = classify(os.fsdecode(path) for path in diff.stdout.split(b"\0") if path)
    with open(os.environ["GITHUB_OUTPUT"], "a") as handle:
        for name, enabled in (("performance", benchmark), ("browser", browser)):
            print(f"{name}={str(enabled).lower()}", file=handle)


if __name__ == "__main__":
    main()
