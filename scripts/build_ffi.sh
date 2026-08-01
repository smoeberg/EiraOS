#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "${REPO_ROOT}"

cargo build --release --target x86_64-unknown-linux-gnu \
    -p eira-core -p eira-ipc -p eira-stated
cargo build --release --target wasm32-unknown-unknown -p eira-core

if [[ -z ${ANDROID_NDK_HOME:-} ]]; then
    echo "ANDROID_NDK_HOME is required for aarch64 Android builds" >&2
    exit 1
fi

ANDROID_API=${ANDROID_API:-28}
TOOLCHAIN="${ANDROID_NDK_HOME}/toolchains/llvm/prebuilt/linux-x86_64/bin"
LINKER="${TOOLCHAIN}/aarch64-linux-android${ANDROID_API}-clang"
if [[ ! -x ${LINKER} ]]; then
    echo "Android NDK linker not found: ${LINKER}" >&2
    exit 1
fi

export CARGO_TARGET_AARCH64_LINUX_ANDROID_LINKER="${LINKER}"
cargo build --release --target aarch64-linux-android -p eira-core

install -D -m 0644 \
    target/aarch64-linux-android/release/libeira_core.so \
    android/eira-core-binding/src/main/jniLibs/arm64-v8a/libeira_core.so
