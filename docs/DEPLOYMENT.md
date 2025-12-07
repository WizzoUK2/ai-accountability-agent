# Deployment Guide

This guide covers deploying the AI Accountability Agent to a self-hosted VPS environment.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Server Setup](#server-setup)
- [Application Deployment](#application-deployment)
- [Service Configuration](#service-configuration)
- [Reverse Proxy Setup](#reverse-proxy-setup)
- [SSL/TLS Configuration](#ssltls-configuration)
- [Database Setup](#database-setup)
- [Monitoring & Logging](#monitoring--logging)
- [Backup Strategy](#backup-strategy)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Server Requirements

- **OS**: Ubuntu 22.04 LTS (recommended) or Debian 12
- **RAM**: Minimum 1GB, recommended 2GB+
- **Storage**: 20GB+ SSD
- **CPU**: 1 vCPU minimum, 2 vCPU recommended

### Domain & DNS

- A domain name (e.g., `accountability.yourdomain.com`)
- DNS A record pointing to your server's IP address

### External Service Accounts

Ensure you have credentials ready for:

- Google Cloud Console (OAuth credentials)
- Twilio (Account SID, Auth Token, Phone Number)
- Slack (Bot Token, Signing Secret)
- Anthropic (API Key)

---

## Server Setup

### 1. Initial Server Configuration

```bash
# Update system packages
sudo apt update && sudo apt upgrade -y

# Install essential packages
sudo apt install -y curl git build-essential nginx certbot python3-certbot-nginx

# Install Python 3.11+
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# Create application user
sudo useradd -m -s /bin/bash accountability
sudo usermod -aG sudo accountability
```

### 2. Install UV (Recommended) or pip

```bash
# Option A: Install UV (faster, recommended)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# Option B: Use pip (traditional)
pip install --upgrade pip
```

### 3. Configure Firewall

```bash
# Allow SSH, HTTP, HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
sudo ufw status
```

---

## Application Deployment

### 1. Clone Repository

```bash
# Switch to application user
sudo su - accountability

# Clone the repository
git clone https://github.com/WizzoUK2/ai-accountability-agent.git
cd ai-accountability-agent
```

### 2. Create Virtual Environment

```bash
# Using UV (recommended)
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .

# OR using standard venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit with your credentials
nano .env
```

**Required `.env` configuration:**

```bash
# Application
APP_NAME=ai-accountability-agent
DEBUG=false
LOG_LEVEL=INFO

# Database (use absolute path for production)
DATABASE_URL=sqlite+aiosqlite:///home/accountability/ai-accountability-agent/data/accountability.db

# Google OAuth (update redirect URI for your domain)
GOOGLE_CLIENT_ID=your-client-id-here
GOOGLE_CLIENT_SECRET=your-client-secret-here
GOOGLE_REDIRECT_URI=https://accountability.yourdomain.com/auth/google/callback

# Twilio SMS
TWILIO_ACCOUNT_SID=your-account-sid
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_FROM_NUMBER=+1234567890
USER_PHONE_NUMBER=+1234567890

# Slack
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-signing-secret
SLACK_USER_ID=U1234567890

# Anthropic
ANTHROPIC_API_KEY=sk-ant-your-api-key

# Scheduling
MORNING_BRIEFING_TIME=07:00
TIMEZONE=Australia/Sydney
```

### 4. Create Data Directory

```bash
mkdir -p /home/accountability/ai-accountability-agent/data
chmod 700 /home/accountability/ai-accountability-agent/data
```

### 5. Initialize Database

```bash
# Test the application starts correctly
source .venv/bin/activate
python -c "from src.models.database import init_db; import asyncio; asyncio.run(init_db())"
```

---

## Service Configuration

### 1. Create Systemd Service

```bash
sudo nano /etc/systemd/system/accountability-agent.service
```

**Service file contents:**

```ini
[Unit]
Description=AI Accountability Agent
After=network.target

[Service]
Type=exec
User=accountability
Group=accountability
WorkingDirectory=/home/accountability/ai-accountability-agent
Environment="PATH=/home/accountability/ai-accountability-agent/.venv/bin"
EnvironmentFile=/home/accountability/ai-accountability-agent/.env
ExecStart=/home/accountability/ai-accountability-agent/.venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=/home/accountability/ai-accountability-agent/data

[Install]
WantedBy=multi-user.target
```

### 2. Enable and Start Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable accountability-agent

# Start the service
sudo systemctl start accountability-agent

# Check status
sudo systemctl status accountability-agent

# View logs
sudo journalctl -u accountability-agent -f
```

---

## Reverse Proxy Setup

### 1. Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/accountability-agent
```

**Nginx configuration:**

```nginx
server {
    listen 80;
    server_name accountability.yourdomain.com;

    # Redirect HTTP to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name accountability.yourdomain.com;

    # SSL configuration (will be managed by Certbot)
    ssl_certificate /etc/letsencrypt/live/accountability.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/accountability.yourdomain.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Logging
    access_log /var/log/nginx/accountability-agent.access.log;
    error_log /var/log/nginx/accountability-agent.error.log;

    # Proxy to application
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        proxy_read_timeout 86400;
    }

    # Health check endpoint (no auth required)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
    }
}
```

### 2. Enable Site

```bash
# Create symlink
sudo ln -s /etc/nginx/sites-available/accountability-agent /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

---

## SSL/TLS Configuration

### 1. Obtain SSL Certificate

```bash
# Get certificate from Let's Encrypt
sudo certbot --nginx -d accountability.yourdomain.com

# Follow the prompts to complete setup
```

### 2. Auto-Renewal

Certbot automatically creates a renewal cron job. Verify it:

```bash
# Test renewal process
sudo certbot renew --dry-run

# Check the timer
sudo systemctl status certbot.timer
```

---

## Database Setup

### SQLite (Default)

SQLite is suitable for single-user deployments. The database file is stored at:

```
/home/accountability/ai-accountability-agent/data/accountability.db
```

### PostgreSQL (Production Scale)

For multi-user or higher reliability requirements:

```bash
# Install PostgreSQL
sudo apt install -y postgresql postgresql-contrib

# Create database and user
sudo -u postgres psql
```

```sql
CREATE USER accountability WITH PASSWORD 'secure-password-here';
CREATE DATABASE accountability_agent OWNER accountability;
GRANT ALL PRIVILEGES ON DATABASE accountability_agent TO accountability;
\q
```

Update `.env`:

```bash
DATABASE_URL=postgresql+asyncpg://accountability:secure-password-here@localhost/accountability_agent
```

Install async PostgreSQL driver:

```bash
source .venv/bin/activate
pip install asyncpg
```

---

## Monitoring & Logging

### 1. Application Logs

```bash
# View real-time logs
sudo journalctl -u accountability-agent -f

# View last 100 lines
sudo journalctl -u accountability-agent -n 100

# View logs since today
sudo journalctl -u accountability-agent --since today
```

### 2. Log Rotation

Create logrotate configuration:

```bash
sudo nano /etc/logrotate.d/accountability-agent
```

```
/var/log/nginx/accountability-agent.*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        [ -f /var/run/nginx.pid ] && kill -USR1 `cat /var/run/nginx.pid`
    endscript
}
```

### 3. Health Check Script

Create a monitoring script:

```bash
nano /home/accountability/check_health.sh
```

```bash
#!/bin/bash

HEALTH_URL="http://127.0.0.1:8000/health"
SLACK_WEBHOOK="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"  # Optional

response=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $response -ne 200 ]; then
    echo "$(date): Health check failed with status $response"

    # Restart service
    sudo systemctl restart accountability-agent

    # Optional: Send Slack notification
    if [ -n "$SLACK_WEBHOOK" ]; then
        curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"⚠️ AI Accountability Agent was down and has been restarted"}' \
            $SLACK_WEBHOOK
    fi
fi
```

```bash
chmod +x /home/accountability/check_health.sh

# Add to crontab (run every 5 minutes)
crontab -e
# Add: */5 * * * * /home/accountability/check_health.sh >> /home/accountability/health_check.log 2>&1
```

### 4. Resource Monitoring (Optional)

Install and configure Netdata for real-time monitoring:

```bash
# Install Netdata
bash <(curl -Ss https://my-netdata.io/kickstart.sh)

# Access at http://your-server:19999
```

---

## Backup Strategy

### 1. Database Backup Script

```bash
nano /home/accountability/backup.sh
```

```bash
#!/bin/bash

BACKUP_DIR="/home/accountability/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_PATH="/home/accountability/ai-accountability-agent/data/accountability.db"

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup SQLite database
sqlite3 $DB_PATH ".backup '$BACKUP_DIR/accountability_$DATE.db'"

# Backup environment file (contains secrets - handle carefully)
cp /home/accountability/ai-accountability-agent/.env $BACKUP_DIR/env_$DATE.bak

# Compress old backups
find $BACKUP_DIR -name "*.db" -mtime +1 -exec gzip {} \;

# Remove backups older than 30 days
find $BACKUP_DIR -name "*.gz" -mtime +30 -delete
find $BACKUP_DIR -name "*.bak" -mtime +30 -delete

echo "$(date): Backup completed"
```

```bash
chmod +x /home/accountability/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /home/accountability/backup.sh >> /home/accountability/backup.log 2>&1
```

### 2. Off-site Backup (Recommended)

Use `rclone` to sync backups to cloud storage:

```bash
# Install rclone
sudo apt install rclone

# Configure (interactive)
rclone config

# Add to backup script:
# rclone sync $BACKUP_DIR remote:accountability-backups
```

---

## Updating the Application

### Standard Update Process

```bash
# Switch to application user
sudo su - accountability
cd ai-accountability-agent

# Pull latest changes
git pull origin main

# Activate virtual environment
source .venv/bin/activate

# Update dependencies
pip install -e .

# Exit back to admin user
exit

# Restart service
sudo systemctl restart accountability-agent

# Verify it's running
sudo systemctl status accountability-agent
```

### Zero-Downtime Update (Advanced)

For critical deployments, use a blue-green strategy:

1. Deploy to a new directory
2. Test the new deployment
3. Update Nginx to point to new deployment
4. Keep old deployment for quick rollback

---

## Troubleshooting

### Service Won't Start

```bash
# Check service status
sudo systemctl status accountability-agent

# Check detailed logs
sudo journalctl -u accountability-agent -n 50 --no-pager

# Common issues:
# - Missing .env file
# - Invalid credentials
# - Port already in use
# - Python path issues
```

### Database Errors

```bash
# Check database file permissions
ls -la /home/accountability/ai-accountability-agent/data/

# Verify database integrity
sqlite3 /home/accountability/ai-accountability-agent/data/accountability.db "PRAGMA integrity_check;"
```

### OAuth Callback Errors

1. Verify `GOOGLE_REDIRECT_URI` matches exactly what's configured in Google Cloud Console
2. Ensure HTTPS is working correctly
3. Check that the domain is accessible from the internet

### SSL Certificate Issues

```bash
# Test certificate
sudo certbot certificates

# Force renewal
sudo certbot renew --force-renewal

# Check Nginx SSL configuration
sudo nginx -t
```

### Performance Issues

```bash
# Check system resources
htop

# Check application memory usage
ps aux | grep uvicorn

# Check database size
du -h /home/accountability/ai-accountability-agent/data/accountability.db
```

---

## Security Checklist

- [ ] SSH key authentication enabled, password auth disabled
- [ ] Firewall configured (UFW)
- [ ] Fail2ban installed for brute-force protection
- [ ] SSL/TLS configured with A+ rating
- [ ] `.env` file has restricted permissions (600)
- [ ] Database file has restricted permissions (600)
- [ ] Regular security updates enabled (`unattended-upgrades`)
- [ ] Backup strategy implemented and tested
- [ ] Monitoring and alerting configured

### Enable Automatic Security Updates

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

---

## Quick Reference Commands

```bash
# Service management
sudo systemctl start accountability-agent
sudo systemctl stop accountability-agent
sudo systemctl restart accountability-agent
sudo systemctl status accountability-agent

# View logs
sudo journalctl -u accountability-agent -f

# Nginx
sudo nginx -t
sudo systemctl reload nginx

# SSL renewal
sudo certbot renew

# Manual backup
/home/accountability/backup.sh
```
