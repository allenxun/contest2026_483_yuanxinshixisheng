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
cmake -S nuttx -B cmake_out/velavision_smp_service_20260910 -G Ninja \
  -DBOARD_CONFIG=kickpi_k7:velavision_smp_service_local
cmake --build cmake_out/velavision_smp_service_20260910 --target resetconfig
cmake --build cmake_out/velavision_smp_service_20260910 -j6
