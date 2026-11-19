"""Validate relative links in the current operator documentation."""
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
GUIDES = ("README.md", "docs/data-source-capabilities.md", "docs/mentor-demo-guide.md",
          "docs/development/reliability-and-release.md", ".github/branch-protection.md")


def main():
    missing = []
    for guide in GUIDES:
        document = ROOT / guide
        for target in re.findall(r"\]\(([^)\s]+)\)", document.read_text()):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            path = (document.parent / unquote(url.path)).resolve()
            if not path.is_relative_to(ROOT) or not path.exists():
                missing.append(f"{guide} -> {target}")
    if missing:
        raise SystemExit("\n".join(missing))
    print(f"Checked relative file links in {len(GUIDES)} guides")


if __name__ == "__main__":
    main()
