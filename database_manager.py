import subprocess
import os
from werkzeug.utils import secure_filename

class DatabaseManager:
    def __init__(self):
        self.db_user, self.db_password = self.test_mysql_connection()
    
    def test_mysql_connection(self):
        """Test MySQL connection and return working credentials"""
        # Try root with no password
        try:
            subprocess.run(['mysql', '-u', 'root', '-e', 'SELECT 1;'], 
                          capture_output=True, text=True, check=True)
            return ('root', '')
        except:
            pass
        
        # Try laravel user
        try:
            subprocess.run(['mysql', '-u', 'laravel', '-plaravel123', '-e', 'SELECT 1;'], 
                          capture_output=True, text=True, check=True)
            return ('laravel', 'laravel123')
        except:
            pass
        
        raise Exception("No working MySQL credentials found")
    
    def setup_database(self, project_name, db_file):
        """Setup database for project"""
        db_name = f"laravel_{project_name}"
        
        # Drop existing database first (for port replacement)
        print(f"🗄️ Setting up database: {db_name}")
        drop_db_cmd = f"DROP DATABASE IF EXISTS {db_name};"
        self._execute_mysql_command(drop_db_cmd)
        print(f"✓ Cleaned existing database: {db_name}")
        
        # Create database with proper charset
        create_db_cmd = f"CREATE DATABASE {db_name} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
        self._execute_mysql_command(create_db_cmd)
        
        # Import database file if provided
        if db_file:
            self._import_database_file(db_name, db_file)
        
        print(f"✅ Database {db_name} ready")
    
    def cleanup_database(self, project_name):
        """Clean up database for project"""
        db_name = f"laravel_{project_name}"
        drop_db_cmd = f"DROP DATABASE IF EXISTS {db_name};"
        self._execute_mysql_command(drop_db_cmd, check=False)
    
    def _execute_mysql_command(self, command, check=True):
        """Execute MySQL command with proper credentials"""
        if self.db_password:
            cmd = ['mysql', '-u', self.db_user, f'-p{self.db_password}', '-e', command]
        else:
            cmd = ['mysql', '-u', self.db_user, '-e', command]
        
        subprocess.run(cmd, check=check)
    
    def _import_database_file(self, db_name, db_file):
        """Import database file"""
        db_file_path = f'/tmp/{secure_filename(db_file.filename)}'
        db_file.save(db_file_path)
        
        try:
            if self.db_password:
                cmd = ['mysql', '-u', self.db_user, f'-p{self.db_password}', db_name]
            else:
                cmd = ['mysql', '-u', self.db_user, db_name]
            
            with open(db_file_path, 'r') as f:
                subprocess.run(cmd, stdin=f, check=True)
            
            print("✅ Database imported successfully")
        except Exception as e:
            print(f"⚠️ Database import failed: {str(e)}")
            # Continue anyway, will use migrations instead
    
    def get_credentials(self):
        """Get database credentials"""
        return self.db_user, self.db_password
