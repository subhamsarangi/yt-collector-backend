# YT Collector — Backend

FastAPI service running on an OCI Always Free Micro instance. Handles yt-dlp scraping, audio extraction, R2 uploads, and PDF generation.

---

## Prerequisites

- OCI Always Free account with a Micro instance provisioned (Ubuntu 22.04, 1 OCPU, 1GB RAM)
- SSH access to the instance
- Cloudflare R2 bucket created (Phase 2 complete)
- Supabase project running (Phase 1 complete)

---

## Server Setup (OCI Instance)

SSH into the instance and run the following:

```bash
# System dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.11 python3.11-venv python3-pip ffmpeg git

# yt-dlp (keep updated regularly)
sudo curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp
sudo chmod a+rx /usr/local/bin/yt-dlp

# WeasyPrint dependencies (for PDF generation)
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2
```

---

## Application Setup

```bash
git clone <your-repo-url> yt-collector
cd yt-collector/backend

python3.11 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

Copy and fill in the env file:

```bash
cp .env.example .env
```

---

## Environment Variables

| Variable | Description |
| --- | --- |
| `OCI_API_KEY` | Shared bearer token — must match the value set in Vercel |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 API access key |
| `R2_SECRET_ACCESS_KEY` | R2 API secret key |
| `R2_BUCKET_NAME` | R2 bucket name, e.g. `yt-collector` |
| `R2_PUBLIC_URL` | Public base URL for R2 assets, e.g. `https://<account>.r2.dev` |
| `SUPABASE_URL` | Supabase project URL (used for PDF data fetching) |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key |

---

## Running the Service

### Development

```bash
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Production (systemd)

Create `/etc/systemd/system/yt-collector.service`:

```ini
[Unit]
Description=YT Collector FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/yt-collector/backend
ExecStart=/home/ubuntu/yt-collector/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
EnvironmentFile=/home/ubuntu/yt-collector/backend/.env

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable yt-collector
sudo systemctl start yt-collector
sudo systemctl status yt-collector
```

---

## OCI Network Setup

Open port 8000 in the OCI security list:

1. OCI Console → Networking → Virtual Cloud Networks → your VCN → Security Lists
2. Add Ingress Rule: Protocol TCP, Destination Port 8000
3. Restrict source CIDR to Vercel's IP range, or leave open and rely solely on the bearer token.

Also open the port in the instance firewall:

```bash
sudo iptables -I INPUT -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

---

## API Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/video` | Download metadata, thumbnail, audio via yt-dlp; upload to R2 |
| `POST` | `/channel/scan` | Scan a channel for videos published in the last 24h |
| `POST` | `/search` | Search YouTube for top 5 videos on a topic |
| `GET` | `/job/{id}` | Poll async job status |
| `GET` | `/job/{id}/metadata` | Get full metadata JSON for a completed job |
| `POST` | `/pdf/video/{id}` | Generate and stream a per-video PDF |
| `POST` | `/pdf/topic/{id}` | Generate and stream a per-topic PDF |
| `GET` | `/health` | Health check — returns `{ "status": "ok" }` |

All endpoints require the header:
```
Authorization: Bearer <OCI_API_KEY>
```

---

## Project Structure

```
backend/
├── main.py               # FastAPI app entry point, route registration
├── routers/
│   ├── video.py          # /video, /channel/scan, /search
│   ├── jobs.py           # /job/{id}, /job/{id}/metadata
│   └── pdf.py            # /pdf/video/{id}, /pdf/topic/{id}
├── services/
│   ├── ytdlp.py          # yt-dlp wrapper functions
│   ├── r2.py             # R2 upload/delete via boto3
│   └── pdf.py            # WeasyPrint PDF generation
├── auth.py               # Bearer token dependency
├── requirements.txt
├── .env.example
└── README.md
```

---

## Keeping yt-dlp Updated

YouTube frequently changes its internals. Update yt-dlp regularly:

```bash
sudo yt-dlp -U
```

Consider adding this as a weekly cron on the OCI instance:

```bash
0 3 * * 1 /usr/local/bin/yt-dlp -U >> /var/log/yt-dlp-update.log 2>&1
```
