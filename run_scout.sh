#!/bin/bash
# pebbles-scout daemon runner — sources shared.env then runs one Scout tick.
# Called by launchd every 30 minutes via com.song.pebbles-scout.plist.

set -a
source /Users/song/.secrets/shared.env
set +a

exec /Users/song/song-workspace/pebbles-scout/.venv/bin/pebbles-scout run \
    --principal /Users/song/song-workspace/pebbles-scout/principals/song.yaml \
    --store supabase
