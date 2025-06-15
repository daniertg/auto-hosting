#!/bin/bash

echo "Setting up Laravel Auto Hosting..."

# Update system
apt update && apt upgrade -y

# Stop and disable Apache if exists (prevent port 80 conflict)
systemctl stop apache2 2>/dev/null || true
systemctl disable apache2 2>/dev/null || true
echo "✓ Apache stopped and disabled"

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

# Configure MySQL properly
systemctl start mysql
systemctl enable mysql

# Fix MySQL authentication - multiple approaches for compatibility
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '';" 2>/dev/null || true
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '';" 2>/dev/null || true
mysql -u root -e "SET PASSWORD FOR 'root'@'localhost' = PASSWORD('');" 2>/dev/null || true
mysql -e "UPDATE mysql.user SET authentication_string = '' WHERE User = 'root' AND Host = 'localhost';" 2>/dev/null || true
mysql -e "UPDATE mysql.user SET plugin = 'mysql_native_password' WHERE User = 'root' AND Host = 'localhost';" 2>/dev/null || true
mysql -e "FLUSH PRIVILEGES;"

# Test MySQL connection
echo "Testing MySQL connection..."
if mysql -u root -e "SELECT 1;" >/dev/null 2>&1; then
    echo "✓ MySQL root authentication working"
else
    echo "✗ MySQL authentication still failing, trying alternative setup..."
    # Alternative setup for problematic systems
    mysql -e "CREATE USER IF NOT EXISTS 'laravel'@'localhost' IDENTIFIED BY 'laravel123';"
    mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'laravel'@'localhost' WITH GRANT OPTION;"
    mysql -e "FLUSH PRIVILEGES;"
    echo "✓ Created alternative laravel user"
fi

# Start services
systemctl enable nginx php8.2-fpm
systemctl start nginx php8.2-fpm

# Ensure Nginx is running on port 80
systemctl restart nginx
echo "✓ Nginx restarted and should be on port 80"

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
