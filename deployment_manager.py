import subprocess
import shutil
import uuid
import os
import requests
from database_manager import DatabaseManager
from laravel_manager import LaravelManager
from nginx_manager import NginxManager
from service_manager import ServiceManager

def get_server_ip():
    """Get server public IP address"""
    try:
        response = requests.get('https://ifconfig.me', timeout=5)
        if response.status_code == 200:
            return response.text.strip()
    except:
        pass
    
    try:
        response = requests.get('https://api.ipify.org', timeout=5)
        if response.status_code == 200:
            return response.text.strip()
    except:
        pass
    
    return 'localhost'

def deploy_laravel_project(git_repo, db_file, env_file, domain, port):
    """Main deployment function"""
    project_id = str(uuid.uuid4())[:8]
    project_path = f"/var/www/{project_id}"
    
    try:
        print(f"🚀 Starting deployment for project: {project_id}")
        
        # Stop Apache to free port 80
        subprocess.run(['systemctl', 'stop', 'apache2'], check=False)
        print("✓ Apache stopped")
        
        # 1. Clone repository
        print("📥 Cloning repository...")
        subprocess.run(['git', 'clone', git_repo, project_path], check=True)
        
        # 2. Setup database
        print("🗄️ Setting up database...")
        db_manager = DatabaseManager()
        db_manager.setup_database(project_id, db_file)
        
        # 3. Setup Laravel
        print("⚙️ Setting up Laravel...")
        laravel_manager = LaravelManager()
        laravel_manager.setup_laravel(project_path, project_id, db_file, env_file)
        
        # 4. Configure Nginx
        print("🌐 Configuring Nginx...")
        nginx_manager = NginxManager()
        nginx_manager.configure_nginx(project_path, project_id, domain, port)
        
        # 5. Setup SSL if domain provided
        ssl_result = ""
        if domain:
            print("🔒 Setting up SSL...")
            ssl_result = nginx_manager.setup_ssl(domain)
        
        # 6. Restart services
        print("🔄 Restarting services...")
        service_manager = ServiceManager()
        service_manager.restart_services()
        
        # Get actual server IP
        server_ip = get_server_ip()
        
        # Generate URLs and DNS info
        if domain:
            access_url = f"http://{domain}" + (f":{port}" if port != '80' else "")
            dns_info = {
                'domain': domain,
                'server_ip': server_ip,
                'dns_records': [
                    {'type': 'A', 'name': '@', 'value': server_ip, 'ttl': '300'},
                    {'type': 'A', 'name': 'www', 'value': server_ip, 'ttl': '300'}
                ],
                'nameservers': get_recommended_nameservers(),
                'instructions': f"Set your domain '{domain}' to point to IP: {server_ip}"
            }
        else:
            access_url = f"http://{server_ip}" + (f":{port}" if port != '80' else "")
            dns_info = None
        
        print(f"✅ Deployment successful! Access URL: {access_url}")
        
        return {
            'success': True,
            'message': 'Project deployed successfully!',
            'project_id': project_id,
            'access_url': access_url,
            'ssl_status': ssl_result,
            'dns_info': dns_info
        }
        
    except Exception as e:
        print(f"❌ Deployment failed: {str(e)}")
        cleanup_failed_deployment(project_path, project_id)
        return {'success': False, 'message': f'Deployment failed: {str(e)}'}

def cleanup_failed_deployment(project_path, project_id):
    """Clean up failed deployment"""
    try:
        print(f"🧹 Cleaning up failed deployment: {project_id}")
        
        # Remove project folder
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        
        # Clean up nginx config
        nginx_manager = NginxManager()
        nginx_manager.cleanup_config(project_id)
        
        # Clean up database
        db_manager = DatabaseManager()
        db_manager.cleanup_database(project_id)
        
        print(f"✅ Cleanup completed for: {project_id}")
        
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")
        
    except Exception as e:
        print(f"⚠️ Cleanup error: {e}")

def get_recommended_nameservers():
    """Get recommended nameservers based on server provider"""
    try:
        # Try to detect server provider
        result = subprocess.run(['curl', '-s', 'http://169.254.169.254/metadata/v1/vendor-data'], 
                              capture_output=True, text=True, check=False)
        
        if 'digitalocean' in result.stdout.lower():
            return ['ns1.digitalocean.com', 'ns2.digitalocean.com', 'ns3.digitalocean.com']
        elif 'amazonaws' in result.stdout.lower():
            return ['Route 53 DNS (AWS)', 'Use AWS Route 53 for DNS management']
        else:
            return ['Cloudflare: nash.ns.cloudflare.com, rima.ns.cloudflare.com', 
                   'Or use your domain registrar nameservers']
    except:
        return ['Cloudflare: nash.ns.cloudflare.com, rima.ns.cloudflare.com', 
               'Or use your domain registrar nameservers']
