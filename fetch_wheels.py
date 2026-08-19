#!/usr/bin/env python3
"""从 PyPI 抓取 wheel 到本地目录，供 pip --no-index 离线安装。

⚠️ 警告：本脚本于 2026-08-16 在 DeepSeek Harness 沙箱内验证发现——
该沙箱的出网流量被整体仿真拦截，无论 http/https 镜像都会返回"合成包"
（实测官方 PyPI 被投喂 pydantic-1.10.26-cp314、带 httpx2 依赖的 openai-3.1.0
等真实世界不存在的包）。**请勿在沙箱环境内运行本脚本并安装其结果。**
本脚本仅适用于有真实互联网的机器（如 WSL / 用户本机 Windows 终端）。
"""
import importlib.util
import os
import re
import sys
import urllib.parse
import urllib.request
import zipfile

INDEX = "https://pypi.org/simple/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".wheels")

TOP_LEVEL = [
    "httpx", "pyyaml", "openai", "pydantic", "scipy",
    "structlog", "aiosqlite", "PyPDF2", "pymupdf", "pytest",
]

_TAG_ORDER = ["cp314", "py3"]
_PLAT_PREF = ["win_amd64", "py3-none-any", "none-any"]


def _importable(name: str) -> bool:
    if name.lower() in {"typing_extensions"}:
        return False  # typing_extensions 仍需要新版本
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _version_key(fname: str):
    m = re.search(r"-(\d+(?:\.\d+)*[a-z0-9.]*?)-", fname)
    if not m:
        return (0,)
    ver = m.group(1)
    # 排除预发布版 (a/b/rc/dev)
    if re.search(r"[a-zA-Z]", ver):
        return (0,)
    parts = re.split(r"[.\-]", ver)
    key = []
    for p in parts:
        try:
            key.append(int(p))
        except ValueError:
            key.append(0)
    return tuple(key)


def _pick_wheel(links):
    """选一个兼容普通 cp314/win_amd64 的最新稳定 wheel。"""
    candidates = []
    for href in links:
        fname = href.rsplit("/", 1)[-1].split("#")[0]
        if not fname.endswith(".whl"):
            continue
        body = fname[:-4]
        tags = body.split("-")[-3:]  # e.g. cp314-cp314-win_amd64 / cp314t-cp314t-win_amd64 / cp39-abi3-win_amd64
        py, abi, plat = tags
        if py.startswith("cp314t"):  # free-threaded 专用，普通 3.14 不兼容
            continue
        if abi == "abi3":
            if not py.startswith("cp"):
                continue
            tag_rank = 2
        elif py == "cp314" and abi == "cp314":
            tag_rank = 1
        elif py.startswith("py3"):
            tag_rank = 3
        else:
            continue
        if plat not in ("win_amd64", "any", "py3-none-any", "none-any"):
            continue
        stable = 0 if re.search(r"[a-zA-Z]", fname.split("-")[1]) else 1  # 排除预发布
        candidates.append((stable, -tag_rank, _version_key(fname), fname, href))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    return candidates[-1][4]


def _resolve(href, base):
    href = href.split("#")[0]
    return urllib.parse.urljoin(base, href)


def _requires(wheel_path):
    with zipfile.ZipFile(wheel_path) as z:
        meta = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")]
        if not meta:
            return []
        text = z.read(meta[0]).decode("utf-8", "replace")
    reqs = []
    for line in text.splitlines():
        if line.startswith("Requires-Dist:"):
            spec = line[len("Requires-Dist:"):].strip()
            # 跳过 extra 依赖 (test/doc/dev/...)，只装 base 依赖
            marker = spec.split(";", 1)
            if len(marker) > 1 and "extra" in marker[1]:
                continue
            req_part = marker[0].strip()
            # 去掉版本约束与 [extra] 下标，取包名
            name = re.split(r"[<>=!~\[( ]+", req_part, maxsplit=1)[0].strip()
            name = name.split("[")[0]
            if name:
                reqs.append(name)
    return reqs


def main():
    os.makedirs(OUT, exist_ok=True)
    seen = set()
    queue = list(TOP_LEVEL)
    fetched = []
    while queue:
        pkg = queue.pop(0)
        key = pkg.lower().replace("_", "-")
        if key in seen:
            continue
        seen.add(key)
        url = INDEX + key + "/"
        try:
            html = urllib.request.urlopen(url, timeout=30).read().decode("utf-8", "replace")
        except Exception as e:
            print(f"[skip] {key}: 索引不可用 {e}")
            continue
        links = re.findall(r'href="([^"]+)"', html)
        chosen = _pick_wheel(links)
        if not chosen:
            print(f"[skip] {key}: 无兼容 wheel")
            continue
        fname = chosen.rsplit("/", 1)[-1].split("#")[0]
        dest = os.path.join(OUT, fname)
        if not os.path.exists(dest) or os.path.getsize(dest) == 0:
            full = _resolve(chosen, url)
            print(f"[get ] {key}: {fname}")
            try:
                urllib.request.urlretrieve(full, dest)
            except Exception as e:
                print(f"[fail] {key}: {e}")
                continue
        else:
            print(f"[have] {key}: {fname}")
        fetched.append(dest)
        for dep in _requires(dest):
            d = dep.lower().replace("_", "-")
            if d not in seen and not _importable(dep):
                if len(seen) < 80:  # 安全上限，防依赖树失控
                    queue.append(dep)
                else:
                    print(f"[cap ] 依赖数量达上限，忽略 {dep}")
    print(f"\n=== 共下载 {len(fetched)} 个 wheel 到 {OUT} ===")
    for f in sorted(fetched):
        print(" ", os.path.basename(f))


if __name__ == "__main__":
    main()
