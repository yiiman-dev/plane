#!/usr/bin/env bash
# =============================================================================
# plane-dev.sh — راه‌اندازی یک‌دستوری محیط توسعه‌ی محلی Plane روی همین مک
# (Apple M1 Pro / arm64 / macOS). جایگزین تمام دستورهای دستی compose و pnpm.
#
#   sh plane-dev.sh              # = up
#   sh plane-dev.sh up           # زیرساخت + api/worker/beat + وب(3000) + ادمین(3001)
#   sh plane-dev.sh down         # توقف کامل (volume ها پاک نمی‌شوند)
#   sh plane-dev.sh status       # جدول وضعیت و سلامت
#   sh plane-dev.sh doctor       # فقط بررسی پیش‌نیازها، هیچ تغییری نمی‌دهد
#   sh plane-dev.sh logs web     # دنبال کردن لاگ (web|admin|api|worker|beat-worker|migrator)
#   sh plane-dev.sh rebuild      # بیلد اجباری ایمیج amd64 سپس up
#   sh plane-dev.sh reset        # خطرناک: down -v + بیلد + up (بدون --yes سوال می‌پرسد)
#
# متغیرهای محیطی:
#   PLANE_FORCE_BUILD=1    حتی اگر ایمیج هست، دوباره بیلد کن
#   PLANE_SKIP_FRONTEND=1  فقط بک‌اند (بدون وب و ادمین)
#   PLANE_SKIP_ADMIN=1     پنل ادمین (god-mode روی 3001) بالا نیاید
#   PLANE_NODE_BIN=/path   اجباری کردن یک node مشخص
#   PLANE_API_PLATFORM=linux/amd64
# =============================================================================

set -u

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
ROOT="$SCRIPT_DIR"

COMPOSE_BASE="docker-compose-local.yml"
COMPOSE_OVERRIDE="docker-compose-local.nominedocker.yml"
API_IMAGE="plane-api-dev"
API_PLATFORM="${PLANE_API_PLATFORM:-linux/amd64}"

WEB_PORT=3000
ADMIN_PORT=3001
API_PORT=8000
# Host 6379 is taken by lobe-redis (another project on this machine), so Plane
# publishes Redis on 6380. See docker-compose-local.nominedocker.yml.
REDIS_PORT=6380

STATE_DIR="$ROOT/.devstack"
LOG_DIR="$STATE_DIR/logs"
RUN_DIR="$STATE_DIR/run"

if [ -t 1 ]; then
  C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YEL=$'\033[33m'
  C_BLU=$'\033[34m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
else
  C_RED=''; C_GRN=''; C_YEL=''; C_BLU=''; C_DIM=''; C_OFF=''
fi

say()  { printf '%s\n' "$*"; }
info() { printf '%s==>%s %s\n' "$C_BLU" "$C_OFF" "$*"; }
ok()   { printf '%s  ok%s %s\n' "$C_GRN" "$C_OFF" "$*"; }
warn() { printf '%swarn%s %s\n' "$C_YEL" "$C_OFF" "$*" >&2; }
err()  { printf '%sfail%s %s\n' "$C_RED" "$C_OFF" "$*" >&2; }
dim()  { printf '%s%s%s\n' "$C_DIM" "$*" "$C_OFF"; }
die()  { err "$*"; exit 1; }

dc() { docker compose -f "$COMPOSE_BASE" -f "$COMPOSE_OVERRIDE" "$@"; }

# ---------------------------------------------------------------- preflight --

ensure_docker() {
  command -v docker >/dev/null 2>&1 || die "docker نصب/active نیست."
  docker info >/dev/null 2>&1 || die "Docker Desktop در حال اجرا نیست (docker info fail شد)."
  docker compose version >/dev/null 2>&1 || die "docker compose (v2 plugin) در دسترس نیست."
  ok "docker daemon در دسترس است"
}

# فایل‌های .env را از .env.example می‌سازد (همان کار setup.sh، بدون pnpm install)
ensure_env() {
  mode="${1:-apply}"
  changed=0
  for svc in "" web api space admin live; do
    if [ -z "$svc" ]; then prefix="$ROOT/"; else prefix="$ROOT/apps/$svc/"; fi
    src="${prefix}.env.example"
    dst="${prefix}.env"
    [ -f "$src" ] || continue
    [ -f "$dst" ] && continue
    if [ "$mode" = "doctor" ]; then
      warn "کمبود: ${dst#$ROOT/}"
      continue
    fi
    cp "$src" "$dst" || die "کپی $src ناموفق بود."
    changed=1
    info "ساخته شد: ${dst#$ROOT/}"
  done

  if [ "$mode" = "apply" ] && ! grep -q '^SECRET_KEY=' "$ROOT/apps/api/.env" 2>/dev/null; then
    key=$(LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom | head -c 50)
    printf '\nSECRET_KEY="%s"\n' "$key" >> "$ROOT/apps/api/.env"
    ok "SECRET_KEY تولید و به apps/api/.env اضافه شد"
  fi
  # `live` runs on the host and talks to Redis over localhost, so its .env must
  # point at the published port (6380 here), not the container's 6379.
  live_env="$ROOT/apps/live/.env"
  if [ "$mode" = "apply" ] && [ -f "$live_env" ]; then
    if grep -q '^REDIS_PORT=6379$' "$live_env" || grep -q 'redis://localhost:6379/' "$live_env"; then
      sed -i.bak -e "s/^REDIS_PORT=.*/REDIS_PORT=$REDIS_PORT/" \
                 -e "s#redis://localhost:6379/#redis://localhost:$REDIS_PORT/#" "$live_env"
      rm -f "$live_env.bak"
      ok "apps/live/.env روی پورت Redis منتشرشده ($REDIS_PORT) هماهنگ شد"
    fi
  fi

  [ "$changed" = 0 ] && ok "فایل‌های .env موجودند"
  return 0
}

require_node_modules() {
  if [ "${PLANE_SKIP_FRONTEND:-0}" = 1 ]; then
    dim "PLANE_SKIP_FRONTEND=1 → بررسی node_modules رد شد"
    return 0
  fi
  missing=0
  for app in web admin; do
    [ "$app" = admin ] && [ "${PLANE_SKIP_ADMIN:-0}" = 1 ] && continue
    [ -d "$ROOT/apps/$app/node_modules/@react-router" ] && continue
    err "apps/$app/node_modules ناقص است."
    missing=1
  done
  if [ "$missing" = 0 ]; then ok "node_modules فرانت‌اند موجود است"; return 0; fi
  cat >&2 <<EOF
  نصب وابستگی‌ها (یک‌بار):

      corepack enable pnpm     # اگر corepack در PATH نبود:
                               # /Applications/Orkas.app/Contents/Resources/runtime/node/darwin-arm64/bin/corepack enable pnpm
      cd $ROOT && pnpm install
EOF
  exit 1
}

# --- انتخاب node -----------------------------------------------------------
# دلیل: node استاتیک داخل Orkas با Hardened Runtime و TeamID امضا شده و macOS
# لود ماژول native بدون TeamID (مثل binding رول‌داون) را بلاک می‌کند:
#   "code signature ... not valid for use in process: mapping process and mapped
#    file (non-platform) have different Team IDs"
# node هوم‌برو TeamID ندارد و بدون خطا لود می‌شود.
resolve_node() {
  NODE_BIN=""
  binding=$(find "$ROOT/node_modules/.pnpm" -maxdepth 5 -name 'rolldown-binding.*.node' 2>/dev/null | head -1)

  if [ -n "${PLANE_NODE_BIN:-}" ]; then
    [ -x "${PLANE_NODE_BIN}" ] || die "PLANE_NODE_BIN اجرایی نیست: ${PLANE_NODE_BIN}"
    NODE_BIN="$PLANE_NODE_BIN"
  elif [ -n "$binding" ]; then
    for cand in $(ls -td /opt/homebrew/Cellar/node/*/bin/node 2>/dev/null) /opt/homebrew/bin/node; do
      [ -x "$cand" ] || continue
      if "$cand" -e 'try{process.dlopen(module,process.argv[1]);process.exit(0)}catch(e){process.exit(1)}' "$binding" 2>/dev/null; then
        NODE_BIN="$cand"
        break
      fi
    done
    if [ -z "$NODE_BIN" ]; then
      err "هیچ node سازگاری برای لود binding رول‌داون پیدا نشد."
      cat >&2 <<EOF
  علت محتمل: node روی PATH با TeamID امضا شده (مثل node داخل Orkas) و macOS
  لود ماژول native بدون TeamID را بلاک می‌کند.
  راه‌حل: node هوم‌برو را جلوی node پیش‌فرض بگذارید یا صریح بدهید:

      PLANE_NODE_BIN=/opt/homebrew/Cellar/node/26.0.0/bin/node sh plane-dev.sh up
EOF
      exit 1
    fi
  else
    NODE_BIN=$(command -v node 2>/dev/null)
    [ -n "$NODE_BIN" ] || die "node در PATH نیست."
  fi
  ok "node: $NODE_BIN ($("$NODE_BIN" -v 2>/dev/null))"
}

# ------------------------------------------------------------------ helpers --

port_pids() { lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | sort -u; }
http_code() { curl -s -o /dev/null -m 4 -w '%{http_code}' "$1" 2>/dev/null; }

wait_http() {
  url="$1"; timeout="${2:-180}"; waited=0; code=""
  while [ "$waited" -lt "$timeout" ]; do
    code=$(http_code "$url")
    case "$code" in 2*|3*) ok "$url → HTTP $code (${waited}s)"; return 0 ;; esac
    sleep 2; waited=$((waited + 2))
  done
  err "$url بعد از ${timeout}s پاسخ نداد (آخرین کد: ${code:-000})"
  return 1
}

free_port() {
  port="$1"; app="$2"; strict="${3:-1}"; killed=0; waited=0; busy=""; pid=""; cmd=""
  while :; do
    busy=$(port_pids "$port")
    [ -z "$busy" ] && break
    for pid in $busy; do
      cmd=$(ps -o command= -p "$pid" 2>/dev/null)
      case "$cmd" in
        *"$ROOT/apps/$app"*) kill "$pid" 2>/dev/null; killed=1 ;;
        "")                   kill -9 "$pid" 2>/dev/null ;;
        *)
          if [ "$strict" = 1 ]; then
            err "پورت $port را پروسه‌ی غریبه گرفته (pid $pid): $cmd"
            die "آن پروسه را ببندید یا پورت را تغییر دهید."
          fi
          warn "پورت $port را پروسه‌ی غریبه گرفته (pid $pid) — دست‌نخورده گذاشته شد"
          ;;
      esac
    done
    [ "$waited" -gt 15 ] && break
    sleep 1; waited=$((waited + 1))
  done
  [ "$killed" = 1 ] && info "پروسه‌ی قدیمی $app روی پورت $port متوقف شد"
  return 0
}

kill_frontend() {
  app="$1"; pidfile="$RUN_DIR/$app.pid"; pid=""
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile" 2>/dev/null)
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
    rm -f "$pidfile"
  fi
}

# هر پروسه‌ای که dev server این اپ را اجرا کند (شامل wrapper های .bin) می‌کشد
kill_app_procs() {
  app="$1"; pids=""
  pids=$(ps -eo pid=,command= 2>/dev/null \
    | grep -F "$ROOT/apps/$app" \
    | grep -E 'bin\.cjs|react-router|vite' \
    | grep -v grep \
    | awk '{print $1}')
  [ -z "$pids" ] && return 0
  for pid in $pids; do kill "$pid" 2>/dev/null; done
  sleep 1
  for pid in $pids; do kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null; done
  info "پروسه‌های قدیمی $app متوقف شدند: $(echo $pids)"
  return 0
}

start_frontend() {
  app="$1"; port="$2"; pidfile="$RUN_DIR/$app.pid"; log="$LOG_DIR/$app.log"; url="http://localhost:$port"

  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile" 2>/dev/null)" 2>/dev/null && [ "$(http_code "$url")" != "000" ]; then
    ok "$app از قبل روی پورت $port بالاست"
    return 0
  fi
  kill_frontend "$app"
  kill_app_procs "$app"
  free_port "$port" "$app"

  mkdir -p "$LOG_DIR" "$RUN_DIR"
  cd "$ROOT/apps/$app" || return 1
  nohup "$NODE_BIN" node_modules/@react-router/dev/bin.cjs dev --port "$port" > "$log" 2>&1 &
  echo $! > "$pidfile"
  cd "$ROOT" || true
  info "$app در حال اجرا روی پورت $port (لاگ: ${log#$ROOT/})"
  wait_http "$url" 240 || { tail -n 25 "$log" >&2; return 1; }
  port_pids "$port" | head -1 > "$pidfile"
}

# --------------------------------------------------------------------- up ---

do_build() {
  force="${1:-0}"
  if [ "$force" != 1 ] && [ "${PLANE_FORCE_BUILD:-0}" != 1 ] && docker image inspect "$API_IMAGE" >/dev/null 2>&1; then
    ok "ایمیج $API_IMAGE موجود است — برای بیلد اجباری: sh plane-dev.sh rebuild"
    return 0
  fi
  info "بیلد ایمیج $API_IMAGE برای $API_PLATFORM — بیلد اول حدود ۸ تا ۱۰ دقیقه (شبیه‌سازی‌شده)"
  # پلتفرم از کلید platform در override خوانده می‌شود (compose v5 کلید build --platform ندارد).
  DOCKER_DEFAULT_PLATFORM="$API_PLATFORM" dc build api || die "بیلد api شکست خورد."
  arch=$(docker image inspect "$API_IMAGE" --format '{{.Architecture}}' 2>/dev/null)
  ok "ایمیج $API_IMAGE ساخته شد (معماری: ${arch:-نامشخص}) — worker/beat/migrator همین ایمیج را استفاده می‌کنند"
}

do_up() {
  say ""
  say "${C_BLU}▌ Plane local dev stack${C_OFF}  —  root: $ROOT"
  say ""
  ensure_docker
  ensure_env apply
  if [ "${PLANE_SKIP_FRONTEND:-0}" != 1 ]; then
    require_node_modules
    resolve_node
  fi

  do_build

  info "بالا آوردن سرویس‌های docker"
  dc up -d || die "docker compose up شکست خورد."

  info "منتظر مهاجرت دیتابیس و بالا آمدن API ..."
  wait_http "http://localhost:$API_PORT/" 420 || {
    err "API بالا نیامد. ۴۰ خط آخر لاگ:"
    dc logs --tail 40 api >&2
    exit 1
  }

  if [ "${PLANE_SKIP_FRONTEND:-0}" = 1 ]; then
    info "PLANE_SKIP_FRONTEND=1 → فقط بک‌اند اجرا شد."
  else
    start_frontend web "$WEB_PORT" || exit 1
    if [ "${PLANE_SKIP_ADMIN:-0}" = 1 ]; then
      warn "PLANE_SKIP_ADMIN=1 → پنل ادمین اجرا نشد؛ فرم ساخت ادمین کار نمی‌کند."
    else
      start_frontend admin "$ADMIN_PORT" || warn "ادمین بالا نیامد؛ فرم setup روی 3001 در دسترس نخواهد بود."
    fi
  fi

  say ""
  ok "همه‌چیز آماده است:"
  dim "  وب        http://localhost:3000"
  [ "${PLANE_SKIP_ADMIN:-0}" = 1 ] || dim "  ادمین     http://localhost:3001/god-mode/"
  dim "  API       http://localhost:8000"
  dim "  S3        http://localhost:9000"
  say ""
  dim "  اگر وب به صفحه‌ی setup رفت یا دکمه‌ی Get started به 3001 پرش کرد،"
  dim "  یعنی is_setup_done هنوز false است: از همان صفحه‌ی ادمین اولین کاربر admin را بسازید."
  say ""
}

# ------------------------------------------------------------------- down ---

do_down() {
  info "توقف dev server های فرانت‌اند"
  kill_frontend web
  kill_frontend admin
  kill_app_procs web
  kill_app_procs admin
  free_port "$WEB_PORT" web 0 || true
  free_port "$ADMIN_PORT" admin 0 || true
  info "توقف کانتینرها"
  dc down || die "docker compose down شکست خورد."
  ok "متوقف شد (داده‌ها در volume ها باقی است)."
}

do_reset() {
  if [ "${1:-}" != "--yes" ]; then
    say "این دستور volume ها (دیتابیس، S3، redis) را پاک می‌کند و از نو می‌سازد."
    printf 'ادامه می‌دهی؟ [y/N] '
    read -r ans
    case "$ans" in y|Y|yes|YES) ;; *) say "لغو شد."; exit 0 ;; esac
  fi
  do_down
  info "پاک کردن volume ها و ایمیج محلی"
  dc down -v --rmi local || true
  do_up
}

# ----------------------------------------------------------------- status ---

do_status() {
  say ""
  say "${C_BLU}▌ کانتینرها${C_OFF}"
  dc ps 2>/dev/null || warn "compose قابل خواندن نیست."
  say ""
  say "${C_BLU}▌ سلامت سرویس‌ها${C_OFF}"
  for entry in "http://localhost:$API_PORT/|api  8000" \
               "http://localhost:$WEB_PORT/|web  3000" \
               "http://localhost:$ADMIN_PORT/|admin 3001" \
               "http://localhost:9000/|s3   9000"; do
    url=${entry%%|*}; label=${entry##*|}; code=$(http_code "$url")
    case "$code" in
      2*|3*) printf '  %s%-14s%s HTTP %s\n' "$C_GRN" "$label" "$C_OFF" "$code" ;;
      000)   printf '  %s%-14s%s down\n'   "$C_RED" "$label" "$C_OFF" ;;
      *)     printf '  %s%-14s%s HTTP %s\n' "$C_YEL" "$label" "$C_OFF" "$code" ;;
    esac
  done
  say ""
  for app in web admin; do
    pidfile="$RUN_DIR/$app.pid"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile" 2>/dev/null)" 2>/dev/null; then
      printf '  %s%-14s%s pid %s\n' "$C_GRN" "$app (dev)" "$C_OFF" "$(cat "$pidfile")"
    else
      printf '  %s%-14s%s %s\n' "$C_DIM" "$app (dev)" "$C_OFF" "not managed by this script"
    fi
  done
  say ""
}

do_doctor() {
  say ""
  say "${C_BLU}▌ بررسی پیش‌نیازها${C_OFF}  (بدون هیچ تغییری)"
  ensure_docker
  ensure_env doctor
  require_node_modules
  resolve_node
  ok "compose files: $COMPOSE_BASE + $COMPOSE_OVERRIDE"
  if docker image inspect "$API_IMAGE" >/dev/null 2>&1; then
    ok "ایمیج $API_IMAGE موجود است"
  else
    warn "ایمیج $API_IMAGE وجود ندارد → اولین up حدود ۸-۱۰ دقیقه طول می‌کشد."
  fi
  for entry in "$API_PORT:API" "$WEB_PORT:وب" "$ADMIN_PORT:ادمین" "9000:S3" "5433:postgres" "$REDIS_PORT:redis"; do
    port=${entry%%:*}; pids=$(port_pids "$port")
    if [ -n "$pids" ]; then
      printf '  پورت %-6s (%s) استفاده‌شده توسط: %s\n' "$port" "${entry##*:}" "$(echo $pids | tr '\n' ' ')"
    else
      printf '  پورت %-6s (%s) آزاد\n' "$port" "${entry##*:}"
    fi
  done
  say ""
  dim "  یادآوری: پورت 3100 (اپ live) را پروژه‌ی db-designer گرفته است."
  say ""
}

do_logs() {
  target="${1:-web}"
  case "$target" in
    web|admin)
      mkdir -p "$LOG_DIR"
      [ -f "$LOG_DIR/$target.log" ] || die "لاگی برای $target نیست؛ اول sh plane-dev.sh up"
      tail -n 200 -f "$LOG_DIR/$target.log"
      ;;
    api|worker|beat-worker|migrator) dc logs --tail 200 -f "$target" ;;
    *) die "سرویس نامعتبر: $target (web|admin|api|worker|beat-worker|migrator)" ;;
  esac
}

usage() { sed -n '2,22p' "$0" | sed 's/^#\{1,\} \{0,1\}//'; }

case "${1:-up}" in
  up)              do_up ;;
  down)            do_down ;;
  restart)         do_down; do_up ;;
  status)          do_status ;;
  doctor)          do_doctor ;;
  rebuild)         do_build 1; do_up ;;
  reset)           do_reset "${2:-}" ;;
  logs)            shift; do_logs "${1:-web}" ;;
  -h|--help|help)  usage ;;
  *)               err "دستور ناشناخته: $1"; usage; exit 1 ;;
esac