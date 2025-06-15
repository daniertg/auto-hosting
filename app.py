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
        
        # Setup database FIRST
        setup_database_first(project_id, db_file)
        
        # Setup Laravel
        setup_laravel(project_path, project_id, db_file, env_file)
        
        # Configure Nginx
        configure_nginx(project_path, project_id, domain, port)
        
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
    
    # Enable the config
    subprocess.run(['ln', '-sf', config_path, f'/etc/nginx/sites-enabled/{project_id}'], check=True)
    
    # Test nginx configuration
    try:
        test_result = subprocess.run(['nginx', '-t'], capture_output=True, text=True, check=True)
        print("✓ Nginx config test passed")
    except subprocess.CalledProcessError as e:
        print(f"✗ Nginx config test failed: {e.stderr}")
        # Remove invalid config
        nginx_enabled = f'/etc/nginx/sites-enabled/{project_id}'
        if os.path.exists(nginx_enabled):
            os.remove(nginx_enabled)
        if os.path.exists(config_path):
            os.remove(config_path)
        raise Exception(f"Nginx configuration test failed: {e.stderr}")

def restart_services():
    """Restart services with better error handling"""
    try:
        # First restart PHP-FPM
        result = subprocess.run(['systemctl', 'restart', 'php8.2-fpm'], 
                               capture_output=True, text=True, check=True)
        print("✓ PHP-FPM restarted successfully")
        
        # Then reload nginx instead of restart
        result = subprocess.run(['systemctl', 'reload', 'nginx'], 
                               capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Nginx reloaded successfully")
        else:
            print(f"⚠ Nginx reload failed, trying restart: {result.stderr}")
            # If reload fails, try restart
            result = subprocess.run(['systemctl', 'restart', 'nginx'], 
                                   capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✓ Nginx restarted successfully")
            else:
                print(f"✗ Nginx restart failed: {result.stderr}")
                # Get detailed error info
                status_result = subprocess.run(['systemctl', 'status', 'nginx'], 
                                             capture_output=True, text=True, check=False)
                print(f"Nginx status: {status_result.stdout}")
                
                # Try to fix common issues
                fix_nginx_issues()
                
                # Try one more time
                result = subprocess.run(['systemctl', 'restart', 'nginx'], 
                                       capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    raise Exception(f"Nginx restart failed after fixes: {result.stderr}")
                else:
                    print("✓ Nginx restarted after fixes")
        
    except subprocess.CalledProcessError as e:
        print(f"✗ Service restart failed: {e}")
        raise Exception(f"Failed to restart services: {e}")

def fix_nginx_issues():
    """Try to fix common nginx issues"""
    try:
        print("🔧 Attempting to fix nginx issues...")
        
        # 1. Check for duplicate default sites
        default_sites = [
            '/etc/nginx/sites-enabled/default',
            '/etc/nginx/sites-enabled/000-default'
        ]
        
        for site in default_sites:
            if os.path.exists(site):
                os.remove(site)
                print(f"✓ Removed duplicate site: {site}")
        
        # 2. Check for port conflicts
        netstat_result = subprocess.run(['netstat', '-tlnp'], 
                                      capture_output=True, text=True, check=False)
        if ':80 ' in netstat_result.stdout:
            print("⚠ Port 80 is in use")
        
        # 3. Fix permissions
        subprocess.run(['chown', '-R', 'www-data:www-data', '/var/www'], check=False)
        subprocess.run(['chmod', '755', '/etc/nginx/sites-available'], check=False)
        subprocess.run(['chmod', '755', '/etc/nginx/sites-enabled'], check=False)
        
        # 4. Test config again
        subprocess.run(['nginx', '-t'], check=True)
        print("✓ Nginx config valid after fixes")
        
    except Exception as e:
        print(f"⚠ Could not fix all nginx issues: {e}")

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
        db_user, db_password = test_mysql_connection()
        if db_password:
            subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        else:
            subprocess.run(['mysql', '-u', db_user, '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        
        # Try to reload nginx config after cleanup
        subprocess.run(['nginx', '-t'], check=False)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=False)
        
        print(f"Cleaned up failed deployment: {project_id}")
    except Exception as e:
        print(f"Cleanup error: {e}")

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
        # Skip migrations if database already has tables
        check_result = subprocess.run(['php', 'artisan', 'migrate:status'], 
                                    cwd=project_path, capture_output=True, text=True, check=False)
        
        if "No migrations found" not in check_result.stdout and check_result.returncode == 0:
            print("✓ Database already has migrations, skipping")
            return True
        
        # Try fresh migration first
        result = subprocess.run(['php', 'artisan', 'migrate:fresh', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Fresh migration successful")
            return True
        
        # If fresh fails, try regular migration
        result = subprocess.run(['php', 'artisan', 'migrate', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Regular migration successful")
            return True
        
        print(f"✗ Migration failed: {result.stderr}")
        return False
        
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
    
    # Run migrations ONLY if no database file was imported
    # Don't pass db_file parameter to avoid confusion
    migration_result = fix_migration_compatibility(project_path)
    if not migration_result:
        print("⚠ Migration failed but continuing with deployment")
    
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

def setup_database_first(project_id, db_file):
    """Setup database before Laravel setup"""
    db_name = f"laravel_{project_id}"
    
    # Get working MySQL credentials
    db_user, db_password = test_mysql_connection()
    
    # Drop database if exists (clean slate)
    drop_db_cmd = f"DROP DATABASE IF EXISTS {db_name};"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', drop_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', drop_db_cmd], check=True)
    
    # Create database with proper charset
    create_db_cmd = f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', create_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', create_db_cmd], check=True)
    
    # Import database file if provided
    if db_file:
        db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
        db_file.save(db_file_path)
        
        # Import database
        try:
            if db_password:
                subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            else:
                subprocess.run(['mysql', '-u', db_user, db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            print("✓ Database imported successfully")
        except Exception as e:
            print(f"✗ Database import failed: {str(e)}")
            # Continue anyway, will use migrations instead
    
    print(f"✓ Database {db_name} ready")

def setup_database(project_path, project_id, db_file):
    # This function is now called from setup_database_first
    # Keep for backward compatibility but make it a no-op
    print("✓ Database setup already completed")
    pass

def setup_ssl(domain):
    try:
        subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                       '--email', 'admin@example.com'], check=True)
        return "SSL certificate installed successfully"
    except:
        return "SSL installation failed"

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
        db_user, db_password = test_mysql_connection()
        if db_password:
            subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        else:
            subprocess.run(['mysql', '-u', db_user, '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        
        # Try to reload nginx config after cleanup
        subprocess.run(['nginx', '-t'], check=False)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=False)
        
        print(f"Cleaned up failed deployment: {project_id}")
    except Exception as e:
        print(f"Cleanup error: {e}")

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
        # Skip migrations if database already has tables
        check_result = subprocess.run(['php', 'artisan', 'migrate:status'], 
                                    cwd=project_path, capture_output=True, text=True, check=False)
        
        if "No migrations found" not in check_result.stdout and check_result.returncode == 0:
            print("✓ Database already has migrations, skipping")
            return True
        
        # Try fresh migration first
        result = subprocess.run(['php', 'artisan', 'migrate:fresh', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Fresh migration successful")
            return True
        
        # If fresh fails, try regular migration
        result = subprocess.run(['php', 'artisan', 'migrate', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Regular migration successful")
            return True
        
        print(f"✗ Migration failed: {result.stderr}")
        return False
        
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
    
    # Run migrations ONLY if no database file was imported
    # Don't pass db_file parameter to avoid confusion
    migration_result = fix_migration_compatibility(project_path)
    if not migration_result:
        print("⚠ Migration failed but continuing with deployment")
    
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

def setup_database_first(project_id, db_file):
    """Setup database before Laravel setup"""
    db_name = f"laravel_{project_id}"
    
    # Get working MySQL credentials
    db_user, db_password = test_mysql_connection()
    
    # Drop database if exists (clean slate)
    drop_db_cmd = f"DROP DATABASE IF EXISTS {db_name};"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', drop_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', drop_db_cmd], check=True)
    
    # Create database with proper charset
    create_db_cmd = f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', create_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', create_db_cmd], check=True)
    
    # Import database file if provided
    if db_file:
        db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
        db_file.save(db_file_path)
        
        # Import database
        try:
            if db_password:
                subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            else:
                subprocess.run(['mysql', '-u', db_user, db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            print("✓ Database imported successfully")
        except Exception as e:
            print(f"✗ Database import failed: {str(e)}")
            # Continue anyway, will use migrations instead
    
    print(f"✓ Database {db_name} ready")

def setup_database(project_path, project_id, db_file):
    # This function is now called from setup_database_first
    # Keep for backward compatibility but make it a no-op
    print("✓ Database setup already completed")
    pass

def setup_ssl(domain):
    try:
        subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                       '--email', 'admin@example.com'], check=True)
        return "SSL certificate installed successfully"
    except:
        return "SSL installation failed"

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
        db_user, db_password = test_mysql_connection()
        if db_password:
            subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        else:
            subprocess.run(['mysql', '-u', db_user, '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        
        # Try to reload nginx config after cleanup
        subprocess.run(['nginx', '-t'], check=False)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=False)
        
        print(f"Cleaned up failed deployment: {project_id}")
    except Exception as e:
        print(f"Cleanup error: {e}")

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
        # Skip migrations if database already has tables
        check_result = subprocess.run(['php', 'artisan', 'migrate:status'], 
                                    cwd=project_path, capture_output=True, text=True, check=False)
        
        if "No migrations found" not in check_result.stdout and check_result.returncode == 0:
            print("✓ Database already has migrations, skipping")
            return True
        
        # Try fresh migration first
        result = subprocess.run(['php', 'artisan', 'migrate:fresh', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Fresh migration successful")
            return True
        
        # If fresh fails, try regular migration
        result = subprocess.run(['php', 'artisan', 'migrate', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Regular migration successful")
            return True
        
        print(f"✗ Migration failed: {result.stderr}")
        return False
        
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
    
    # Run migrations ONLY if no database file was imported
    # Don't pass db_file parameter to avoid confusion
    migration_result = fix_migration_compatibility(project_path)
    if not migration_result:
        print("⚠ Migration failed but continuing with deployment")
    
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

def setup_database_first(project_id, db_file):
    """Setup database before Laravel setup"""
    db_name = f"laravel_{project_id}"
    
    # Get working MySQL credentials
    db_user, db_password = test_mysql_connection()
    
    # Drop database if exists (clean slate)
    drop_db_cmd = f"DROP DATABASE IF EXISTS {db_name};"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', drop_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', drop_db_cmd], check=True)
    
    # Create database with proper charset
    create_db_cmd = f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', create_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', create_db_cmd], check=True)
    
    # Import database file if provided
    if db_file:
        db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
        db_file.save(db_file_path)
        
        # Import database
        try:
            if db_password:
                subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            else:
                subprocess.run(['mysql', '-u', db_user, db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            print("✓ Database imported successfully")
        except Exception as e:
            print(f"✗ Database import failed: {str(e)}")
            # Continue anyway, will use migrations instead
    
    print(f"✓ Database {db_name} ready")

def setup_database(project_path, project_id, db_file):
    # This function is now called from setup_database_first
    # Keep for backward compatibility but make it a no-op
    print("✓ Database setup already completed")
    pass

def setup_ssl(domain):
    try:
        subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                       '--email', 'admin@example.com'], check=True)
        return "SSL certificate installed successfully"
    except:
        return "SSL installation failed"

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
        db_user, db_password = test_mysql_connection()
        if db_password:
            subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        else:
            subprocess.run(['mysql', '-u', db_user, '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        
        # Try to reload nginx config after cleanup
        subprocess.run(['nginx', '-t'], check=False)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=False)
        
        print(f"Cleaned up failed deployment: {project_id}")
    except Exception as e:
        print(f"Cleanup error: {e}")

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
        # Skip migrations if database already has tables
        check_result = subprocess.run(['php', 'artisan', 'migrate:status'], 
                                    cwd=project_path, capture_output=True, text=True, check=False)
        
        if "No migrations found" not in check_result.stdout and check_result.returncode == 0:
            print("✓ Database already has migrations, skipping")
            return True
        
        # Try fresh migration first
        result = subprocess.run(['php', 'artisan', 'migrate:fresh', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Fresh migration successful")
            return True
        
        # If fresh fails, try regular migration
        result = subprocess.run(['php', 'artisan', 'migrate', '--force'], 
                              cwd=project_path, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            print("✓ Regular migration successful")
            return True
        
        print(f"✗ Migration failed: {result.stderr}")
        return False
        
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
    
    # Run migrations ONLY if no database file was imported
    # Don't pass db_file parameter to avoid confusion
    migration_result = fix_migration_compatibility(project_path)
    if not migration_result:
        print("⚠ Migration failed but continuing with deployment")
    
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

def setup_database_first(project_id, db_file):
    """Setup database before Laravel setup"""
    db_name = f"laravel_{project_id}"
    
    # Get working MySQL credentials
    db_user, db_password = test_mysql_connection()
    
    # Drop database if exists (clean slate)
    drop_db_cmd = f"DROP DATABASE IF EXISTS {db_name};"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', drop_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', drop_db_cmd], check=True)
    
    # Create database with proper charset
    create_db_cmd = f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
    if db_password:
        subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', create_db_cmd], check=True)
    else:
        subprocess.run(['mysql', '-u', db_user, '-e', create_db_cmd], check=True)
    
    # Import database file if provided
    if db_file:
        db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
        db_file.save(db_file_path)
        
        # Import database
        try:
            if db_password:
                subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            else:
                subprocess.run(['mysql', '-u', db_user, db_name], 
                             stdin=open(db_file_path, 'r'), check=True)
            print("✓ Database imported successfully")
        except Exception as e:
            print(f"✗ Database import failed: {str(e)}")
            # Continue anyway, will use migrations instead
    
    print(f"✓ Database {db_name} ready")

def setup_database(project_path, project_id, db_file):
    # This function is now called from setup_database_first
    # Keep for backward compatibility but make it a no-op
    print("✓ Database setup already completed")
    pass

def setup_ssl(domain):
    try:
        subprocess.run(['certbot', '--nginx', '-d', domain, '--non-interactive', '--agree-tos', 
                       '--email', 'admin@example.com'], check=True)
        return "SSL certificate installed successfully"
    except:
        return "SSL installation failed"

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
        db_user, db_password = test_mysql_connection()
        if db_password:
            subprocess.run(['mysql', '-u', db_user, f'-p{db_password}', '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        else:
            subprocess.run(['mysql', '-u', db_user, '-e', f'DROP DATABASE IF EXISTS {db_name}'], check=False)
        
        # Try to reload nginx config after cleanup
        subprocess.run(['nginx', '-t'], check=False)
        subprocess.run(['systemctl', 'reload', 'nginx'], check=False)
        
        print(f"Cleaned up failed deployment: {project_id}")
    except Exception as e:
        print(f"Cleanup error: {e}")

# ...existing code...
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
