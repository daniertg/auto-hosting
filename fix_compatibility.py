import json
import os
import subprocess
import sys

def fix_laravel_compatibility(project_path):
    """Fix Laravel project compatibility issues"""
    
    print(f"Fixing compatibility for project: {project_path}")
    
    # 1. Remove composer.lock
    composer_lock = os.path.join(project_path, 'composer.lock')
    if os.path.exists(composer_lock):
        os.remove(composer_lock)
        print("✓ Removed composer.lock")
    
    # 2. Update composer.json
    composer_json_path = os.path.join(project_path, 'composer.json')
    if os.path.exists(composer_json_path):
        with open(composer_json_path, 'r') as f:
            composer_data = json.load(f)
        
        # Update PHP requirement
        if 'require' in composer_data and 'php' in composer_data['require']:
            composer_data['require']['php'] = '^8.1|^8.2'
            print("✓ Updated PHP requirement")
        
        # Update Symfony packages to compatible versions
        symfony_packages = {
            'symfony/css-selector': '^6.0',
            'symfony/event-dispatcher': '^6.0',
            'symfony/string': '^6.0',
            'symfony/console': '^6.0',
            'symfony/process': '^6.0',
            'symfony/http-kernel': '^6.0',
            'symfony/routing': '^6.0',
            'symfony/http-foundation': '^6.0',
            'symfony/finder': '^6.0'
        }
        
        updated_packages = []
        if 'require' in composer_data:
            for package, version in symfony_packages.items():
                if package in composer_data['require']:
                    composer_data['require'][package] = version
                    updated_packages.append(package)
        
        if updated_packages:
            print(f"✓ Updated packages: {', '.join(updated_packages)}")
        
        # Save updated composer.json
        with open(composer_json_path, 'w') as f:
            json.dump(composer_data, f, indent=4)
    
    # 3. Clear caches and run composer update
    try:
        os.chdir(project_path)
        
        # Clear Laravel caches
        subprocess.run(['php', 'artisan', 'config:clear'], check=False)
        subprocess.run(['php', 'artisan', 'cache:clear'], check=False)
        subprocess.run(['php', 'artisan', 'view:clear'], check=False)
        
        # Run composer update with proper environment
        env = os.environ.copy()
        env['COMPOSER_ALLOW_SUPERUSER'] = '1'
        
        result = subprocess.run([
            'composer', 'update', 
            '--no-dev', 
            '--optimize-autoloader', 
            '--no-interaction',
            '--prefer-stable'
        ], env=env, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ Composer update successful")
        else:
            print(f"✗ Composer update failed: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"✗ Error during update: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 fix_compatibility.py <project_path>")
        sys.exit(1)
    
    project_path = sys.argv[1]
    if fix_laravel_compatibility(project_path):
        print("✓ Compatibility fix completed successfully")
    else:
        print("✗ Compatibility fix failed")
        sys.exit(1)
