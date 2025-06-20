import subprocess
import os

class NginxManager:
    def configure_nginx(self, project_path, project_name, domain, port):
        """Configure Nginx for project"""
        # Get PHP socket from service manager
        from service_manager import ServiceManager
        service_manager = ServiceManager()
        php_socket = service_manager.get_php_socket()
        
        # Clean ALL existing configs first
        self._cleanup_all_configs()
        
        # Remove existing config for this port (if any)
        self.cleanup_config(project_name)
        
        # Create nginx config
        nginx_config = self._generate_nginx_config(project_path, project_name, domain, port, php_socket)
        
        # Write config file
        config_path = f'/etc/nginx/sites-available/{project_name}'
        with open(config_path, 'w') as f:
            f.write(nginx_config)
        
        # Enable the config
        subprocess.run(['ln', '-sf', config_path, f'/etc/nginx/sites-enabled/{project_name}'], check=True)
        
        # Test nginx configuration
        self._test_nginx_config(project_name, config_path)
        
        print(f"✅ Nginx configured successfully for port {port}")

    def _cleanup_all_configs(self):
        """Clean up ALL existing nginx configs to prevent conflicts"""
        try:
            print("🧹 Cleaning up all existing nginx configs...")
            
            # Get all enabled sites
            enabled_sites_dir = '/etc/nginx/sites-enabled'
            if os.path.exists(enabled_sites_dir):
                enabled_sites = os.listdir(enabled_sites_dir)
                
                # Remove all enabled sites except default nginx config
                for site in enabled_sites:
                    site_path = os.path.join(enabled_sites_dir, site)
                    if site != 'default' and os.path.islink(site_path):
                        os.remove(site_path)
                        print(f"✓ Removed enabled site: {site}")
            
            # Clean up old project configs from sites-available
            available_sites_dir = '/etc/nginx/sites-available'
            if os.path.exists(available_sites_dir):
                available_sites = os.listdir(available_sites_dir)
                
                # Remove old project configs (anything that looks like project ID)
                for site in available_sites:
                    site_path = os.path.join(available_sites_dir, site)
                    # Skip default nginx configs
                    if site in ['default', '000-default']:
                        continue
                    
                    # Remove if it's a project config (8 chars or port_xx format)
                    if (len(site) == 8 and site.isalnum()) or site.startswith('port_'):
                        if os.path.exists(site_path):
                            os.remove(site_path)
                            print(f"✓ Removed available site: {site}")
            
            print("✅ All old configs cleaned up")
            
        except Exception as e:
            print(f"⚠️ Error cleaning configs: {e}")

    def _generate_nginx_config(self, project_path, project_name, domain, port, php_socket):
        """Generate nginx configuration"""
        server_name = domain if domain else f'localhost'
        
        return f"""server {{
    listen {port};
    server_name {server_name};
    root {project_path}/public;
    index index.php index.html index.htm;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        fastcgi_pass unix:{php_socket};
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
    }}

    location ~ /\\.ht {{
        deny all;
    }}

    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }}
}}"""

    def _test_nginx_config(self, project_name, config_path):
        """Test nginx configuration"""
        try:
            result = subprocess.run(['nginx', '-t'], capture_output=True, text=True, check=True)
            print("✅ Nginx config test passed")
            
            # Also check for conflicting server names
            if "conflicting server name" in result.stderr:
                print("⚠️ Detected conflicting server names, but config is valid")
            
        except subprocess.CalledProcessError as e:
            print(f"❌ Nginx config test failed: {e.stderr}")
            # Remove invalid config
            self.cleanup_config(project_name)
            raise Exception(f"Nginx configuration test failed: {e.stderr}")
    
    def _fix_nginx_conflicts(self):
        """Fix nginx conflicting configurations"""
        conflicting_sites = [
            '/etc/nginx/sites-enabled/default',
            '/etc/nginx/sites-enabled/000-default'
        ]
        
        for site in conflicting_sites:
            if os.path.exists(site):
                os.remove(site)
                print(f"✅ Removed conflicting site: {site}")
    
    def cleanup_config(self, project_name):
        """Clean up nginx configuration"""
        nginx_config = f'/etc/nginx/sites-available/{project_name}'
        nginx_enabled = f'/etc/nginx/sites-enabled/{project_name}'
        
        if os.path.exists(nginx_enabled):
            os.remove(nginx_enabled)
            print(f"✓ Removed nginx enabled config: {nginx_enabled}")
        if os.path.exists(nginx_config):
            os.remove(nginx_config)
            print(f"✓ Removed nginx available config: {nginx_config}")
    
    def setup_ssl(self, domain):
        """Setup SSL certificate"""
        try:
            # First check if domain points to this server
            server_ip = self._get_server_ip()
            domain_ip = self._resolve_domain(domain)
            
            if domain_ip != server_ip:
                return f"SSL failed: Domain {domain} points to {domain_ip}, but server IP is {server_ip}. Please update DNS first."
            
            # Install certbot if not exists
            subprocess.run(['apt', 'install', '-y', 'certbot', 'python3-certbot-nginx'], check=False)
            
            # Try to get SSL certificate
            result = subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                           '--email', 'admin@example.com'], capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                return "SSL certificate installed successfully"
            else:
                return f"SSL installation failed: {result.stderr}"
        except Exception as e:
            return f"SSL installation failed: {str(e)}"
    
    def _get_server_ip(self):
        """Get server public IP"""
        try:
            import requests
            response = requests.get('https://ifconfig.me', timeout=5)
            return response.text.strip()
        except:
            return 'unknown'
    
    def _resolve_domain(self, domain):
        """Resolve domain to IP"""
        try:
            import socket
            return socket.gethostbyname(domain)
        except:
            return 'unresolved'
