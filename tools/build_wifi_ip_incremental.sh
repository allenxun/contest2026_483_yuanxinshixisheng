#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sdk_dir="${1:?SDK directory required}"
python3 "$project_dir/tools/sync_sdk.py" --sdk "$sdk_dir" --apply
cd "$sdk_dir"
set +eu
source build/envsetup.sh >/dev/null
setup_status=$?
set -eu
test "$setup_status" -eq 0
python3 -c 'import hashlib,json;from pathlib import Path;b=Path("cmake_out/velavision_wifi_ip_20260909/.config");r=json.loads(Path("work/velavision-wifi-amsdu-20260909/verification.json").read_text());assert hashlib.sha256(b.read_bytes()).hexdigest()==r["artifacts"][".config"]["sha256"]'
cmake --build cmake_out/velavision_wifi_ip_20260909 -j6
