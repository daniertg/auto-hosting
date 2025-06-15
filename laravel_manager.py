import subprocess
import os
import re
from database_manager import DatabaseManager

class LaravelManager:
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def setup_laravel(self, project_path, project_id, db_file, env_file):
        """Setup Laravel project"""
        # Remove lock file
        composer_lock = os.path.join(project_path, 'composer.lock')
        if os.path.exists(composer_lock):
            os.remove(composer_lock)
        
        # Install dependencies
        self._install_dependencies(project_path)
        
        # Setup .env file
        db_user, db_password = self.db_manager.get_credentials()
        self._setup_env_file(project_path, project_id, env_file, db_user, db_password)
        
        # Generate application key
        subprocess.run(['php', 'artisan', 'key:generate', '--force'], cwd=project_path, check=True)
        
        # Run migrations
        migration_result = self._run_migrations(project_path)
        if not migration_result:
            print("⚠️ Migration failed but continuing with deployment")
        
        # Fix permissions
        self._fix_permissions(project_path)
        
        # Clear caches
        self._clear_caches(project_path)
        
        print("✅ Laravel setup completed")
    
    def _install_dependencies(self, project_path):
        """Install Composer dependencies"""
        env = os.environ.copy()
        env['COMPOSER_ALLOW_SUPERUSER'] = '1'
        subprocess.run([
            'composer', 'update', 
            '--no-dev', 
            '--optimize-autoloader', 
            '--no-interaction', 
            '--ignore-platform-reqs'
        ], cwd=project_path, check=True, env=env)
    
    def _setup_env_file(self, project_path, project_id, env_file, db_user, db_password):
        """Setup .env file"""
        if env_file:
            env_file.save(os.path.join(project_path, '.env'))
            self._fix_env_database_config(os.path.join(project_path, '.env'), project_id, db_user, db_password)
        else:
            self._create_basic_env(project_path, project_id, db_user, db_password)
    
    def _fix_env_database_config(self, env_path, project_id, db_user, db_password):
        """Fix database configuration in .env file"""
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Replace problematic database hosts
        content = content.replace('DB_HOST=db', 'DB_HOST=127.0.0.1')
        content = content.replace('DB_HOST=mysql', 'DB_HOST=127.0.0.1')
        content = content.replace('DB_HOST=database', 'DB_HOST=127.0.0.1')
        content = content.replace('DB_HOST=localhost', 'DB_HOST=127.0.0.1')
        
        # Update database credentials
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
    
    def _create_basic_env(self, project_path, project_id, db_user, db_password):
        """Create basic .env file"""
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
    
    def _run_migrations(self, project_path):
        """Run Laravel migrations"""
        try:
            # Check if migrations already exist
            check_result = subprocess.run(['php', 'artisan', 'migrate:status'], 
                                        cwd=project_path, capture_output=True, text=True, check=False)
            
            if "No migrations found" not in check_result.stdout and check_result.returncode == 0:
                print("✅ Database already has migrations, skipping")
                return True
            
            # Try fresh migration first
            result = subprocess.run(['php', 'artisan', 'migrate:fresh', '--force'], 
                                  cwd=project_path, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Fresh migration successful")
                return True
            
            # If fresh fails, try regular migration
            result = subprocess.run(['php', 'artisan', 'migrate', '--force'], 
                                  cwd=project_path, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Regular migration successful")
                return True
            
            print(f"⚠️ Migration failed: {result.stderr}")
            return False
            
        except Exception as e:
            print(f"⚠️ Migration error: {str(e)}")
            return False
    
    def _fix_permissions(self, project_path):
        """Fix file permissions"""
        subprocess.run(['chmod', '-R', '755', project_path], check=True)
        subprocess.run(['chmod', '-R', '777', f'{project_path}/storage'], check=True)
        subprocess.run(['chmod', '-R', '777', f'{project_path}/bootstrap/cache'], check=True)
        subprocess.run(['chown', '-R', 'www-data:www-data', project_path], check=True)
    
    def _clear_caches(self, project_path):
        """Clear Laravel caches"""
        subprocess.run(['php', 'artisan', 'config:clear'], cwd=project_path, check=False)
        subprocess.run(['php', 'artisan', 'cache:clear'], cwd=project_path, check=False)
        subprocess.run(['php', 'artisan', 'view:clear'], cwd=project_path, check=False)
