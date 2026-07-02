#!/usr/bin/env bash
# First-time SSL certificate setup with Let's Encrypt.
# Run once on the server before starting the full stack.
# Usage: bash scripts/setup_ssl.sh your-domain.com your@email.com

set -euo pipefail

DOMAIN="${1:?Usage: $0 <domain> <email>}"
EMAIL="${2:?Usage: $0 <domain> <email>}"
CONF="nginx/app.conf"

# 1. Patch the nginx config with the real domain
sed -i "s/YOUR_DOMAIN/${DOMAIN}/g" "$CONF"
echo "✓ nginx/app.conf updated with domain: $DOMAIN"

# 2. Spin up nginx on port 80 only (no SSL yet) to serve the ACME challenge
docker compose -f docker-compose.prod.yml up -d nginx

# 3. Issue the certificate
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot \
  --webroot-path /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  -d "$DOMAIN" \
  -d "www.$DOMAIN"

echo ""
echo "✓ Certificate issued for $DOMAIN"
echo ""
echo "Next steps:"
echo "  1. Set NEXT_PUBLIC_API_URL=https://$DOMAIN/api in .env"
echo "  2. Set GOOGLE_OAUTH_REDIRECT_URI=https://$DOMAIN/api/youtube/callback in .env"
echo "  3. docker compose -f docker-compose.prod.yml up -d"
