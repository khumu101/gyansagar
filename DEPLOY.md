# Gyansagar — Deploy guide (VPS + Docker)

Stack: **Caddy (HTTPS) → nginx → gunicorn/Django → PostgreSQL + Redis**, with a daily backup container.
Any Ubuntu 22.04/24.04 VPS with 2 GB RAM is enough to start (Hetzner, DigitalOcean, Contabo ...).

## 1. Server setup (once)
```bash
curl -fsSL https://get.docker.com | sh          # installs Docker + compose plugin
sudo apt install -y caddy                        # HTTPS in front
git clone <your-repo> gyansagar && cd gyansagar  # or upload the zip and unzip it
cp .env.example .env && nano .env                # fill DOMAIN, DJANGO_SECRET_KEY, POSTGRES_PASSWORD, admin login ...
```
Point your domain's **A record** to the server IP, then put this in `/etc/caddy/Caddyfile` (replace the domain):
```
gyansagar.com, www.gyansagar.com {
    request_body { max_size 110MB }
    reverse_proxy 127.0.0.1:8080
}
```
`sudo systemctl reload caddy` — Caddy gets and renews the HTTPS certificate automatically.
(Using Cloudflare instead? Point it at the server, set SSL mode "Full", and let it talk to port 8080 via a tunnel or Caddy.)

## 2. Start
```bash
docker compose up -d --build
docker compose ps                  # web should become "healthy"
docker compose logs -f web
```
First start creates tables and the admin from `DJANGO_SUPERUSER_*`. Open `https://DOMAIN/<ADMIN_URL>` → log in → **remove `DJANGO_SUPERUSER_PASSWORD` from .env**.
Optional demo content: `docker compose exec web python manage.py seed_full`

## 3. Update to a new version
```bash
git pull   # or upload new files
docker compose up -d --build       # migrations run automatically on start
```

## 4. Backups  (do not skip!)
The `backup` container writes a PostgreSQL dump + uploads archive to `./backups` every 24 h and keeps the last `BACKUP_KEEP` (14).
**A backup on the same server is not enough** — copy `./backups` off the server, e.g. daily from your laptop/another server:
```bash
rsync -az user@server:/path/to/gyansagar/backups/ ./gyansagar-backups/
```
Manual backup: `docker compose exec web python manage.py backup --dir /backups`

**Restore** (stops the app first):
```bash
docker compose stop web backup nginx
docker compose run --rm --no-deps -v ./backups:/backups -e RUN_MIGRATIONS=0 web \
  python manage.py restore /backups/gyansagar-YYYYMMDD-HHMMSS-db.dump \
  --media /backups/gyansagar-YYYYMMDD-HHMMSS-media.tar.gz --yes
docker compose up -d
```
Test a restore on a spare machine at least once — an untested backup is a hope, not a backup.

## 5. Monitoring
* **Errors:** create a free project at sentry.io, put the DSN in `SENTRY_DSN`, restart. Every crash is emailed to you with the stack trace.
* **Uptime:** point UptimeRobot / BetterStack at `https://DOMAIN/healthz/` (process up) and `/readyz/` (database + cache OK, returns 503 otherwise).
* **Logs:** `docker compose logs --tail=200 web`

## 6. Uploads in S3 / Cloudflare R2 (when the disk gets big)
Add `django-storages[s3]` to requirements.txt, fill `AWS_*` in `.env` (for R2 also `AWS_S3_ENDPOINT_URL`), rebuild.
Files then live in the bucket; students get a 5-minute signed link after Django checks they are logged in. Enable bucket versioning as your backup.

## 7. Settings cheat-sheet
| Variable | Meaning |
|---|---|
| `DJANGO_DEBUG=0` | production mode (needs `DJANGO_SECRET_KEY`) |
| `ADMIN_URL` | secret admin path, e.g. `my-panel/` |
| `DOMAIN` | used for allowed hosts + HTTPS origin |
| `SENTRY_DSN` | error tracking |
| `EMAIL_HOST…` | real SMTP so password-reset emails are delivered |
| `SIGNUP_MAX_PER_HOUR`, `PASSWORD_RESET_MAX_PER_HOUR` | abuse limits per IP |
| `RESOURCE_MAX_UPLOAD_MB` | upload size cap (keep nginx `client_max_body_size` above it) |
| `ANTHROPIC_API_KEY` | AI Tutor |

## 8. Sign in with Google (optional)
1. <https://console.cloud.google.com> → create a project → **APIs & Services → OAuth consent screen** (External, app name *Gyansagar*, your support e-mail) → *Publish app* when ready.
2. **Credentials → Create credentials → OAuth client ID → Web application.**
   * Authorized redirect URI: `https://YOUR-DOMAIN/accounts/google/callback/` (exactly, with the trailing slash; add `http://localhost:8000/accounts/google/callback/` to test locally)
3. Copy *Client ID* and *Client secret* into `.env` (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) → `docker compose up -d`.
4. The **Continue with Google** button now appears on Login and Sign-up. Google users get a verified e-mail automatically; admin (superuser) accounts must still use their password.

## 9. Files, previews and text notes
* Any file type can be uploaded **except** programs/scripts/web pages (`.exe .js .html .svg .php ...`, list in `RESOURCE_BLOCKED_EXTENSIONS`).
* PDF, images, video, audio and `.txt` open in a preview page (with Download and Open-in-new-tab buttons). Word/PowerPoint/Excel and everything else download.
* For old questions or short notes you can simply **type the text** into the admin ("Content" box) — students read it on the page, no file needed.
* Video seeking (jumping ahead) works best with nginx serving (`RESOURCE_SERVE_METHOD=nginx`, already set in docker-compose).

## 10. Checklist before going live
- [ ] `.env` filled, `DJANGO_DEBUG=0`, long random `DJANGO_SECRET_KEY`
- [ ] HTTPS works, `http://` redirects to `https://`
- [ ] Admin password changed / removed from `.env`, `ADMIN_URL` is secret
- [ ] Backup ran once, copied off-server, restore tested
- [ ] Sentry DSN set + uptime monitor on `/readyz/`
- [ ] SMTP configured and a password reset email really arrives
- [ ] (if used) Google redirect URI matches your domain exactly
- [ ] Firewall: only ports 22, 80, 443 open (`ufw allow 22,80,443/tcp && ufw enable`)
