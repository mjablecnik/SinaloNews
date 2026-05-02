#!/bin/sh
# fly-setup.sh — Create Fly.io app and set secrets from .env

set -e

APP_NAME=$(grep '^app\s*=' fly.toml | head -n 1 | sed 's/app\s*=\s*"\([^"]*\)"/\1/')
if [ -z "$APP_NAME" ]; then
    echo "Could not parse app name from fly.toml" >&2
    exit 1
fi

echo "App name: $APP_NAME"

# Create app if it doesn't exist
if ! fly apps list 2>/dev/null | grep -q "^$APP_NAME"; then
    echo "Creating app $APP_NAME..."
    fly apps create "$APP_NAME"
else
    echo "App $APP_NAME already exists."
fi

# Keys defined in fly.toml [env] section — do not set as secrets
FLY_ENV_KEYS="APP_HOST APP_PORT REQUEST_DELAY_SECONDS REQUEST_TIMEOUT_SECONDS USER_AGENT"

# Read .env and set secrets for keys not already in fly.toml
if [ ! -f .env ]; then
    echo ".env file not found. Create one from .env.example first." >&2
    exit 1
fi

secrets_args=""
while IFS= read -r line || [ -n "$line" ]; do
    # Skip comments and blank lines
    case "$line" in
        \#*|"") continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    # Skip if key is in fly.toml [env] section
    skip=0
    for env_key in $FLY_ENV_KEYS; do
        if [ "$key" = "$env_key" ]; then
            skip=1
            break
        fi
    done
    if [ "$skip" = "0" ]; then
        secrets_args="$secrets_args $key=$value"
    fi
done < .env

if [ -n "$secrets_args" ]; then
    echo "Setting secrets..."
    eval "fly secrets set $secrets_args"
else
    echo "No secrets to set."
fi

echo "Setup complete. Run 'fly deploy' to deploy."
