import subprocess
import os

class ServiceManager:
    def __init__(self):
        self.php_service = self._detect_available_php()
        self.php_socket = self._get_php_socket()
    
    def _detect_available_php(self):
        """Detect available PHP-FPM service"""
        php_versions = ['php8.2-fpm', 'php8.1-fpm', 'php8.0-fpm', 'php7.4-fpm']
        
        for php_service in php_versions:
            try:
                # Check if service exists
                result = subprocess.run(['systemctl', 'list-units', '--type=service', '--all'], 
                                      capture_output=True, text=True, check=False)
                if php_service in result.stdout:
                    print(f"✅ Found PHP service: {php_service}")
                    return php_service
                
                # Check if package is available for install
                result = subprocess.run(['apt', 'list', php_service], 
                                      capture_output=True, text=True, check=False)
                if php_service in result.stdout and 'installed' not in result.stdout:
                    print(f"✅ PHP package available: {php_service}")
                    return php_service
                    
            except:
                continue
        
        # Default fallback
        return 'php8.1-fpm'
    
    def _get_php_socket(self):
        """Get corresponding PHP socket path"""
        socket_map = {
            'php8.2-fpm': '/var/run/php/php8.2-fpm.sock',
            'php8.1-fpm': '/var/run/php/php8.1-fpm.sock',
            'php8.0-fpm': '/var/run/php/php8.0-fpm.sock', 
            'php7.4-fpm': '/var/run/php/php7.4-fpm.sock'
        }
        return socket_map.get(self.php_service, '/var/run/php/php8.1-fpm.sock')
    
    def restart_services(self):
        """Restart system services"""
        self._stop_apache()
        self._stop_conflicting_php()
        self._ensure_php_installed()
        self._manage_php_fpm()
        self._manage_nginx()
        print("✅ Services restarted successfully")
    
    def _stop_conflicting_php(self):
        """Stop other PHP versions"""
        conflicting_services = ['php8.2-fpm', 'php8.1-fpm', 'php7.4-fpm', 'php8.0-fpm']
        # Remove current service from conflicts
        if self.php_service in conflicting_services:
            conflicting_services.remove(self.php_service)
        
        for service in conflicting_services:
            try:
                subprocess.run(['systemctl', 'stop', service], check=False)
                subprocess.run(['systemctl', 'disable', service], check=False)
                print(f"✅ Stopped conflicting service: {service}")
            except:
                pass
    
    def _ensure_php_installed(self):
        """Ensure PHP FPM is installed"""
        try:
            # Check if service already exists
            result = subprocess.run(['systemctl', 'status', self.php_service], 
                                  capture_output=True, check=False)
            
            if result.returncode == 0:
                print(f"✅ {self.php_service} already exists")
                return True
            
            # Try to install the PHP version
            print(f"📦 Installing {self.php_service}...")
            
            # Update package list first
            subprocess.run(['apt', 'update'], check=False)
            
            # Install PHP-FPM
            install_result = subprocess.run(['apt', 'install', '-y', self.php_service], 
                                          capture_output=True, text=True, check=False)
            
            if install_result.returncode == 0:
                subprocess.run(['systemctl', 'enable', self.php_service], check=True)
                print(f"✅ {self.php_service} installed and enabled")
                return True
            else:
                print(f"⚠️ Could not install {self.php_service}: {install_result.stderr}")
                # Try to find any working PHP version
                return self._find_working_php()
                
        except Exception as e:
            print(f"⚠️ Could not ensure PHP installation: {e}")
            return self._find_working_php()
    
    def _find_working_php(self):
        """Find any working PHP-FPM service"""
        php_versions = ['php8.1-fpm', 'php8.0-fpm', 'php7.4-fpm']
        
        for php_service in php_versions:
            try:
                result = subprocess.run(['systemctl', 'status', php_service], 
                                      capture_output=True, check=False)
                if result.returncode == 0 or 'loaded' in result.stdout.decode():
                    self.php_service = php_service
                    self.php_socket = self._get_php_socket()
                    print(f"✅ Using existing PHP service: {php_service}")
                    return True
            except:
                continue
        
        print("❌ No working PHP-FPM service found")
        return False
    
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
                    # Don't raise exception, continue with deployment
                    print("⚠️ Continuing deployment without PHP-FPM restart")
                    return
            
            # Wait for socket creation and fix permissions
            import time
            time.sleep(3)
            self._fix_socket_permissions()
                
        except Exception as e:
            print(f"⚠️ PHP-FPM management failed: {e}")
    
    def _fix_socket_permissions(self):
        """Fix socket permissions specifically"""
        if os.path.exists(self.php_socket):
            subprocess.run(['chmod', '666', self.php_socket], check=False)
            subprocess.run(['chown', 'www-data:www-data', self.php_socket], check=False)
            print(f"✅ Fixed permissions for {self.php_socket}")
            
            # Test socket is writable
            try:
                result = subprocess.run(['sudo', '-u', 'www-data', 'test', '-w', self.php_socket], 
                                      check=False)
                if result.returncode == 0:
                    print(f"✅ Socket {self.php_socket} is writable by www-data")
                else:
                    print(f"⚠️ Socket {self.php_socket} not writable by www-data")
            except:
                pass
        else:
            print(f"⚠️ Socket {self.php_socket} not found")
    
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
    
    def get_php_socket(self):
        """Get current PHP socket path for nginx config"""
        return self.php_socket
    
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
            # Test nginx config first before any reload/restart
            self._test_and_fix_nginx_config()
            
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
                else:
                    print(f"⚠️ Nginx reload failed: {result.stderr}")
            
            # Start nginx
            result = subprocess.run(['systemctl', 'start', 'nginx'], 
                                   capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Nginx started successfully")
            else:
                print(f"⚠️ Nginx start failed: {result.stderr}")
                # Try restart
                result = subprocess.run(['systemctl', 'restart', 'nginx'], 
                                       capture_output=True, text=True, check=False)
                if result.returncode == 0:
                    print("✅ Nginx restarted successfully")
                else:
                    print(f"❌ Nginx restart failed: {result.stderr}")
                    # Force clean restart
                    self._force_nginx_restart()
                
        except Exception as e:
            print(f"⚠️ Nginx management failed: {e}")
            self._force_nginx_restart()
    
    def _test_and_fix_nginx_config(self):
        """Test nginx config and fix if needed"""
        try:
            result = subprocess.run(['nginx', '-t'], capture_output=True, text=True, check=False)
            
            if result.returncode != 0:
                print(f"⚠️ Nginx config has issues: {result.stderr}")
                
                # Check for common issues and fix
                if "conflicting server name" in result.stderr:
                    self._fix_conflicting_server_names()
                
                if "failed" in result.stderr.lower():
                    self._emergency_nginx_fix()
                    
        except Exception as e:
            print(f"⚠️ Could not test nginx config: {e}")
    
    def _fix_conflicting_server_names(self):
        """Fix conflicting server names"""
        try:
            print("🔧 Fixing conflicting server names...")
            
            # List all enabled sites
            enabled_dir = '/etc/nginx/sites-enabled'
            if os.path.exists(enabled_dir):
                sites = os.listdir(enabled_dir)
                print(f"Found enabled sites: {sites}")
                
                # Keep only the latest port-based config
                port_configs = [s for s in sites if s.startswith('port_')]
                old_configs = [s for s in sites if not s.startswith('port_') and s != 'default']
                
                # Remove old configs
                for config in old_configs:
                    config_path = os.path.join(enabled_dir, config)
                    if os.path.exists(config_path):
                        os.remove(config_path)
                        print(f"✓ Removed conflicting config: {config}")
            
        except Exception as e:
            print(f"⚠️ Could not fix conflicting server names: {e}")
    
    def _emergency_nginx_fix(self):
        """Emergency nginx fix - disable all sites and enable only working ones"""
        try:
            print("🚨 Emergency nginx fix...")
            
            # Disable all sites
            enabled_dir = '/etc/nginx/sites-enabled'
            if os.path.exists(enabled_dir):
                for site in os.listdir(enabled_dir):
                    site_path = os.path.join(enabled_dir, site)
                    if os.path.exists(site_path):
                        os.remove(site_path)
                        print(f"✓ Disabled site: {site}")
            
            # Test if nginx config is now valid
            result = subprocess.run(['nginx', '-t'], capture_output=True, text=True, check=False)
            if result.returncode == 0:
                print("✅ Emergency fix successful - nginx config now valid")
            else:
                print("❌ Emergency fix failed - nginx still has issues")
                
        except Exception as e:
            print(f"❌ Emergency fix failed: {e}")
    
    def _force_nginx_restart(self):
        """Force nginx restart with clean config"""
        try:
            print("🔧 Force restarting nginx...")
            
            # Stop nginx
            subprocess.run(['systemctl', 'stop', 'nginx'], check=False)
            
            # Kill any remaining nginx processes
            subprocess.run(['pkill', '-f', 'nginx'], check=False)
            
            # Emergency config cleanup
            self._emergency_nginx_fix()
            
            # Start nginx
            result = subprocess.run(['systemctl', 'start', 'nginx'], 
                                   capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Force restart successful")
            else:
                print(f"❌ Force restart failed: {result.stderr}")
                
        except Exception as e:
            print(f"❌ Force restart failed: {e}")
