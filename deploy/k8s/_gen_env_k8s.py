"""从仓库根 .env 抽出 K8s Secret 所需键，写入 deploy/k8s/env.k8s（gitignored）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / ".env"
DST = Path(__file__).resolve().parent / "env.k8s"

KEYS = [
    "MYSQL_ROOT_PASSWORD",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_API_BASE",
    "JWT_SECRET",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD",
    "EMBEDDING_API_KEY",
    "EMBEDDING_API_BASE",
    "EMBEDDING_MODEL",
]


def main() -> None:
    if not SRC.is_file():
        raise SystemExit(f"missing {SRC}")
    found: dict[str, str] = {}
    for line in SRC.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        if k in KEYS and k not in found:
            found[k] = v.strip()
    missing = [k for k in KEYS if k not in found or not found[k]]
    lines = [f"{k}={found.get(k, '')}" for k in KEYS]
    DST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {DST} ({len(KEYS)} keys)")
    if missing:
        print("WARNING empty/missing:", ", ".join(missing))


if __name__ == "__main__":
    main()
