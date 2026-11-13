#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "${REPO_ROOT}"

cargo build --release --target x86_64-unknown-linux-gnu \
    -p eira-core -p eira-ipc -p eira-stated
cargo build --release --target wasm32-unknown-unknown -p eira-core

# The Android client is not part of EiraOS 1.0 and is archived in
# docs/archive/android (UDVIKLINGSPLAN F1.8); no aarch64-linux-android build.
