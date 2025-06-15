from flask import Flask, render_template, request, jsonify
import os
from deployment_manager import deploy_laravel_project

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
        
        # Deploy project using deployment manager
        result = deploy_laravel_project(git_repo, db_file, env_file, domain, port)
        
        # Add DNS instructions to response if domain is used
        if result.get('success') and result.get('dns_info'):
            dns_info = result['dns_info']
            result['message'] += f"\n\n🌐 DNS Setup Required:\n"
            result['message'] += f"1. Go to your domain registrar ({domain})\n"
            result['message'] += f"2. Set these DNS records:\n"
            for record in dns_info['dns_records']:
                result['message'] += f"   - Type: {record['type']}, Name: {record['name']}, Value: {record['value']}\n"
            result['message'] += f"3. Or use these nameservers: {', '.join(dns_info['nameservers'])}\n"
            result['message'] += f"4. Wait 5-30 minutes for DNS propagation\n"
            result['message'] += f"5. Then access: {result['access_url']}"
        
        return jsonify(result)
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)