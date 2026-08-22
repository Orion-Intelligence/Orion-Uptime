#!/bin/bash
set -e
set -o pipefail

PROJECT_NAME="orion-uptime"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

COMPOSE_FILE="docker-compose.yml"
PRODUCTION_COMPOSE_FILE="docker-compose-production.yml"
ENV_FILE=".env"
LOCAL_SSL_DIR="nginx/certs/local"
LOCAL_SSL_CERT="$LOCAL_SSL_DIR/localhost-cert.pem"
LOCAL_SSL_KEY="$LOCAL_SSL_DIR/localhost-key.pem"
CLIENT_DIR="client"
CLIENT_BUILD_DIR="client/build"
BACKEND_BUILD_DIR="backend/build"
NG_SERVE_PID_FILE="/tmp/orion-uptime-ng-serve.pid"
NG_SERVE_PORT="${NG_SERVE_PORT:-4400}"
NG_SERVE_URL="http://127.0.0.1:${NG_SERVE_PORT}/"
READY_TIMEOUT="${READY_TIMEOUT:-300}"

resolve_app_port() {
    if [ -z "$APP_PORT" ] && [ -f "$ENV_FILE" ]; then
        APP_PORT="$(sed -n 's/^APP_PORT=//p' "$ENV_FILE" | tail -1 | tr -d '\042\047')"
    fi
    APP_PORT="${APP_PORT:-8600}"
    APP_URL="http://127.0.0.1:${APP_PORT}/"
}

usage() {
    cat <<'EOF'
Usage:
  ./run.sh lint         Lint the client (eslint + stylelint) and the backend (ruff)
  ./run.sh lint -f      Lint and apply every available auto-fix
  ./run.sh test         Run the backend test suite (pytest)
  ./run.sh test -c      Run the backend test suite with coverage and write backend/coverage.xml
  ./run.sh build        Install client dependencies, build the client, build images and start the stack
  ./run.sh build -d     Build and start the backend only, with live reload on backend changes
  ./run.sh build -b     Rebuild images and start the stack, reusing the existing client build
  ./run.sh build -t     Build an Istanbul-instrumented client for Cypress coverage, then build images and start the stack
  ./run.sh build -p     Same as ./run.sh production
  ./run.sh serve        Start the stack and run the Angular dev server on :4400
  ./run.sh production   Build the client and images and start the production stack (nginx on :80/:443 with Let's Encrypt for PRODUCTION_DOMAIN)
  ./run.sh stop         Stop the Angular dev server and the stack
  ./run.sh              Start the stack from the images that already exist

The stack is published on APP_PORT (.env, default 8600). After ./run.sh build -t, run
"cd client && npm run cypress:run:coverage" against https://127.0.0.1:APP_HTTPS_PORT to
collect client coverage in client/coverage/lcov.info. After ./run.sh build -d,
run the client yourself with "cd client && ng serve", which opens on :4400.
EOF
}

COMPOSE_FILES=(-f "$COMPOSE_FILE")

compose() {
    docker compose -p "$PROJECT_NAME" "${COMPOSE_FILES[@]}" "$@"
}

use_compose_file() {
    COMPOSE_FILE="$1"
    COMPOSE_FILES=(-f "$COMPOSE_FILE")
}

env_value() {
    sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | tr -d '\042\047'
}

ensure_local_ssl_cert() {
    mkdir -p "$LOCAL_SSL_DIR"
    if [ -f "$LOCAL_SSL_CERT" ] && [ -f "$LOCAL_SSL_KEY" ]; then
        return 0
    fi
    openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
        -keyout "$LOCAL_SSL_KEY" \
        -out "$LOCAL_SSL_CERT" \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1
    chmod 600 "$LOCAL_SSL_KEY"
    echo "Generated a self-signed development certificate in $LOCAL_SSL_DIR"
}

start_production_stack() {
    ensure_env_file
    ensure_production_settings
    stop_docker
    install_client_dependencies
    client_build
    use_compose_file "$PRODUCTION_COMPOSE_FILE"
    compose build --pull
    compose up -d
    wait_for_application_services
    echo "Orion Uptime production stack is running; nginx serves https://$PRODUCTION_DOMAIN/ and requests its Let's Encrypt certificate automatically."
}

ensure_production_settings() {
    PRODUCTION_DOMAIN="$(env_value PRODUCTION_DOMAIN)"
    LETSENCRYPT_EMAIL="$(env_value LETSENCRYPT_EMAIL)"
    if [ -z "$PRODUCTION_DOMAIN" ] || [ "$PRODUCTION_DOMAIN" = "localhost" ] || [ "$PRODUCTION_DOMAIN" = "*" ]; then
        echo "PRODUCTION_DOMAIN in $ENV_FILE must be the public hostname nginx should serve (for example uptime.orionintelligence.org)." >&2
        exit 1
    fi
    if [ -z "$LETSENCRYPT_EMAIL" ]; then
        echo "Note: LETSENCRYPT_EMAIL is empty in $ENV_FILE; the certificate is still issued, but Let's Encrypt cannot send expiry notices."
    fi
    if [ "$(env_value APP_ENV)" = "development" ]; then
        echo "Note: APP_ENV is development in $ENV_FILE; the production stack overrides it to production for its containers."
    fi
}

ensure_env_file() {
    if [ -f "$ENV_FILE" ]; then
        return 0
    fi

    echo "Missing $ENV_FILE. Create it with the required application, database, and authentication settings." >&2
    exit 1
}

ng_serve_pids() {
    local pid cwd
    for pid in $(pgrep -f "ng serve|npm run serve" 2>/dev/null); do
        cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
        case "$cwd" in
            "$ROOT_DIR"|"$ROOT_DIR"/*) echo "$pid" ;;
        esac
    done
}

ng_serve_is_running() {
    [ -n "$(ng_serve_pids)" ]
}

stop_ng_serve() {
    local pids waited

    if [ -f "$NG_SERVE_PID_FILE" ]; then
        kill -9 "$(cat "$NG_SERVE_PID_FILE")" 2>/dev/null || true
        rm -f "$NG_SERVE_PID_FILE"
    fi

    pids="$(ng_serve_pids)"
    if [ -n "$pids" ]; then
        printf '%s\n' "$pids" | xargs -r kill -9 2>/dev/null || true
    fi

    waited=0
    while ng_serve_is_running && [ "$waited" -lt 30 ]; do
        sleep 1
        waited=$((waited + 1))
    done
}

stop_docker() {
    local file
    for file in "$COMPOSE_FILE" "$PRODUCTION_COMPOSE_FILE"; do
        docker compose -p "$PROJECT_NAME" -f "$file" down --remove-orphans >/dev/null 2>&1 || true
    done
}

ruff_bin() {
    if [ -x "$ROOT_DIR/.venv/bin/ruff" ]; then
        echo "$ROOT_DIR/.venv/bin/ruff"
    elif command -v ruff >/dev/null 2>&1; then
        command -v ruff
    fi
}

backend_python() {
    if [ -x "$ROOT_DIR/.venv/bin/python" ]; then
        echo "$ROOT_DIR/.venv/bin/python"
    else
        command -v python3
    fi
}

run_backend_tests() {
    (cd "$ROOT_DIR/backend" && "$(backend_python)" -m pytest -q "$@")
}

lint_backend() {
    local ruff
    ruff="$(ruff_bin)"
    if [ -z "$ruff" ]; then
        echo "ruff is not installed; run .venv/bin/python -m pip install ruff" >&2
        return 1
    fi
    "$ruff" check backend/main.py backend/configs backend/orion backend/routes backend/seeder backend/tests "$@"
}

lint_client() {
    (cd "$CLIENT_DIR" && npm run "$1")
}

run_lint() {
    local failed=0
    if [ "$1" = "-f" ]; then
        lint_client lint:fix || failed=1
        lint_backend --fix || failed=1
    else
        lint_client lint || failed=1
        lint_backend || failed=1
    fi
    return "$failed"
}

install_client_dependencies() {
    if [ ! -f "$CLIENT_DIR/package-lock.json" ]; then
        echo "Missing client lockfile; refusing unpinned dependency install" >&2
        exit 1
    fi

    if ng_serve_is_running; then
        echo "Angular dev server is running; preserving node_modules and skipping npm ci"
    else
        (cd "$CLIENT_DIR" && npm ci)
    fi
    lint_client lint
}

client_build() {
    local configuration="${1:-production}"
    (cd "$CLIENT_DIR" && npx ng build --configuration "$configuration")
    if [ "$configuration" = "instrumented" ]; then
        (cd "$CLIENT_DIR" && node scripts/instrument-build.mjs build)
    fi

    if [ ! -f "$CLIENT_BUILD_DIR/index.html" ]; then
        echo "Client build produced no $CLIENT_BUILD_DIR/index.html" >&2
        exit 1
    fi

    rm -rf "$BACKEND_BUILD_DIR"
    mkdir -p "$BACKEND_BUILD_DIR"
    cp -r "$CLIENT_BUILD_DIR"/. "$BACKEND_BUILD_DIR"/
}

ensure_client_build() {
    if [ ! -f "$BACKEND_BUILD_DIR/index.html" ]; then
        install_client_dependencies
        client_build
    fi
}

wait_for_application_services() {
    local container health deadline

    resolve_app_port
    echo "Waiting for application services to become ready..."
    deadline=$((SECONDS + READY_TIMEOUT))

    while true; do
        container="$(compose ps -q backend 2>/dev/null || true)"
        if [ -n "$container" ]; then
            health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
            case "$health" in
                healthy)
                    echo "Orion Uptime is ready on $APP_URL"
                    return 0
                    ;;
                unhealthy|exited|dead)
                    echo "Backend failed before becoming ready (container: $health)." >&2
                    compose logs --tail 100 backend >&2 || true
                    exit 1
                    ;;
            esac
        fi

        if [ "$SECONDS" -ge "$deadline" ]; then
            echo "Timed out after ${READY_TIMEOUT}s waiting for the backend to become healthy." >&2
            compose ps >&2 || true
            compose logs --tail 100 backend >&2 || true
            exit 1
        fi

        sleep 2
    done
}

restart_ng_serve() {
    stop_ng_serve

    (
        cd "$CLIENT_DIR" || exit 1
        nohup npm run serve -- --host 127.0.0.1 --port "$NG_SERVE_PORT" >/tmp/orion-uptime-ng-serve.log 2>&1 &
        echo $! > "$NG_SERVE_PID_FILE"
    )

    until curl -fsS -o /dev/null "$NG_SERVE_URL" >/dev/null 2>&1; do
        sleep 2
    done
    echo "Angular dev server is ready on $NG_SERVE_URL"
}

COMMAND="$1"
FLAG="$2"

case "$COMMAND" in
    lint)
        case "$FLAG" in
            ""|-f)
                run_lint "$FLAG"
                exit $?
                ;;
            *)
                echo "Unknown lint flag: $FLAG" >&2
                usage >&2
                exit 1
                ;;
        esac
        ;;
    test)
        case "$FLAG" in
            "")
                run_backend_tests
                exit $?
                ;;
            -c)
                run_backend_tests --cov=. --cov-report=term-missing --cov-report=xml:coverage.xml
                exit $?
                ;;
            *)
                echo "Unknown test flag: $FLAG" >&2
                usage >&2
                exit 1
                ;;
        esac
        ;;
    stop)
        stop_ng_serve
        stop_docker
        echo "Orion Uptime service stopped"
        exit 0
        ;;
    build)
        ensure_env_file
        case "$FLAG" in
            "")
                stop_docker
                install_client_dependencies
                client_build
                ;;
            -d)
                stop_docker
                mkdir -p "$BACKEND_BUILD_DIR"
                ;;
            -b)
                stop_docker
                ensure_client_build
                ;;
            -t)
                stop_docker
                install_client_dependencies
                client_build instrumented
                ;;
            -p)
                start_production_stack
                exit 0
                ;;
            *)
                echo "Unknown build flag: $FLAG" >&2
                usage >&2
                exit 1
                ;;
        esac
        ensure_local_ssl_cert
        compose build --pull
        compose up -d
        wait_for_application_services
        ;;
    production)
        start_production_stack
        ;;
    serve)
        ensure_env_file
        ensure_client_build
        ensure_local_ssl_cert
        compose up -d
        wait_for_application_services
        restart_ng_serve
        ;;
    "")
        ensure_env_file
        ensure_client_build
        ensure_local_ssl_cert
        compose up -d
        wait_for_application_services
        ;;
    *)
        usage >&2
        exit 1
        ;;
esac
