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
mkdir -p cmake_out/velavision_wifi_ip_20260909
# This directory belongs exclusively to this experimental build; refresh its
# generated config from the audited project profile on every invocation.
rm -f cmake_out/velavision_wifi_ip_20260909/.config
cmake -S nuttx -B cmake_out/velavision_wifi_ip_20260909 -G Ninja \
  -DBOARD_CONFIG=kickpi_k7:velavision_wifi_ip_local
cmake --build cmake_out/velavision_wifi_ip_20260909 -j6
