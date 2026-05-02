#!/bin/sh
# Sets up a Fly.io app for the AI News Agent.
# Reads the app name from fly.toml, creates the app if needed,
# then sets all .env secrets (excluding vars already in fly.toml [env]).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FLY_TOML="${PROJECT_DIR}/fly.toml"
ENV_FILE="${PROJECT_DIR}/.env"

if [ ! -f "$FLY_TOML" ]; then
    echo "Error: fly.toml not found at ${FLY_TOML}" >&2
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: .env not found at ${ENV_FILE}" >&2
    echo "Copy .env.example to .env and fill in the values." >&2
    exit 1
fi

APP_NAME=$(grep '^app\s*=' "$FLY_TOML" | head -1 | sed 's/^app\s*=\s*"\(.*\)"/\1/')
if [ -z "$APP_NAME" ]; then
    echo "Error: could not parse app name from fly.toml" >&2
    exit 1
fi

echo "App name: ${APP_NAME}"

# Collect keys already defined in fly.toml [env] section
TOML_KEYS=$(awk '/^\[env\]/{found=1; next} found && /^\[/{found=0} found && /=/{gsub(/[ \t]*=.*/, ""); print}' "$FLY_TOML")

# Create app if it doesn't exist
if ! fly apps list 2>/dev/null | grep -q "^${APP_NAME}"; then
    echo "Creating app ${APP_NAME}..."
    fly apps create "$APP_NAME"
else
    echo "App ${APP_NAME} already exists."
fi

# Set secrets from .env, skipping keys already in [env] and empty values
echo "Setting secrets from .env..."
secrets_args=""
while IFS= read -r line; do
    # Skip comments and empty lines
    case "$line" in
        "#"*|"") continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    # Skip empty values
    if [ -z "$value" ]; then
        continue
    fi
    # Skip keys already in fly.toml [env]
    skip=0
    for toml_key in $TOML_KEYS; do
        if [ "$key" = "$toml_key" ]; then
            skip=1
            break
        fi
    done
    if [ "$skip" = "0" ]; then
        secrets_args="${secrets_args} ${key}=${value}"
    fi
done < "$ENV_FILE"

if [ -n "$secrets_args" ]; then
    # shellcheck disable=SC2086
    fly secrets set --app "$APP_NAME" $secrets_args
    echo "Secrets set successfully."
else
    echo "No secrets to set."
fi

echo "Setup complete. Run 'fly deploy' to deploy the app."
