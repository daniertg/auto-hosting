import subprocess
import os
import re
from database_manager import DatabaseManager

class LaravelManager:
    def __init__(self):
        self.db_manager = DatabaseManager()
    
    def _install_dependencies(self, project_path):
        """Install Composer dependencies with better error handling"""
        try:
            # Remove vendor directory if corrupted
            vendor_dir = os.path.join(project_path, 'vendor')
            if os.path.exists(vendor_dir):
                import shutil
                shutil.rmtree(vendor_dir)
                print("✓ Removed corrupted vendor directory")
            
            # Clear composer cache
            env = os.environ.copy()
            env['COMPOSER_ALLOW_SUPERUSER'] = '1'
            
            subprocess.run(['composer', 'clear-cache'], cwd=project_path, env=env, check=False)
            print("✓ Cleared composer cache")
            
            # Install fresh dependencies
            result = subprocess.run([
                'composer', 'install', 
                '--no-dev', 
                '--optimize-autoloader', 
                '--no-interaction', 
                '--ignore-platform-reqs',
                '--prefer-dist'
            ], cwd=project_path, env=env, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Composer install successful")
                return True
            else:
                print(f"⚠️ Composer install failed, trying update: {result.stderr}")
                
                # If install fails, try update
                result = subprocess.run([
                    'composer', 'update', 
                    '--no-dev', 
                    '--optimize-autoloader', 
                    '--no-interaction', 
                    '--ignore-platform-reqs',
                    '--prefer-dist'
                ], cwd=project_path, env=env, capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    print("✅ Composer update successful")
                    return True
                else:
                    print(f"❌ Both composer install and update failed: {result.stderr}")
                    # Try compatibility fix
                    return self._fix_composer_compatibility(project_path)
                    
        except Exception as e:
            print(f"❌ Error installing dependencies: {str(e)}")
            return self._fix_composer_compatibility(project_path)

    def _fix_composer_compatibility(self, project_path):
        """Fix composer compatibility issues"""
        try:
            print("🔧 Attempting composer compatibility fix...")
            
            # Use the fix_compatibility script
            fix_script_path = os.path.join(os.path.dirname(__file__), 'fix_compatibility.py')
            if os.path.exists(fix_script_path):
                result = subprocess.run(['python3', fix_script_path, project_path], 
                                      capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    print("✅ Compatibility fix successful")
                    return True
                else:
                    print(f"⚠️ Compatibility fix failed: {result.stderr}")
            
            # Manual compatibility fix
            return self._manual_composer_fix(project_path)
            
        except Exception as e:
            print(f"❌ Compatibility fix error: {str(e)}")
            return False

    def _manual_composer_fix(self, project_path):
        """Manual composer fix as fallback"""
        try:
            print("🔧 Manual composer fix...")
            
            env = os.environ.copy()
            env['COMPOSER_ALLOW_SUPERUSER'] = '1'
            
            # Remove composer.lock
            composer_lock = os.path.join(project_path, 'composer.lock')
            if os.path.exists(composer_lock):
                os.remove(composer_lock)
                print("✓ Removed composer.lock")
            
            # Try install without optimization first
            result = subprocess.run([
                'composer', 'install', 
                '--no-interaction', 
                '--ignore-platform-reqs',
                '--no-scripts'
            ], cwd=project_path, env=env, capture_output=True, text=True, check=False)
            
            if result.returncode == 0:
                print("✅ Basic composer install successful")
                
                # Now try with optimization
                subprocess.run([
                    'composer', 'dump-autoload', 
                    '--optimize'
                ], cwd=project_path, env=env, check=False)
                
                return True
            else:
                print(f"❌ Manual fix failed: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"❌ Manual fix error: {str(e)}")
            return False

    def setup_laravel(self, project_path, project_name, db_file, env_file):
        """Setup Laravel project"""
        # Remove lock file
        composer_lock = os.path.join(project_path, 'composer.lock')
        if os.path.exists(composer_lock):
            os.remove(composer_lock)
        
        # Install dependencies with better error handling
        if not self._install_dependencies(project_path):
            print("⚠️ Dependency installation failed, continuing anyway...")
        
        # Setup .env file
        db_user, db_password = self.db_manager.get_credentials()
        self._setup_env_file(project_path, project_name, env_file, db_user, db_password)
        
        # Generate application key
        try:
            subprocess.run(['php', 'artisan', 'key:generate', '--force'], cwd=project_path, check=True)
        except Exception as e:
            print(f"⚠️ Key generation failed: {e}")
        
        # Run migrations
        migration_result = self._run_migrations(project_path)
        if not migration_result:
            print("⚠️ Migration failed but continuing with deployment")
        
        # Fix permissions
        self._fix_permissions(project_path)
        
        # Clear caches
        self._clear_caches(project_path)
        
        print("✅ Laravel setup completed")
    
    def _setup_env_file(self, project_path, project_name, env_file, db_user, db_password):
        """Setup .env file"""
        if env_file:
            env_file.save(os.path.join(project_path, '.env'))
            self._fix_env_database_config(os.path.join(project_path, '.env'), project_name, db_user, db_password)
        else:
            self._create_basic_env(project_path, project_name, db_user, db_password)
    
    def _fix_env_database_config(self, env_path, project_name, db_user, db_password):
        """Fix database configuration in .env file"""
        with open(env_path, 'r') as f:
            content = f.read()
        
        # Replace problematic database hosts
        content = content.replace('DB_HOST=db', 'DB_HOST=127.0.0.1')
        content = content.replace('DB_HOST=mysql', 'DB_HOST=127.0.0.1')
        content = content.replace('DB_HOST=database', 'DB_HOST=127.0.0.1')
        content = content.replace('DB_HOST=localhost', 'DB_HOST=127.0.0.1')
        
        # Update database credentials
        content = re.sub(r'DB_DATABASE=.*', f'DB_DATABASE=laravel_{project_name}', content)
        content = re.sub(r'DB_USERNAME=.*', f'DB_USERNAME={db_user}', content)
        content = re.sub(r'DB_PASSWORD=.*', f'DB_PASSWORD={db_password}', content)
        
        # Add missing config if not present
        if 'DB_DATABASE=' not in content:
            content += f'\nDB_DATABASE=laravel_{project_name}'
        if 'DB_USERNAME=' not in content:
            content += f'\nDB_USERNAME={db_user}'
        if 'DB_PASSWORD=' not in content:
            content += f'\nDB_PASSWORD={db_password}'
        
        with open(env_path, 'w') as f:
            f.write(content)
    
    def _create_basic_env(self, project_path, project_name, db_user, db_password):
        """Create basic .env file"""
        basic_env = f"""APP_NAME=Laravel
APP_ENV=production
APP_KEY=
APP_DEBUG=false
APP_URL=http://localhost

DB_CONNECTION=mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_DATABASE=laravel_{project_name}
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
        subprocess.run(['php', 'artisan', 'view:clear'], cwd=project_path, check=False)
