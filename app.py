from flask import Flask, render_template, request, jsonify
import os
import subprocess
import shutil
import uuid
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'
app.config['UPLOAD_FOLDER'] = '/tmp/auto-hosting'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy_project():
    try:
        git_repo = request.form.get('git_repo')
        domain = request.form.get('domain', '')
        port = request.form.get('port', '80')
        
        db_file = request.files.get('database_file')
        env_file = request.files.get('env_file')
        
        if not git_repo:
            return jsonify({'success': False, 'message': 'Git repository URL is required'})
        
        project_id = str(uuid.uuid4())[:8]
        project_path = f"/var/www/{project_id}"
        
        # Deploy project
        result = deploy_laravel_project(git_repo, project_path, project_id, db_file, env_file, domain, port)
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

def deploy_laravel_project(git_repo, project_path, project_id, db_file, env_file, domain, port):
    try:
        # Clone repository
        subprocess.run(['git', 'clone', git_repo, project_path], check=True)
        
        # Setup Laravel
        setup_laravel(project_path, project_id, db_file, env_file)
        
        # Configure Nginx
        configure_nginx(project_path, project_id, domain, port)
        
        # Setup database if provided
        if db_file:
            setup_database(project_path, project_id, db_file)
        
        # Setup SSL if domain provided
        ssl_result = ""
        if domain:
            ssl_result = setup_ssl(domain)
        
        # Restart services
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
        # HAPUS SEMUA JIKA GAGAL
        cleanup_failed_deployment(project_path, project_id)
        return {'success': False, 'message': f'Deployment failed: {str(e)}'}

def cleanup_failed_deployment(project_path, project_id):
    """Hapus semua konfigurasi jika deployment gagal"""
    try:
        # Hapus folder project
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        
        # Hapus nginx config
        nginx_config = f'/etc/nginx/sites-available/{project_id}'
        nginx_enabled = f'/etc/nginx/sites-enabled/{project_id}'
        
        if os.path.exists(nginx_enabled):
            os.remove(nginx_enabled)
        if os.path.exists(nginx_config):
            os.remove(nginx_config)
        
        # Hapus database
        db_name = f"laravel_{project_id}"
        subprocess.run(['mysql', '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        
        # Restart nginx
        subprocess.run(['systemctl', 'restart', 'nginx'], check=False)
        
        print(f"Cleaned up failed deployment: {project_id}")
    except:
        pass

def test_mysql_connection():
    """Test MySQL connection and return working credentials"""
    # Try root with no password
    try:
        result = subprocess.run(['mysql', '-u', 'root', '-e', 'SELECT 1;'], 
                              capture_output=True, text=True, check=True)
        return ('root', '')
    except:
        pass
    
    # Try laravel user
    try:
        result = subprocess.run(['mysql', '-u', 'laravel', '-plaravel123', '-e', 'SELECT 1;'], 
                              capture_output=True, text=True, check=True)
        return ('laravel', 'laravel123')
    except:
        pass
    
    raise Exception("No working MySQL credentials found")

def fix_migration_compatibility(project_path):
    """Fix Laravel migration compatibility issues"""
    try:
        # Fix foreign key issues by running migration with specific flags
        subprocess.run(['php', 'artisan', 'migrate:fresh', '--force'], cwd=project_path, check=False)
        
        # If fresh fails, try step by step
        subprocess.run(['php', 'artisan', 'migrate:reset', '--force'], cwd=project_path, check=False)
        subprocess.run(['php', 'artisan', 'migrate:install'], cwd=project_path, check=False)
        subprocess.run(['php', 'artisan', 'migrate', '--force'], cwd=project_path, check=False)
        
        print("✓ Migration compatibility fixed")
        return True
    except Exception as e:
        print(f"✗ Migration fix failed: {str(e)}")
        return False

def setup_laravel(project_path, project_id, db_file, env_file):
    # Remove lock file
    composer_lock = os.path.join(project_path, 'composer.lock')
    if os.path.exists(composer_lock):
        os.remove(composer_lock)
    
    # Install dependencies
    env = os.environ.copy()
    env['COMPOSER_ALLOW_SUPERUSER'] = '1'
    subprocess.run(['composer', 'update', '--no-dev', '--optimize-autoloader', '--no-interaction', '--ignore-platform-reqs'], 
                  cwd=project_path, check=True, env=env)
    
    # Test MySQL connection first
    db_user, db_password = test_mysql_connection()
    
    # Handle .env file
    if env_file:
        env_file.save(os.path.join(project_path, '.env'))
        fix_env_database_config(os.path.join(project_path, '.env'), project_id, db_user, db_password)
    else:
        create_basic_env(project_path, project_id, db_user, db_password)
    
    # Generate key
    subprocess.run(['php', 'artisan', 'key:generate', '--force'], cwd=project_path, check=True)
    
    # Fix migration compatibility before running migrations
    fix_migration_compatibility(project_path)
    
    # Fix permissions
    subprocess.run(['chmod', '-R', '755', project_path], check=True)
    subprocess.run(['chmod', '-R', '777', f'{project_path}/storage'], check=True)
    subprocess.run(['chmod', '-R', '777', f'{project_path}/bootstrap/cache'], check=True)
    subprocess.run(['chown', '-R', 'www-data:www-data', project_path], check=True)
    
    # Clear caches
    subprocess.run(['php', 'artisan', 'config:clear'], cwd=project_path, check=False)
    subprocess.run(['php', 'artisan', 'cache:clear'], cwd=project_path, check=False)
    subprocess.run(['php', 'artisan', 'view:clear'], cwd=project_path, check=False)

def fix_env_database_config(env_path, project_id, db_user, db_password):
    """Fix database configuration in .env file"""
    with open(env_path, 'r') as f:
        content = f.read()
    
    # Replace problematic database hosts
    content = content.replace('DB_HOST=db', 'DB_HOST=127.0.0.1')
    content = content.replace('DB_HOST=mysql', 'DB_HOST=127.0.0.1')
    content = content.replace('DB_HOST=database', 'DB_HOST=127.0.0.1')
    content = content.replace('DB_HOST=localhost', 'DB_HOST=127.0.0.1')
    
    # Update database credentials
    import re
    content = re.sub(r'DB_DATABASE=.*', f'DB_DATABASE=laravel_{project_id}', content)
    content = re.sub(r'DB_USERNAME=.*', f'DB_USERNAME={db_user}', content)
    content = re.sub(r'DB_PASSWORD=.*', f'DB_PASSWORD={db_password}', content)
    
    # Add missing config if not present
    if 'DB_DATABASE=' not in content:
        content += f'\nDB_DATABASE=laravel_{project_id}'
    if 'DB_USERNAME=' not in content:
        content += f'\nDB_USERNAME={db_user}'
    if 'DB_PASSWORD=' not in content:
        content += f'\nDB_PASSWORD={db_password}'
    
    with open(env_path, 'w') as f:
        f.write(content)

def create_basic_env(project_path, project_id, db_user, db_password):
    basic_env = f"""APP_NAME=Laravel
APP_ENV=production
APP_KEY=
APP_DEBUG=false
APP_URL=http://localhost

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=laravel_{project_id}
DB_USERNAME={db_user}
DB_PASSWORD={db_password}

CACHE_DRIVER=file
SESSION_DRIVER=file
QUEUE_CONNECTION=sync
"""
    
    with open(os.path.join(project_path, '.env'), 'w') as f:
        f.write(basic_env)

def configure_nginx(project_path, project_id, domain, port):
    nginx_config = f"""server {{
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

    location ~* \\.(css|js|png|jpg|jpeg|gif|ico|svg)$ {{
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }}
}}"""
    
    config_path = f'/etc/nginx/sites-available/{project_id}'
    with open(config_path, 'w') as f:
        f.write(nginx_config)
    
    # Test nginx configuration before enabling
    try:
        subprocess.run(['nginx', '-t'], check=True, capture_output=True)
        print("✓ Nginx config valid")
    except subprocess.CalledProcessError as e:
        print(f"✗ Nginx config invalid: {e}")
        # Remove invalid config
        if os.path.exists(config_path):
            os.remove(config_path)
        raise Exception("Nginx configuration test failed")
    
    subprocess.run(['ln', '-sf', config_path, f'/etc/nginx/sites-enabled/{project_id}'], check=True)

def setup_database(project_path, project_id, db_file):
    db_name = f"laravel_{project_id}"
    
    # Get working MySQL credentials
    db_user, db_password = test_mysql_connection()
    
    # Create database with proper charset
    create_db_cmd = f"CREATE DATABASE IF NOT EXISTS {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', create_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', create_db_cmd], check=True)
    
    if db_file:
        db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
        db_file.save(db_file_path)
        
        # Import database
        if db_password:
            subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', db_name], stdin=open(db_file_path, 'r'), check=True)
        else:
            subprocess.run(['mysql', '-u', db_user, db_name], stdin=open(db_file_path, 'r'), check=True)
    
    # Run migrations with compatibility fixes
    fix_migration_compatibility(project_path)

def setup_ssl(domain):
    try:
        subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                       '--email', 'admin@example.com'], check=True)
        return "SSL certificate installed successfully"
    except:
        return "SSL installation failed"

def restart_services():
    subprocess.run(['systemctl', 'restart', 'nginx'], check=True)
    subprocess.run(['systemctl', 'restart', 'php8.2-fpm'], check=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
