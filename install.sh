#!/usr/bin/env bash
#
# install.sh - copy this delivery into an existing BambooAI_Prod checkout.
#
#   unzip delve_planner.zip && cd delve_planner
#   ./install.sh /home/data/bambooai
#
# Backs up every file it is about to overwrite into a timestamped directory, so
# a bad drop is one `mv` away from undone. Adds new files, never deletes.
#
# It does NOT touch: web_app/LLM_CONFIG.json (your live config - the template is
# copied as LLM_CONFIG_template.json for you to merge), tests/unit/, or anything
# else already in the repo that this delivery does not ship.

set -euo pipefail

DRY_RUN=0
ARGS=()
for a in "$@"; do
    case "$a" in
        --dry-run|-n) DRY_RUN=1 ;;
        *) ARGS+=("$a") ;;
    esac
done
TARGET="${ARGS[0]:-}"
if [[ -z "$TARGET" ]]; then
    echo "usage: ./install.sh [--dry-run] /path/to/BambooAI_Prod" >&2
    exit 1
fi
if [[ ! -d "$TARGET/bambooai" ]]; then
    echo "error: $TARGET does not look like a BambooAI checkout (no bambooai/)" >&2
    exit 1
fi

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── drift check ───────────────────────────────────────────────────────────
# This delivery edits 19 existing files, based on a snapshot of the repo. If one
# of them has changed in YOUR checkout since that snapshot, overwriting it loses
# your change silently. BASELINE.md5 holds the checksums of the versions these
# edits were made against; anything that does not match is reported and you
# decide.
if [[ -f "$SRC/BASELINE.md5" ]]; then
    drifted=()
    while read -r sum path; do
        [[ -f "$TARGET/$path" ]] || continue
        actual="$(md5sum "$TARGET/$path" | awk '{print $1}')"
        [[ "$actual" == "$sum" ]] || drifted+=("$path")
    done < "$SRC/BASELINE.md5"

    if (( ${#drifted[@]} )); then
        echo "WARNING: ${#drifted[@]} file(s) differ from the version these edits were built on:"
        printf '  %s\n' "${drifted[@]}"
        echo
        echo "Installing overwrites them. Your originals go to the backup directory,"
        echo "so nothing is lost - but any change you made since the snapshot will not"
        echo "be in the installed version. Diff the backup afterwards, or abort now and"
        echo "send an up-to-date copy of those files."
        echo
        if (( ! DRY_RUN )); then
            read -r -p "Continue? [y/N] " reply
            [[ "$reply" =~ ^[Yy]$ ]] || { echo "aborted"; exit 1; }
        fi
        echo
    else
        echo "drift check: all 19 target files match the expected baseline"
        echo
    fi
fi
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$TARGET/.delve_backup_$STAMP"

echo "source : $SRC"
echo "target : $TARGET"
if (( DRY_RUN )); then
    echo "mode   : DRY RUN - nothing will be written"
else
    echo "backup : $BACKUP"
fi
echo

modified=0
added=0

while IFS= read -r -d '' file; do
    rel="${file#$SRC/}"
    case "$rel" in
        install.sh|MANIFEST.md|bambooai_changes.patch|BASELINE.md5|README_INSTALL.md) continue ;;
    esac
    dest="$TARGET/$rel"
    if [[ -f "$dest" ]]; then
        if cmp -s "$file" "$dest"; then
            continue                       # already identical, nothing to do
        fi
        modified=$((modified + 1))
        echo "  M  $rel"
        if (( ! DRY_RUN )); then
            mkdir -p "$(dirname "$BACKUP/$rel")"
            cp -p "$dest" "$BACKUP/$rel"
        fi
    else
        added=$((added + 1))
        echo "  A  $rel"
    fi
    if (( ! DRY_RUN )); then
        mkdir -p "$(dirname "$dest")"
        cp -p "$file" "$dest"
    fi
done < <(find "$SRC" -type f ! -path '*/.git/*' ! -name '*.pyc' -print0 | sort -z)

echo
echo "$added added, $modified modified"
if (( DRY_RUN )); then
    echo "DRY RUN - nothing was written. Re-run without --dry-run to apply."
    exit 0
fi
[[ $modified -gt 0 ]] && echo "originals in $BACKUP  (rm -rf it once you are happy)"

cat <<'NEXT'

Next:

  1. pip install -r requirements.txt          # adds httpx

  2. Force every per-user config to rebuild from the new template:
         touch web_app/LLM_CONFIG_template.json

     Per-user configs live at web_app/config/<user_id>/LLM_CONFIG.json and are
     what ModelManager actually loads. They are regenerated from the template
     only when the template is NEWER (mtime), checked on /api/user/initialize.
     A config that does not rebuild has no Investigator seat, and _init raises
     the moment deep mode runs. The touch costs nothing and removes the doubt.

     Note this regenerates from tier defaults, so any per-agent model choices a
     user made in the UI are reset.

  3. Rebuild the executor image — the Dockerfile changed and now copies six
     kernel modules. Skipping this leaves you with a container that builds,
     starts, passes its health check, and has no deep mode:
         cd containers/executor && docker build -t bambooai-executor .

  4. Verify:
         python3 tests/delve_planner/verify_deployment.py
         python3 tests/delve_planner/verify_deployment.py http://<container>:5000

  5. Turn it on: planning=True is the switch. planning=False is unchanged.
NEXT
