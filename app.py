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
        # Clean up on failure
        if os.path.exists(project_path):
            shutil.rmtree(project_path)
        return {'success': False, 'message': f'Deployment failed: {str(e)}'}

def setup_laravel(project_path, project_id, db_file, env_file):
    # Remove lock file to avoid conflicts
    composer_lock = os.path.join(project_path, 'composer.lock')
    if os.path.exists(composer_lock):
        os.remove(composer_lock)
    
    # Install dependencies
    env = os.environ.copy()
    env['COMPOSER_ALLOW_SUPERUSER'] = '1'
    subprocess.run(['composer', 'update', '--no-dev', '--optimize-autoloader', '--no-interaction', '--ignore-platform-reqs'], 
                  cwd=project_path, check=True, env=env)
    
    # Handle .env file
    if env_file:
        env_file.save(os.path.join(project_path, '.env'))
    else:
        # Create basic .env
        create_basic_env(project_path, project_id)
    
    # Generate key
    subprocess.run(['php', 'artisan', 'key:generate', '--force'], cwd=project_path, check=True)
    
    # Fix permissions
    subprocess.run(['chmod', '-R', '755', project_path], check=True)
    subprocess.run(['chmod', '-R', '777', f'{project_path}/storage'], check=True)
    subprocess.run(['chmod', '-R', '777', f'{project_path}/bootstrap/cache'], check=True)
    subprocess.run(['chown', '-R', 'www-data:www-data', project_path], check=True)
    
    # Clear caches
    subprocess.run(['php', 'artisan', 'config:clear'], cwd=project_path, check=False)
    subprocess.run(['php', 'artisan', 'cache:clear'], cwd=project_path, check=False)
    subprocess.run(['php', 'artisan', 'view:clear'], cwd=project_path, check=False)

def create_basic_env(project_path, project_id):
    basic_env = f"""APP_NAME=Laravel
APP_ENV=production
APP_KEY=
APP_DEBUG=false
APP_URL=http://localhost

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=laravel_{project_id}
DB_USERNAME=root
DB_PASSWORD=

CACHE_DRIVER=file
SESSION_DRIVER=file
QUEUE_CONNECTION=sync
"""
    
    with open(os.path.join(project_path, '.env'), 'w') as f:
        f.write(basic_env)

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
    
    subprocess.run(['ln', '-sf', config_path, f'/etc/nginx/sites-enabled/{project_id}'], check=True)

def setup_database(project_path, project_id, db_file):
    db_name = f"laravel_{project_id}"
    subprocess.run(['mysql', '-e', f'CREATE DATABASE IF NOT EXISTS {db_name}'], check=True)
    
    db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
    db_file.save(db_file_path)
    
    subprocess.run(['mysql', db_name], stdin=open(db_file_path, 'r'), check=True)
    
    # Run migrations
    subprocess.run(['php', 'artisan', 'migrate', '--force'], cwd=project_path, check=False)

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
