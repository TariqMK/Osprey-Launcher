#!/usr/bin/env bash
# Works out release versions. Existing tags are read from stdin, one per line.
#
# Usage:
#   next_version.sh <major|minor|patch>          Next vX.Y.Z from the plain vX.Y.Z tags only.
#   next_version.sh branch <vX.Y.Z> <label>       Next vX.Y.Z-label.N branch build tag.
#   next_version.sh label <branch name>           Branch name made safe for a tag (no stdin).
set -euo pipefail

make_label() {
  local label
  label=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//')
  label=${label:0:30}
  label=$(printf '%s' "$label" | sed -E 's/-+$//')
  printf '%s\n' "${label:-branch}"
}

case "${1:-}" in
  major | minor | patch)
    # Pre-release tags (vX.Y.Z-label.N) never count towards the next version.
    latest=$(grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' | sort -V | tail -n 1 || true)
    IFS=. read -r major minor patch <<< "${latest#v}"
    major=${major:-0} minor=${minor:-0} patch=${patch:-0}
    case "$1" in
      major) echo "v$((major + 1)).0.0" ;;
      minor) echo "v$major.$((minor + 1)).0" ;;
      patch) echo "v$major.$minor.$((patch + 1))" ;;
    esac
    ;;
  branch)
    base=${2:?base version needed, for example v1.5.0}
    label=${3:?label needed}
    # Highest N already used for this base and label, from tags and releases (drafts included).
    last=$(grep -E "^${base//./\\.}-${label}\.[0-9]+$" | sed -E 's/.*\.([0-9]+)$/\1/' | sort -n | tail -n 1 || true)
    echo "$base-$label.$(( ${last:-0} + 1 ))"
    ;;
  label)
    make_label "${2:?branch name needed}"
    ;;
  *)
    echo "Usage: next_version.sh <major|minor|patch> | branch <vX.Y.Z> <label> | label <branch>" >&2
    exit 1
    ;;
esac
