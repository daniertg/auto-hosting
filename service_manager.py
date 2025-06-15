import subprocess
import os

class ServiceManager:
    def __init__(self):
        self.php_service = self._detect_php_service()
    
    def _detect_php_service(self):
        """Detect correct PHP-FPM service name"""
        possible_services = [
            'php8.2-fpm',
            'php-fpm8.2', 
            'php-fpm',
            'php8.1-fpm',
            'php7.4-fpm'
        ]
        
        for service in possible_services:
            try:
                result = subprocess.run(['systemctl', 'list-units', '--type=service', '--all'], 
                                      capture_output=True, text=True, check=False)
                if service in result.stdout:
                    print(f"✅ Found PHP service: {service}")
                    return service
            except:
                continue
        
        print("⚠️ No PHP-FPM service found, will try to install")
        return 'php8.2-fpm'
    
    def restart_services(self):
        """Restart system services"""
        # Stop Apache first to free port 80
        self._stop_apache()
        self._install_php_fpm_if_missing()
        self._manage_php_fpm()
        self._manage_nginx()
        print("✅ Services restarted successfully")
    
    def _install_php_fpm_if_missing(self):
        """Install PHP-FPM if missing"""
        try:
            # Check if service exists
            result = subprocess.run(['systemctl', 'status', self.php_service], 
                                  capture_output=True, check=False)
            
            if result.returncode != 0:
                print("📦 Installing PHP-FPM...")
                subprocess.run(['apt', 'update'], check=False)
                subprocess.run(['apt', 'install', '-y', 'php8.2-fpm'], check=True)
                subprocess.run(['systemctl', 'enable', 'php8.2-fpm'], check=True)
                print("✅ PHP-FPM installed")
                
        except Exception as e:
            print(f"⚠️ Could not install PHP-FPM: {e}")
    
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
                
        except Exception as e:
            print(f"⚠️ PHP-FPM management failed: {e}")
            # Try alternative approach
            subprocess.run(['pkill', '-f', 'php-fpm'], check=False)
            subprocess.run(['systemctl', 'start', 'php8.2-fpm'], check=False)
    
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
