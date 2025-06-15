#!/usr/bin/env python3
import os
import json
import subprocess
import sys

def fix_existing_project(project_path):
    """Fix compatibility issues for already deployed Laravel project"""
    
    if not os.path.exists(project_path):
        print(f"Project path {project_path} does not exist!")
        return False
    
    print(f"Fixing project at: {project_path}")
    
    # 1. Remove composer.lock
    composer_lock = os.path.join(project_path, 'composer.lock')
    if os.path.exists(composer_lock):
        os.remove(composer_lock)
        print("✓ Removed composer.lock")
    
    # 2. Fix composer.json
    composer_json_path = os.path.join(project_path, 'composer.json')
    if os.path.exists(composer_json_path):
        with open(composer_json_path, 'r') as f:
            composer_data = json.load(f)
        
        # Update PHP requirement
        if 'require' in composer_data and 'php' in composer_data['require']:
            composer_data['require']['php'] = '^8.1|^8.2'
            
        # Downgrade Symfony packages
        symfony_packages = {
            'symfony/css-selector': '^6.0',
            'symfony/event-dispatcher': '^6.0',
            'symfony/string': '^6.0',
            'symfony/console': '^6.0'
        }
        
        if 'require' in composer_data:
            for package, version in symfony_packages.items():
                if package in composer_data['require']:
                    composer_data['require'][package] = version
        
        with open(composer_json_path, 'w') as f:
            json.dump(composer_data, f, indent=4)
        
        print("✓ Updated composer.json")
    
    # 3. Run composer update
    composer_env = os.environ.copy()
    composer_env['COMPOSER_ALLOW_SUPERUSER'] = '1'
    
    try:
        print("Running composer update...")
        result = subprocess.run(['composer', 'update', '--no-dev', '--optimize-autoloader', '--no-interaction'], 
                              cwd=project_path, env=composer_env, 
                              capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ Composer update successful")
        else:
            print("Composer update failed, trying with --ignore-platform-reqs...")
            result = subprocess.run(['composer', 'update', '--no-dev', '--optimize-autoloader', 
                                   '--no-interaction', '--ignore-platform-reqs'], 
                                  cwd=project_path, env=composer_env, 
                                  capture_output=True, text=True)
            
            if result.returncode == 0:
                print("✓ Composer update successful with --ignore-platform-reqs")
            else:
                print(f"✗ Composer update failed: {result.stderr}")
                return False
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    
    # 4. Clear Laravel caches
    try:
        subprocess.run(['php', 'artisan', 'config:clear'], cwd=project_path, check=False)
        subprocess.run(['php', 'artisan', 'cache:clear'], cwd=project_path, check=False)
        subprocess.run(['php', 'artisan', 'view:clear'], cwd=project_path, check=False)
        print("✓ Cleared Laravel caches")
    except:
        pass
    
    # 5. Fix database configuration
    env_path = os.path.join(project_path, '.env')
    if os.path.exists(env_path):
        fix_env_database(env_path)
        print("✓ Fixed database configuration")
    
    print("✓ Project fixed successfully!")
    return True

def fix_env_database(env_path):
    """Fix database configuration in existing .env file"""
    
    with open(env_path, 'r') as f:
        content = f.read()
    
    # Fix common database hostname issues
    fixes = {
        'DB_HOST=db': 'DB_HOST=127.0.0.1',
        'DB_HOST=mysql': 'DB_HOST=127.0.0.1',
        'DB_HOST=localhost': 'DB_HOST=127.0.0.1',
        'DB_PASSWORD=password': 'DB_PASSWORD=',
        'DB_PASSWORD=secret': 'DB_PASSWORD='
    }
    
    for old, new in fixes.items():
        if old in content:
            content = content.replace(old, new)
            print(f"  - Fixed: {old} -> {new}")
    
    # Ensure DB_CONNECTION is mysql
    if 'DB_CONNECTION=' not in content:
        content += '\nDB_CONNECTION=mysql'
    elif 'DB_CONNECTION=mysql' not in content:
        import re
        content = re.sub(r'DB_CONNECTION=.*', 'DB_CONNECTION=mysql', content)
    
    with open(env_path, 'w') as f:
        f.write(content)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 manual_fix.py /path/to/laravel/project")
        print("Example: python3 manual_fix.py /var/www/12345678")
        sys.exit(1)
    
    project_path = sys.argv[1]
    success = fix_existing_project(project_path)
    
    if not success:
        sys.exit(1)
