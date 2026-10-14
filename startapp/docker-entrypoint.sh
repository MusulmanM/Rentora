#!/bin/sh
set -e

mkdir -p "${MEDIA_ROOT:-/data/media}" "${CHAT_MEDIA_ROOT:-/data/chat-media}"

# Only the web container migrates; the Telegram bot container starts with RUN_MIGRATIONS=0.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python manage.py migrate --noinput
fi

exec "$@"
