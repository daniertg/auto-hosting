# Laravel Auto Hosting System

A web-based tool for automatically deploying Laravel projects on VPS servers.

## Features

- Web interface for easy deployment
- Automatic Git repository cloning
- Database import and setup
- Environment file configuration
- Nginx configuration
- SSL certificate installation
- Asset path fixing for cross-platform compatibility

## Installation

1. Run the installation script on your VPS:
```bash
chmod +x install.sh
sudo ./install.sh
```

2. Install Python dependencies:
```bash
pip3 install -r requirements.txt
```

3. Start the application:
```bash
python3 app.py
```

4. Access the web interface at `http://your-server-ip:5000`

## Usage

1. Open the web interface
2. Fill in the deployment form:
   - Git repository URL (required)
   - Upload database.sql file (optional)
   - Upload .env file (optional)
   - Domain name (optional)
   - Port (default: 80)
3. Click "Deploy Project"
4. Wait for deployment to complete
5. Access your deployed Laravel application

## Requirements

- Ubuntu/Debian VPS
- Root access
- Internet connection
- Domain name (optional, for SSL)

## Supported Ports

- 80 (HTTP)
- 8080
- 3000
- 8000

## SSL Configuration

SSL certificates are automatically installed using Let's Encrypt when a domain is provided.

## Troubleshooting

- Check Nginx configuration: `nginx -t`
- Restart services: `systemctl restart nginx php8.1-fpm`
- Check logs: `tail -f /var/log/nginx/error.log`
