#!/usr/bin/env python3
import os
import re
import sys

def quick_fix_database_config(project_path):
    """Quick fix untuk masalah database configuration"""
    
    env_path = os.path.join(project_path, '.env')
    
    if not os.path.exists(env_path):
        print("File .env tidak ditemukan!")
        return False
    
    print(f"Memperbaiki konfigurasi database di: {env_path}")
    
    with open(env_path, 'r') as f:
        content = f.read()
    
    # Tampilkan konfigurasi database saat ini
    print("\nKonfigurasi database saat ini:")
    for line in content.split('\n'):
        if line.startswith('DB_'):
            print(f"  {line}")
    
    # Perbaikan otomatis
    fixes = {
        r'DB_HOST=db': 'DB_HOST=127.0.0.1',
        r'DB_HOST=mysql': 'DB_HOST=127.0.0.1', 
        r'DB_HOST=database': 'DB_HOST=127.0.0.1',
        r'DB_PASSWORD=.*': 'DB_PASSWORD=',
        r'DB_USERNAME=.*': 'DB_USERNAME=root'
    }
    
    for pattern, replacement in fixes.items():
        content = re.sub(pattern, replacement, content)
    
    # Pastikan ada konfigurasi minimal
    required_configs = [
        'DB_CONNECTION=mysql',
        'DB_HOST=127.0.0.1',
        'DB_PORT=3306',
        'DB_USERNAME=root',
        'DB_PASSWORD='
    ]
    
    for config in required_configs:
        key = config.split('=')[0]
        if f'{key}=' not in content:
            content += f'\n{config}'
        elif config not in content:
            content = re.sub(f'{key}=.*', config, content)
    
    # Simpan perubahan
    with open(env_path, 'w') as f:
        f.write(content)
    
    print("\nKonfigurasi database setelah diperbaiki:")
    with open(env_path, 'r') as f:
        for line in f.read().split('\n'):
            if line.startswith('DB_'):
                print(f"  {line}")
    
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 quick_db_fix.py /path/to/project")
        print("Example: python3 quick_db_fix.py /var/www/12345678")
        sys.exit(1)
    
    project_path = sys.argv[1]
    if quick_fix_database_config(project_path):
        print("\n✓ Database configuration berhasil diperbaiki!")
        print("Silakan coba akses website Laravel lagi.")
    else:
        print("\n✗ Gagal memperbaiki konfigurasi database.")
        sys.exit(1)
