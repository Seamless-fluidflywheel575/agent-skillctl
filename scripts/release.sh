#!/usr/bin/env bash

set -euo pipefail

bump="${1:-patch}"
release_branch="${RELEASE_BRANCH:-main}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd -- "$script_dir/.." && pwd)"

cd "$repo_root"

case "$bump" in
  patch | minor | major) ;;
  *)
    echo "Bump must be patch, minor, or major (got: $bump)" >&2
    exit 2
    ;;
esac

for tool in git uv gh python3; do
  command -v "$tool" >/dev/null || {
    echo "Missing required command: $tool" >&2
    exit 2
  }
done

branch="$(git branch --show-current)"
if [[ "$branch" != "$release_branch" ]]; then
  echo "Release must run from $release_branch (current: $branch)" >&2
  exit 2
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "Working tree must be clean before releasing" >&2
  git status --short
  exit 2
fi

echo "==> Checking origin/$release_branch"
git fetch --quiet origin "$release_branch"
if [[ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$release_branch")" ]]; then
  echo "Local $release_branch must exactly match origin/$release_branch" >&2
  exit 2
fi

echo "==> Running release checks"
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen mypy

echo "==> Bumping $bump version"
old_version="$(uv version --short)"
uv version --bump "$bump" --frozen
version="$(uv version --short)"

python3 - "$old_version" "$version" <<'PY'
import sys
from pathlib import Path

path = Path("uv.lock")
content = path.read_text()
old = (
    'name = "agent-skillctl"\n'
    f'version = "{sys.argv[1]}"\n'
    'source = { editable = "." }'
)
new = (
    'name = "agent-skillctl"\n'
    f'version = "{sys.argv[2]}"\n'
    'source = { editable = "." }'
)
if content.count(old) != 1:
    raise SystemExit("Could not locate the project version in uv.lock")
path.write_text(content.replace(old, new, 1))
PY

tag="v$version"
if git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
  echo "Tag already exists: $tag" >&2
  exit 2
fi

echo "==> Building $tag"
uv build

echo "==> Committing and tagging $tag"
git add pyproject.toml uv.lock
git commit -m "release: $tag"
git tag -a "$tag" -m "$tag"

echo "==> Pushing $tag"
git push --atomic origin "$release_branch" "$tag"

echo "==> Creating GitHub Release"
gh release create "$tag" --verify-tag --generate-notes --title "$tag"

echo "==> Released $tag; GitHub Actions will publish it to PyPI"
