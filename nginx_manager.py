import subprocess
import os

class NginxManager:
    def __init__(self):
        self.php_socket = '/var/run/php/php8.2-fpm.sock'  # Force PHP 8.2 socket
    
    def configure_nginx(self, project_path, project_id, domain, port):
        """Configure Nginx for project"""
        # Remove conflicting configs first
        self._fix_nginx_conflicts()
        
        # Create nginx config
        nginx_config = self._generate_nginx_config(project_path, project_id, domain, port)
        
        # Write config file
        config_path = f'/etc/nginx/sites-available/{project_id}'
        with open(config_path, 'w') as f:
            f.write(nginx_config)
        
        # Enable the config
        subprocess.run(['ln', '-sf', config_path, f'/etc/nginx/sites-enabled/{project_id}'], check=True)
        
        # Test nginx configuration
        self._test_nginx_config(project_id, config_path)
        
        print("✅ Nginx configured successfully")
    
    def _generate_nginx_config(self, project_path, project_id, domain, port):
        """Generate nginx configuration"""
        return f"""server {{
    listen {port};
    server_name {domain if domain else f'site-{project_id}'};
    root {project_path}/public;
    index index.php index.html index.htm;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        fastcgi_pass unix:{self.php_socket};
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

    def _test_nginx_config(self, project_id, config_path):
        """Test nginx configuration"""
        try:
            subprocess.run(['nginx', '-t'], capture_output=True, text=True, check=True)
            print("✅ Nginx config test passed")
        except subprocess.CalledProcessError as e:
            print(f"❌ Nginx config test failed: {e.stderr}")
            # Remove invalid config
            self.cleanup_config(project_id)
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
    
    def cleanup_config(self, project_id):
        """Clean up nginx configuration"""
        nginx_config = f'/etc/nginx/sites-available/{project_id}'
        nginx_enabled = f'/etc/nginx/sites-enabled/{project_id}'
        
        if os.path.exists(nginx_enabled):
            os.remove(nginx_enabled)
        if os.path.exists(nginx_config):
            os.remove(nginx_config)
    
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
