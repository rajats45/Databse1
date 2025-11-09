import subprocess, os, shlex, time, re
from flask import Flask, render_template, jsonify, request, send_file
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = '/tmp'
load_dotenv(os.path.join(PROJECT_DIR, '.env'))
DB_PASSWORD = os.getenv("MONGO_PASSWORD")
if not DB_PASSWORD: exit(1)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def run_command(command, timeout=60):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, timeout=timeout, cwd=PROJECT_DIR)
        return {"success": True, "output": result.stdout.strip()}
    except subprocess.TimeoutExpired: return {"success": False, "error": "Command timed out."}
    except subprocess.CalledProcessError as e: return {"success": False, "output": e.stdout, "error": e.stderr}
    except Exception as e: return {"success": False, "error": str(e)}

@app.route('/')
def index(): return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    # 1. Ensure base security: Deny all external access to 27017 by default
    run_command("sudo ufw deny 27017/tcp", timeout=10)
    # 2. Standard deploy
    run_command("docker compose pull", timeout=300)
    return jsonify(run_command("docker compose up -d", timeout=60))

@app.route('/get-rules', methods=['GET'])
def get_rules():
    # Parse 'ufw status' to find IPs allowed specifically for port 27017
    res = run_command("sudo ufw status", timeout=5)
    if not res["success"]: return jsonify({"rules": []})
    
    ips = []
    # Regex looks for lines like: "27017/tcp  ALLOW IN  1.2.3.4"
    for line in res["output"].split('\n'):
        if '27017' in line and 'ALLOW' in line:
            match = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
            if match: ips.append(match.group(1))
    # Remove duplicates and return
    return jsonify({"rules": list(set(ips))})

@app.route('/add-rule', methods=['POST'])
def add_rule():
    ip = request.json.get('ip')
    if not ip: return jsonify({"success": False, "error": "No IP."}), 400
    # Insert rule at top (position 1) to ensure it overrides any generic denies
    return jsonify(run_command(f"sudo ufw insert 1 allow from {shlex.quote(ip)} to any port 27017 proto tcp", timeout=10))

@app.route('/delete-rule', methods=['POST'])
def delete_rule():
    ip = request.json.get('ip')
    if not ip: return jsonify({"success": False, "error": "No IP."}), 400
    return jsonify(run_command(f"sudo ufw delete allow from {shlex.quote(ip)} to any port 27017 proto tcp", timeout=10))

# ... [KEEP YOUR EXISTING BACKUP/RESTORE/LOGS/STATUS FUNCTIONS EXACTLY AS THEY WERE] ...
# (I omitted them here to save space, paste your LAST working Backup/Restore functions here)
@app.route('/backup', methods=['GET', 'POST'])
def backup():
    # ... paste your last working backup code here ...
    pass # REMOVE THIS PASS WHEN YOU PASTE

@app.route('/restore', methods=['POST'])
def restore():
     # ... paste your last working restore code here ...
     pass # REMOVE THIS PASS WHEN YOU PASTE

@app.route('/logs', methods=['GET'])
def logs(): return jsonify(run_command("docker compose logs --tail=100", timeout=10))

@app.route('/status', methods=['GET'])
def get_status():
    try:
        res = subprocess.run("docker inspect --format '{{.State.Status}}' my-mongo-db", shell=True, check=True, capture_output=True, text=True, timeout=5)
        return jsonify({"success": True, "status": res.stdout.strip()})
    except: return jsonify({"success": True, "status": "not_deployed"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
