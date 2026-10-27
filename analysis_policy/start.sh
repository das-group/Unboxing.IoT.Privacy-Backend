#!/bin/bash
set -e

# Start Xvfb
Xvfb :99 -screen 0 1280x720x24 -ac 2>/dev/null &
XVFB_PID=$!

# Wait for Xvfb to be ready
sleep 1

export DISPLAY=:99

# Start uvicorn
#uvicorn app:app --host 0.0.0.0 --port 8000 &
granian --host 0.0.0.0 --port 8080 --interface asgi app:app &
UVICORN_PID=$!

# If either process dies, kill the other and exit
wait $UVICORN_PID
kill $XVFB_PID

