#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
sdk_dir="${1:?SDK directory required}"
python3 "$project_dir/tools/sync_sdk.py" --sdk "$sdk_dir" --apply
cd "$sdk_dir"
mkdir -p /dev/shm/velavision_audio_io_tmp
export TMPDIR=/dev/shm/velavision_audio_io_tmp
set +eu
source build/envsetup.sh >/dev/null
setup_status=$?
set -eu
test "$setup_status" -eq 0
cmake -S nuttx -B /dev/shm/velavision_audio_io_20260910 -G Ninja \
  -DBOARD_CONFIG=kickpi_k7:velavision_audio_io_local
cmake --build /dev/shm/velavision_audio_io_20260910 --target resetconfig
cmake --build /dev/shm/velavision_audio_io_20260910 -j4
