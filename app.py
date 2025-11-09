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

def run_cmd(c, t=60):
    try:
        r = subprocess.run(c, shell=True, check=True, capture_output=True, text=True, timeout=t, cwd=PROJECT_DIR)
        return {"success": True, "output": r.stdout.strip()}
    except Exception as e: return {"success": False, "error": str(e)}

@app.route('/')
def index(): return render_template('index.html')

@app.route('/deploy', methods=['POST'])
def deploy():
    run_cmd("sudo ufw deny 27017/tcp", t=10)
    run_cmd("docker compose pull", t=300)
    return jsonify(run_cmd("docker compose up -d", t=60))

@app.route('/get-rules', methods=['GET'])
def get_rules():
    res = run_cmd("sudo ufw status", t=5)
    ips = []
    if res["success"]:
        for line in res["output"].split('\n'):
            if '27017' in line and 'ALLOW' in line:
                m = re.search(r'(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})', line)
                if m: ips.append(m.group(1))
    return jsonify({"rules": list(set(ips))})

@app.route('/add-rule', methods=['POST'])
def add_rule():
    ip = request.json.get('ip')
    if not ip: return jsonify({"error": "No IP"}), 400
    return jsonify(run_cmd(f"sudo ufw insert 1 allow from {shlex.quote(ip)} to any port 27017 proto tcp", t=10))

@app.route('/delete-rule', methods=['POST'])
def delete_rule():
    ip = request.json.get('ip')
    if not ip: return jsonify({"error": "No IP"}), 400
    return jsonify(run_cmd(f"sudo ufw delete allow from {shlex.quote(ip)} to any port 27017 proto tcp", t=10))

@app.route('/backup', methods=['GET'])
def backup():
    f = os.path.join(UPLOAD_FOLDER, f"backup_{int(time.time())}.gz")
    cmd = f"docker exec my-mongo-db mongodump --username=root --password={shlex.quote(DB_PASSWORD)} --authenticationDatabase=admin --archive --gzip"
    try:
        with open(f, 'wb') as fh: subprocess.run(cmd, shell=True, stdout=fh, check=True, timeout=120)
        return send_file(f, as_attachment=True, download_name="mongo_backup.gz", mimetype="application/gzip")
    except Exception as e: return f"Error: {e}", 500
    finally:
        # FIXED SYNTAX HERE
        if os.path.exists(f):
            time.sleep(1)
            try: os.remove(f)
            except: pass

@app.route('/restore', methods=['POST'])
def restore():
    if subprocess.run("docker inspect -f '{{.State.Running}}' my-mongo-db", shell=True, capture_output=True, text=True).stdout.strip() != 'true':
        return jsonify({"success": False, "error": "DB not running"}), 400
    file = request.files.get('backupFile')
    if not file: return jsonify({"success": False, "error": "No file"}), 400
    path = os.path.join(UPLOAD_FOLDER, secure_filename(file.filename))
    file.save(path)
    try:
        if not run_cmd(f"docker cp {path} my-mongo-db:/tmp/restore.gz", t=60)["success"]: return jsonify({"error": "Copy failed"}), 500
        return jsonify(run_cmd(f"docker exec my-mongo-db mongorestore --username=root --password={shlex.quote(DB_PASSWORD)} --authenticationDatabase=admin --archive=/tmp/restore.gz --gzip --drop --noIndexRestore --nsExclude=admin.*", t=300))
    finally:
        if os.path.exists(path): os.remove(path)
        run_cmd("docker exec my-mongo-db rm -f /tmp/restore.gz", t=10)

@app.route('/logs', methods=['GET'])
def logs(): return jsonify(run_cmd("docker compose logs --tail=100", t=10))

@app.route('/status', methods=['GET'])
def status():
    try: return jsonify({"success": True, "status": subprocess.run("docker inspect --format '{{.State.Status}}' my-mongo-db", shell=True, capture_output=True, text=True, timeout=5).stdout.strip()})
    except: return jsonify({"success": True, "status": "not_deployed"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
