#!/bin/bash

echo "Setting up Laravel Auto Hosting..."

# Update system
apt update && apt upgrade -y

# Add PHP repository
apt install -y software-properties-common
add-apt-repository ppa:ondrej/php -y
apt update

# Install packages
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

# Start services
systemctl enable nginx php8.2-fpm
systemctl start nginx php8.2-fpm

# Create web directory
mkdir -p /var/www
chown -R www-data:www-data /var/www

# Configure firewall
ufw allow 22
ufw allow 80
ufw allow 443
ufw allow 5000
ufw --force enable

echo "Installation complete!"
echo "Run: python3 app.py"
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
