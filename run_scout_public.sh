#!/bin/bash
# pebbles-scout public voice runner — scouts AI/consciousness/singularity content for @themeatfinger
set -a
source /Users/song/.secrets/shared.env
set +a

exec /Users/song/song-workspace/pebbles-scout/.venv/bin/pebbles-scout run \
    --principal /Users/song/song-workspace/pebbles-scout/principals/song-public.yaml \
    --store supabase
