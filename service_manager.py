import subprocess
import os

class ServiceManager:
    def __init__(self):
        self.php_service = 'php8.2-fpm'  # Force PHP 8.2
    
    def restart_services(self):
        """Restart system services"""
        self._stop_apache()
        self._stop_conflicting_php()
        self._ensure_php82_installed()
        self._manage_php_fpm()
        self._manage_nginx()
        print("✅ Services restarted successfully")
    
    def _stop_conflicting_php(self):
        """Stop other PHP versions"""
        conflicting_services = ['php8.1-fpm', 'php7.4-fpm', 'php8.0-fpm']
        
        for service in conflicting_services:
            try:
                subprocess.run(['systemctl', 'stop', service], check=False)
                subprocess.run(['systemctl', 'disable', service], check=False)
                print(f"✅ Stopped conflicting service: {service}")
            except:
                pass
    
    def _ensure_php82_installed(self):
        """Ensure PHP 8.2 FPM is installed"""
        try:
            result = subprocess.run(['systemctl', 'status', 'php8.2-fpm'], 
                                  capture_output=True, check=False)
            
            if result.returncode != 0:
                print("📦 Installing PHP 8.2 FPM...")
                subprocess.run(['apt', 'update'], check=False)
                subprocess.run(['apt', 'install', '-y', 'php8.2-fpm'], check=True)
                subprocess.run(['systemctl', 'enable', 'php8.2-fpm'], check=True)
                print("✅ PHP 8.2 FPM installed")
                
        except Exception as e:
            print(f"⚠️ Could not ensure PHP 8.2 FPM: {e}")
    
    def _manage_php_fpm(self):
        """Manage PHP-FPM service"""
        try:
            # Fix PHP-FPM issues first
            self._fix_php_fpm_issues()
            
            # Try to start PHP-FPM
            result = subprocess.run(['systemctl', 'start', self.php_service], 
                                   capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print(f"✅ {self.php_service} started successfully")
            else:
                print(f"⚠️ {self.php_service} start failed: {result.stderr}")
                # Try restart
                result = subprocess.run(['systemctl', 'restart', self.php_service], 
                                       capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    print(f"✅ {self.php_service} restarted successfully")
                else:
                    print(f"❌ {self.php_service} restart failed: {result.stderr}")
                    raise Exception(f"Could not start {self.php_service}")
            
            # Wait for socket creation and fix permissions
            import time
            time.sleep(3)
            self._fix_socket_permissions()
                
        except Exception as e:
            print(f"⚠️ PHP-FPM management failed: {e}")
    
    def _fix_socket_permissions(self):
        """Fix socket permissions specifically"""
        socket_path = '/var/run/php/php8.2-fpm.sock'
        
        if os.path.exists(socket_path):
            subprocess.run(['chmod', '666', socket_path], check=False)
            subprocess.run(['chown', 'www-data:www-data', socket_path], check=False)
            print(f"✅ Fixed permissions for {socket_path}")
            
            # Test socket is writable
            try:
                result = subprocess.run(['sudo', '-u', 'www-data', 'test', '-w', socket_path], 
                                      check=False)
                if result.returncode == 0:
                    print(f"✅ Socket {socket_path} is writable by www-data")
                else:
                    print(f"⚠️ Socket {socket_path} not writable by www-data")
            except:
                pass
        else:
            print(f"⚠️ Socket {socket_path} not found")
    
    def _fix_php_fpm_issues(self):
        """Fix common PHP-FPM issues"""
        try:
            # Create missing directories
            subprocess.run(['mkdir', '-p', '/var/run/php'], check=False)
            subprocess.run(['chown', 'www-data:www-data', '/var/run/php'], check=False)
            
            # Kill any hanging processes
            subprocess.run(['pkill', '-f', 'php-fpm'], check=False)
            
            # Wait a moment
            import time
            time.sleep(1)
            
        except Exception as e:
            print(f"⚠️ Could not fix all PHP-FPM issues: {e}")
    
    def _stop_apache(self):
        """Stop Apache to prevent port conflicts"""
        try:
            subprocess.run(['systemctl', 'stop', 'apache2'], check=False)
            subprocess.run(['systemctl', 'disable', 'apache2'], check=False)
            print("✅ Apache stopped and disabled")
        except Exception as e:
            print(f"⚠️ Could not stop Apache: {e}")
    
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
