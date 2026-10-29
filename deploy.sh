#!/bin/bash
# ===========================================================
# Printer Agent – One-Command Cloud VPS Deployment Script
# ===========================================================
# Tested on: Ubuntu 22.04 / Debian 12
#
# USAGE:
#   chmod +x deploy.sh
#   ./deploy.sh                     # Interactive setup
#   ./deploy.sh --no-ssl            # HTTP only (for testing)
#   ./deploy.sh --domain example.com   # Auto SSL via Let's Encrypt
# ===========================================================

set -euo pipefail

# ── Configurable Defaults ────────────────────────────────────
DOMAIN=""
ENABLE_SSL=true
ADMIN_EMAIL_DEFAULT="admin@printagent.com"
ADMIN_PASSWORD_DEFAULT="admin123"
APP_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Color output ─────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

banner() {
  echo ""
  echo "================================================================"
  echo "   🖨️  PRINTER AGENT – CLOUD VPS DEPLOYMENT"
  echo "================================================================"
  echo ""
}

# ── Parse Arguments ──────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --no-ssl)       ENABLE_SSL=false ;;
    --domain=*)     DOMAIN="${arg#*=}" ;;
    --domain)       shift; DOMAIN="$1" ;;
  esac
done

# ── Step 1: Check Docker ──────────────────────────────────────
check_docker() {
  info "Checking Docker installation..."
  if ! command -v docker &>/dev/null; then
    warn "Docker not found. Installing Docker..."
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker "$USER" || true
    ok "Docker installed."
  else
    ok "Docker $(docker --version | cut -d' ' -f3) is installed."
  fi

  if ! command -v docker-compose &>/dev/null && ! docker compose version &>/dev/null 2>&1; then
    warn "Docker Compose not found. Installing..."
    apt-get install -y docker-compose-plugin || pip install docker-compose
  fi
  ok "Docker Compose is available."
}

# ── Step 2: Configure .env ───────────────────────────────────
configure_env() {
  info "Configuring environment..."
  if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
  fi

  # Generate a strong secret key
  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))" 2>/dev/null || openssl rand -hex 32)
  sed -i "s|please-change-this-secret-key-in-production|$SECRET|g" "$APP_DIR/.env"

  ok ".env configured with strong SECRET_KEY."
  warn "Edit $APP_DIR/.env to change ADMIN_PASSWORD, UPI_DEFAULT_VPA, etc."
}

# ── Step 3: SSL via Let's Encrypt ────────────────────────────
setup_ssl() {
  if [ "$ENABLE_SSL" = false ]; then
    warn "SSL disabled (--no-ssl). Running HTTP only on port 80."
    # Replace docker-compose to not use nginx with ssl
    return 0
  fi

  if [ -z "$DOMAIN" ]; then
    warn "No domain specified. Skipping SSL. Use --domain=yourdomain.com for HTTPS."
    ENABLE_SSL=false
    return 0
  fi

  info "Setting up Let's Encrypt SSL for domain: $DOMAIN..."

  mkdir -p "$APP_DIR/nginx/ssl"

  if ! command -v certbot &>/dev/null; then
    apt-get update && apt-get install -y certbot
  fi

  # Stop nginx if running to free port 80
  docker compose -f "$APP_DIR/docker-compose.yml" stop nginx 2>/dev/null || true

  certbot certonly --standalone \
    -d "$DOMAIN" \
    --non-interactive \
    --agree-tos \
    --email "${ADMIN_EMAIL_DEFAULT}" \
    --expand || error "certbot SSL issuance failed for $DOMAIN."

  # Symlink certs
  ln -sf "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" "$APP_DIR/nginx/ssl/fullchain.pem"
  ln -sf "/etc/letsencrypt/live/$DOMAIN/privkey.pem" "$APP_DIR/nginx/ssl/privkey.pem"

  # Update nginx config with real domain
  sed -i "s|server_name _;|server_name $DOMAIN;|g" "$APP_DIR/nginx/nginx.conf"

  ok "SSL certificates installed for $DOMAIN."

  # Auto-renew cron
  (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && docker compose -f $APP_DIR/docker-compose.yml exec -T nginx nginx -s reload") | crontab -
  ok "Auto-renewal cron added."
}

# ── Step 4: Build and Start ───────────────────────────────────
start_services() {
  info "Building Printer Agent Docker image..."
  cd "$APP_DIR"
  docker compose build --no-cache web
  ok "Image built."

  info "Starting all services..."
  if [ "$ENABLE_SSL" = true ] && [ -n "$DOMAIN" ]; then
    docker compose up -d
  else
    # Start only the web service without nginx if no SSL/domain
    docker compose up -d web
  fi

  ok "Services started!"
}

# ── Step 5: Print Summary ─────────────────────────────────────
print_summary() {
  echo ""
  echo "================================================================"
  echo "   ✅ PRINTER AGENT DEPLOYED SUCCESSFULLY"
  echo "================================================================"
  echo ""
  if [ "$ENABLE_SSL" = true ] && [ -n "$DOMAIN" ]; then
    echo "   🌐 Web Portal     : https://$DOMAIN"
    echo "   📱 Customer Upload: https://$DOMAIN/upload?shop=counter-1"
  else
    SERVER_IP=$(curl -s ifconfig.me 2>/dev/null || hostname -I | awk '{print $1}')
    echo "   🌐 Web Portal     : http://$SERVER_IP:8000"
    echo "   📱 Customer Upload: http://$SERVER_IP:8000/upload?shop=counter-1"
    echo "   📊 QR Counter Flyer: http://$SERVER_IP:8000/qr?shop=counter-1"
  fi
  echo ""
  echo "   🔑 Admin Login    : admin@printagent.com"
  echo "   🔒 Password       : (see .env → ADMIN_PASSWORD)"
  echo ""
  echo "   📋 Useful commands:"
  echo "   docker compose logs -f web     # Stream logs"
  echo "   docker compose restart web     # Restart app"
  echo "   docker compose down            # Stop all"
  echo "================================================================"
}

# ── Main ──────────────────────────────────────────────────────
banner
check_docker
configure_env
setup_ssl
start_services
print_summary
