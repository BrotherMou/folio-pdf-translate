#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
swift build --package-path "$ROOT/engine" -c release
BUILT=$(swift build --package-path "$ROOT/engine" -c release --show-bin-path)
mkdir -p "$ROOT/bin"
cp "$BUILT/pdf-translate-engine" "$ROOT/bin/"
for resource in "$BUILT/"*.bundle; do
    [ ! -d "$resource" ] || cp -R "$resource" "$ROOT/bin/"
done
