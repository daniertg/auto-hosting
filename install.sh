#!/bin/bash

# Laravel Auto Hosting VPS Setup Script

echo "Setting up Laravel Auto Hosting environment..."

# Update system
apt update && apt upgrade -y

# Add PHP repository for latest versions
apt install -y software-properties-common
add-apt-repository ppa:ondrej/php -y
apt update

# Install PHP 8.2 instead of 8.1 for better Laravel compatibility
apt install -y nginx php8.2 php8.2-fpm php8.2-mysql php8.2-xml php8.2-gd php8.2-curl php8.2-zip php8.2-mbstring php8.2-bcmath php8.2-intl
apt install -y mysql-server git python3 python3-pip

# Install Composer
curl -sS https://getcomposer.org/installer | php
mv composer.phar /usr/local/bin/composer
chmod +x /usr/local/bin/composer

# Install Flask
pip3 install flask werkzeug

# Configure MySQL
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '';"
mysql -e "FLUSH PRIVILEGES;"

# Configure PHP-FPM 8.2
systemctl enable php8.2-fpm
systemctl start php8.2-fpm

# Update Nginx default config to use PHP 8.2
sed -i 's/php8\.1-fpm/php8.2-fpm/g' /etc/nginx/sites-available/default

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
echo "PHP 8.2 installed for better Laravel compatibility"
echo "Run the auto-hosting script with: python3 app.py"
echo "Access the web interface at: http://your-server-ip:5000"
