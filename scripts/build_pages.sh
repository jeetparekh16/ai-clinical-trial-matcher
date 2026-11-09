#!/usr/bin/env bash
# Builds the static GitHub Pages demo into frontend/out.
# Usage: scripts/build_pages.sh [base path, default /ai-clinical-trial-matcher]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_PATH="${1-/ai-clinical-trial-matcher}"

# Package the Python matcher for Pyodide (pure Python, no server dependencies).
mkdir -p "$ROOT/frontend/public/py"
rm -f "$ROOT/frontend/public/py/trialmatch.zip"
(cd "$ROOT/backend" && python3 -c "
import pathlib, zipfile
with zipfile.ZipFile('$ROOT/frontend/public/py/trialmatch.zip', 'w', zipfile.ZIP_DEFLATED) as z:
    for f in sorted(pathlib.Path('trialmatch').rglob('*')):
        if f.is_file() and '__pycache__' not in f.parts and f.suffix in ('.py', '.json'):
            z.write(f)
")

cd "$ROOT/frontend"
NEXT_PUBLIC_ENGINE=browser NEXT_PUBLIC_BASE_PATH="$BASE_PATH" NEXT_TELEMETRY_DISABLED=1 npx next build
touch out/.nojekyll
echo "Built frontend/out for base path '$BASE_PATH'"
