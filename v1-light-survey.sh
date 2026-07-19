#!/bin/bash
mapfile -t recent_refs < <(
  git for-each-ref --sort=-committerdate --format='%(refname)' --count=25 refs/heads/ refs/tags/
)

echo "Checking ${#recent_refs[@]} recent refs against mirrors..."

for ref in "${recent_refs[@]}"; do
    primary_oid=$(git rev-parse "$ref")

    for mirror in 92.118.206.28 15.204.88.113; do
        mirror_oid=$(git ls-remote --refs --quiet "$mirror" "$ref" | awk '{print $1}')

        if [ "$primary_oid" = "$mirror_oid" ]; then
            echo "✓ $ref matches on $mirror"
        else
            echo "MISMATCH on $mirror for $ref"
            echo " Primary: $primary_oid"
            echo " Mirror : $mirror_oid"
        fi
    done
done