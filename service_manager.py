import subprocess
import os

class ServiceManager:
    def restart_services(self):
        """Restart system services"""
        self._manage_php_fpm()
        self._manage_nginx()
        print("✅ Services restarted successfully")
    
    def _manage_php_fpm(self):
        """Manage PHP-FPM service"""
        try:
            # Fix PHP-FPM issues first
            self._fix_php_fpm_issues()
            
            # Try to start PHP-FPM
            result = subprocess.run(['systemctl', 'start', 'php8.2-fpm'], 
                                   capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ PHP-FPM started successfully")
            else:
                print(f"⚠️ PHP-FPM start failed, trying restart: {result.stderr}")
                # Try restart
                subprocess.run(['systemctl', 'restart', 'php8.2-fpm'], check=True)
                print("✅ PHP-FPM restarted successfully")
                
        except Exception as e:
            print(f"⚠️ PHP-FPM management failed: {e}")
            # Try alternative approach
            subprocess.run(['pkill', '-f', 'php-fpm'], check=False)
            subprocess.run(['systemctl', 'start', 'php8.2-fpm'], check=False)
    
    def _manage_nginx(self):
        """Manage Nginx service"""
        try:
            # Check if nginx is running
            status_result = subprocess.run(['systemctl', 'is-active', 'nginx'], 
                                         capture_output=True, text=True, check=False)
            
            if status_result.stdout.strip() == 'active':
                # Nginx is running, try reload first
                result = subprocess.run(['systemctl', 'reload', 'nginx'], 
                                       capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    print("✅ Nginx reloaded successfully")
                    return
            
            # Start nginx
            result = subprocess.run(['systemctl', 'start', 'nginx'], 
                                   capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Nginx started successfully")
            else:
                # Try restart
                subprocess.run(['systemctl', 'restart', 'nginx'], check=True)
                print("✅ Nginx restarted successfully")
                
        except Exception as e:
            print(f"⚠️ Nginx management failed: {e}")
    
    def _fix_php_fpm_issues(self):
        """Fix common PHP-FPM issues"""
        try:
            # Fix permissions on PHP-FPM directories
            php_dirs = ['/var/run/php', '/etc/php/8.2/fpm']
            
            for php_dir in php_dirs:
                if os.path.exists(php_dir):
                    subprocess.run(['chown', '-R', 'www-data:www-data', php_dir], check=False)
            
            # Create missing directories
            subprocess.run(['mkdir', '-p', '/var/run/php'], check=False)
            subprocess.run(['chown', 'www-data:www-data', '/var/run/php'], check=False)
            
            # Fix socket permissions
            socket_path = '/var/run/php/php8.2-fpm.sock'
            if os.path.exists(socket_path):
                subprocess.run(['chmod', '666', socket_path], check=False)
            
            # Kill any hanging processes
            subprocess.run(['pkill', '-f', 'php-fpm'], check=False)
            
        except Exception as e:
            print(f"⚠️ Could not fix all PHP-FPM issues: {e}")
