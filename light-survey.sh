#!/bin/bash

# ================== CONFIGURATION ==================
TOP_LEVEL_DIR="/home/scott/sav-prime"
 MIRROR_IPS=(
    "92.118.206.28"
    "15.204.88.113"
)
# git://92.118.206.28/test-project.git
MIRROR_URL_PATTERN="git://%s/%s.git"     # %s = IP, %s = repo folder name

# Number of most recent refs to check per repo
RECENT_COUNT=25
# ==================================================

if [ ! -d "$TOP_LEVEL_DIR" ]; then
    echo "Error: Directory $TOP_LEVEL_DIR does not exist"
    exit 1
fi

echo "=== Git Mirror Sync Health Check ==="
echo "Top-level directory : $TOP_LEVEL_DIR"
echo "Mirrors to check    : ${MIRROR_IPS[*]}"
echo "Recent refs to check: $RECENT_COUNT"
echo "==========================================="

cd "$TOP_LEVEL_DIR" || exit 1

for repo_dir in */; do
    repo_dir=${repo_dir%/}

    # Skip non-git directories
    if [ ! -d "$repo_dir/.git" ] && [ ! -f "$repo_dir/HEAD" ]; then
        continue
    fi

    echo -e "\n→ Repository: $repo_dir"

    cd "$repo_dir" 2>/dev/null || continue

    # Get most recent refs locally (sorted by committerdate)
    mapfile -t recent_refs < <(
        git for-each-ref --sort=-committerdate \
            --format='%(refname)' \
            --count="$RECENT_COUNT" \
            refs/heads/ refs/tags/ 2>/dev/null
    )

    if [ ${#recent_refs[@]} -eq 0 ]; then
        echo "   No refs found. Skipping."
        cd "$TOP_LEVEL_DIR" || exit 1
        continue
    fi

    mismatch_found=false

    for mirror_ip in "${MIRROR_IPS[@]}"; do
        mirror_url=$(printf "$MIRROR_URL_PATTERN" "$mirror_ip" "$repo_dir")
        echo "   Checking mirror: $mirror_ip"

        for ref in "${recent_refs[@]}"; do
            local_oid=$(git rev-parse --quiet --verify "$ref" 2>/dev/null)
            mirror_oid=$(git ls-remote --refs --quiet "$mirror_url" "$ref" | awk '{print $1}')

            if [ -z "$mirror_oid" ]; then
                echo "      ⚠  $ref → Not found on mirror"
                mismatch_found=true
                continue
            fi

            if [ "$local_oid" = "$mirror_oid" ]; then
                echo "      ✓  $ref"
            else
                echo "      ✗  $ref MISMATCH"
                echo "         Local   : ${local_oid:-<missing>}"
                echo "         Mirror  : ${mirror_oid:-<missing>}"
                mismatch_found=true
            fi
        done
    done

    if [ "$mismatch_found" = false ]; then
        echo "   All checked refs are in sync across mirrors."
    fi

    cd "$TOP_LEVEL_DIR" || exit 1
done

echo -e "\n=== Check completed ==="