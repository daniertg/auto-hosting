#!/bin/bash

# Laravel Auto Hosting VPS Setup Script

echo "Setting up Laravel Auto Hosting environment..."

# Update system
apt update && apt upgrade -y

# Install required packages
apt install -y nginx php8.1 php8.1-fpm php8.1-mysql php8.1-xml php8.1-gd php8.1-curl php8.1-zip php8.1-mbstring
apt install -y mysql-server git composer python3 python3-pip

# Install Flask
pip3 install flask werkzeug

# Configure MySQL
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '';"
mysql -e "FLUSH PRIVILEGES;"

# Configure PHP-FPM
systemctl enable php8.1-fpm
systemctl start php8.1-fpm

# Configure Nginx
systemctl enable nginx
systemctl start nginx

# Create web directory
mkdir -p /var/www
chown -R www-data:www-data /var/www

# Set up firewall
ufw allow 22
ufw allow 80
ufw allow 443
ufw allow 5000
ufw --force enable

echo "Installation complete!"
echo "Run the auto-hosting script with: python3 app.py"
echo "Access the web interface at: http://your-server-ip:5000"
