from flask import Flask, render_template, request, jsonify, flash, redirect, url_for
import os
import subprocess
import shutil
import uuid
from werkzeug.utils import secure_filename
import json
import time

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = '/tmp/auto-hosting'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy_project():
    try:
        # Get form data
        git_repo = request.form.get('git_repo')
        domain = request.form.get('domain', '')
        port = request.form.get('port', '80')
        
        # Handle file uploads
        db_file = request.files.get('database_file')
        env_file = request.files.get('env_file')
        
        if not git_repo:
            return jsonify({'success': False, 'message': 'Git repository URL is required'})
        
        # Generate unique project ID
        project_id = str(uuid.uuid4())[:8]
        project_path = f"/var/www/{project_id}"
        
        # Start deployment process
        deployment_result = deploy_laravel_project(
            git_repo, project_path, project_id, 
            db_file, env_file, domain, port
        )
        
        return jsonify(deployment_result)
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

def deploy_laravel_project(git_repo, project_path, project_id, db_file, env_file, domain, port):
    try:
        # Step 1: Clone repository
        print(f"Cloning repository: {git_repo}")
        subprocess.run(['git', 'clone', git_repo, project_path], check=True)
        
        # Step 2: Setup Laravel project
        setup_laravel(project_path, project_id, db_file, env_file)
        
        # Step 3: Configure web server
        configure_nginx(project_path, project_id, domain, port)
        
        # Step 4: Setup database if provided
        if db_file:
            setup_database(project_path, project_id, db_file)
        
        # Step 5: Setup SSL if domain provided
        ssl_result = ""
        if domain:
            ssl_result = setup_ssl(domain)
        
        # Step 6: Start services
        restart_services()
        
        access_url = f"http://{domain if domain else 'localhost'}:{port if port != '80' else ''}"
        
        return {
            'success': True,
            'message': 'Project deployed successfully!',
            'project_id': project_id,
            'access_url': access_url,
            'ssl_status': ssl_result
        }
        
    except Exception as e:
        # Cleanup on failure
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        return {'success': False, 'message': f'Deployment failed: {str(e)}'}

def setup_laravel(project_path, project_id, db_file, env_file):
    # Check PHP version and handle compatibility
    try:
        php_version = subprocess.check_output(['php', '-v']).decode('utf-8')
        print(f"PHP Version: {php_version.split()[1]}")
    except:
        pass
    
    # Remove composer.lock to avoid version conflicts
    composer_lock = os.path.join(project_path, 'composer.lock')
    if os.path.exists(composer_lock):
        os.remove(composer_lock)
        print("Removed composer.lock to avoid version conflicts")
    
    # Update composer.json to be compatible with PHP 8.1
    fix_composer_compatibility(project_path)
    
    # Install dependencies with update to resolve conflicts
    try:
        # First try composer install
        subprocess.run(['composer', 'install', '--no-dev', '--optimize-autoloader', '--no-interaction'], 
                      cwd=project_path, check=True, env={'COMPOSER_ALLOW_SUPERUSER': '1'})
    except subprocess.CalledProcessError:
        print("Composer install failed, trying composer update...")
        # If install fails, try update to resolve dependencies
        subprocess.run(['composer', 'update', '--no-dev', '--optimize-autoloader', '--no-interaction'], 
                      cwd=project_path, check=True, env={'COMPOSER_ALLOW_SUPERUSER': '1'})
    
    # Handle .env file
    if env_file:
        env_file.save(os.path.join(project_path, '.env'))
    else:
        # Copy .env.example to .env
        env_example = os.path.join(project_path, '.env.example')
        env_target = os.path.join(project_path, '.env')
        if os.path.exists(env_example):
            subprocess.run(['cp', '.env.example', '.env'], cwd=project_path, check=True)
        else:
            # Create basic .env if .env.example doesn't exist
            create_basic_env(project_path)
    
    # Generate application key
    subprocess.run(['php', 'artisan', 'key:generate', '--force'], cwd=project_path, check=True)
    
    # Fix file permissions
    subprocess.run(['chmod', '-R', '755', project_path], check=True)
    subprocess.run(['chmod', '-R', '777', f'{project_path}/storage'], check=True)
    subprocess.run(['chmod', '-R', '777', f'{project_path}/bootstrap/cache'], check=True)
    
    # Change ownership to web server user
    subprocess.run(['chown', '-R', 'www-data:www-data', project_path], check=True)
    
    # Fix path issues for Windows/Linux compatibility
    fix_asset_paths(project_path)

def fix_composer_compatibility(project_path):
    """Fix composer.json to be compatible with PHP 8.1"""
    composer_json_path = os.path.join(project_path, 'composer.json')
    
    if os.path.exists(composer_json_path):
        with open(composer_json_path, 'r') as f:
            composer_data = json.load(f)
        
        # Update PHP requirement to be compatible with 8.1
        if 'require' in composer_data:
            if 'php' in composer_data['require']:
                # Change PHP requirement to support 8.1
                composer_data['require']['php'] = '^8.1'
                print("Updated PHP requirement to ^8.1")
            
            # Update problematic packages to versions compatible with PHP 8.1
            problematic_packages = {
                'symfony/css-selector': '^6.0',
                'symfony/event-dispatcher': '^6.0', 
                'symfony/string': '^6.0',
                'symfony/console': '^6.0',
                'symfony/process': '^6.0',
                'symfony/http-kernel': '^6.0',
                'symfony/routing': '^6.0'
            }
            
            for package, version in problematic_packages.items():
                if package in composer_data['require']:
                    composer_data['require'][package] = version
                    print(f"Updated {package} to {version}")
        
        # Save updated composer.json
        with open(composer_json_path, 'w') as f:
            json.dump(composer_data, f, indent=4)
        
        print("Updated composer.json for PHP 8.1 compatibility")

def create_basic_env(project_path):
    """Create a basic .env file"""
    basic_env = """APP_NAME=Laravel
APP_ENV=production
APP_KEY=
APP_DEBUG=false
APP_URL=http://localhost

LOG_CHANNEL=stack
LOG_DEPRECATIONS_CHANNEL=null
LOG_LEVEL=debug

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=laravel
DB_USERNAME=root
DB_PASSWORD=

BROADCAST_DRIVER=log
CACHE_DRIVER=file
FILESYSTEM_DRIVER=local
QUEUE_CONNECTION=sync
SESSION_DRIVER=file
SESSION_LIFETIME=120

MEMCACHED_HOST=127.0.0.1

REDIS_HOST=127.0.0.1
REDIS_PASSWORD=null
REDIS_PORT=6379

MAIL_MAILER=smtp
MAIL_HOST=mailhog
MAIL_PORT=1025
MAIL_USERNAME=null
MAIL_PASSWORD=null
MAIL_ENCRYPTION=null
MAIL_FROM_ADDRESS=null
MAIL_FROM_NAME="${APP_NAME}"
"""
    
    env_path = os.path.join(project_path, '.env')
    with open(env_path, 'w') as f:
        f.write(basic_env)
    
    print("Created basic .env file")

def fix_asset_paths(project_path):
    # Create a helper script to fix asset paths
    asset_fix_script = f"""
cd {project_path}
# Clear caches
php artisan config:clear
php artisan cache:clear
php artisan view:clear
php artisan route:clear

# Optimize for production
php artisan config:cache
php artisan route:cache
php artisan view:cache

# Fix asset paths in blade templates
find resources/views -name "*.blade.php" -exec sed -i 's/\\\\/\\//g' {{}} \\;
"""
    
    with open('/tmp/asset_fix.sh', 'w') as f:
        f.write(asset_fix_script)
    
    subprocess.run(['bash', '/tmp/asset_fix.sh'], check=True)

def configure_nginx(project_path, project_id, domain, port):
    nginx_config = f"""
server {{
    listen {port};
    server_name {domain if domain else '_'};
    root {project_path}/public;
    index index.php index.html index.htm;

    location / {{
        try_files $uri $uri/ /index.php?$query_string;
    }}

    location ~ \\.php$ {{
        fastcgi_pass unix:/var/run/php/php8.2-fpm.sock;
        fastcgi_index index.php;
        fastcgi_param SCRIPT_FILENAME $realpath_root$fastcgi_script_name;
        include fastcgi_params;
    }}

    location ~ /\\.ht {{
        deny all;
    }}

    # Handle static assets
    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }}
}}
"""
    
    config_path = f'/etc/nginx/sites-available/{project_id}'
    with open(config_path, 'w') as f:
        f.write(nginx_config)
    
    # Enable site
    subprocess.run(['ln', '-sf', config_path, f'/etc/nginx/sites-enabled/{project_id}'], check=True)

def setup_database(project_path, project_id, db_file):
    # Create database
    db_name = f"laravel_{project_id}"
    subprocess.run(['mysql', '-e', f'CREATE DATABASE IF NOT EXISTS {db_name}'], check=True)
    
    # Import database
    db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
    db_file.save(db_file_path)
    
    subprocess.run(['mysql', db_name], stdin=open(db_file_path, 'r'), check=True)
    
    # Update .env with database settings
    env_path = os.path.join(project_path, '.env')
    with open(env_path, 'a') as f:
        f.write(f'\nDB_DATABASE={db_name}\n')
        f.write('DB_USERNAME=root\n')
        f.write('DB_PASSWORD=\n')
    
    # Run migrations
    subprocess.run(['php', 'artisan', 'migrate', '--force'], cwd=project_path, check=True)

def setup_ssl(domain):
    try:
        # Install certbot if not already installed
        subprocess.run(['apt', 'update'], check=True)
        subprocess.run(['apt', 'install', '-y', 'certbot', 'python3-certbot-nginx'], check=True)
        
        # Get SSL certificate
        subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                       '--email', 'admin@example.com'], check=True)
        
        return "SSL certificate installed successfully"
    except:
        return "SSL installation failed - please install manually"

def restart_services():
    subprocess.run(['systemctl', 'restart', 'nginx'], check=True)
    subprocess.run(['systemctl', 'restart', 'php8.2-fpm'], check=True)

@app.route('/projects')
def list_projects():
    projects = []
    nginx_sites = '/etc/nginx/sites-enabled'
    if os.path.exists(nginx_sites):
        for site in os.listdir(nginx_sites):
            if os.path.islink(os.path.join(nginx_sites, site)):
                projects.append(site)
    return render_template('projects.html', projects=projects)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
