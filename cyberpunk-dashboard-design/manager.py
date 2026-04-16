import sys
import subprocess
import time
import requests
from flask import Flask, jsonify
from flask_cors import CORS
import atexit

app = Flask(__name__)
CORS(app)

current_process = None
current_mode = None

def cleanup():
    """Ensure we don't leave zombie processes when the manager is closed."""
    global current_process
    if current_process:
        print("\nShutting down backend process...")
        try:
            current_process.terminate()
            current_process.wait(timeout=3)
        except Exception as e:
            print(f"Error during cleanup: {e}")

atexit.register(cleanup)

def wait_for_port_5000(timeout=15):
    """Wait until the backend on port 5000 is fully responsive."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Check a simple endpoint to verify Flask is running
            response = requests.get('http://127.0.0.1:5000/api/data', timeout=1)
            # as long as we get a response, it means the server is online
            print("Backend is fully up and responding on port 5000!")
            return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    return False

def start_backend(mode):
    global current_process, current_mode
    if mode == current_mode and current_process and current_process.poll() is None:
        print(f"{mode.capitalize()} mode is already running.")
        return True

    # 1. Fetch current IP from port 5000 before killing the backend
    saved_ip = None
    if current_process and current_process.poll() is None:
        try:
            r = requests.get('http://127.0.0.1:5000/api/selected_ip', timeout=1)
            if r.status_code == 200:
                saved_ip = r.json().get('selected_ip')
                print(f"Preserving selected IP: {saved_ip}")
        except Exception:
            pass

    print(f"Switching to {mode.capitalize()} mode...")
    if current_process:
        print("Terminating current backend...")
        current_process.terminate()
        current_process.wait() # Wait for process to fully exit
        time.sleep(1) # Give OS a moment to free port 5000
        
    script_path = "app.py" 
    script_dir = "scripts" if mode == "rifle" else "scripts_pistol"
    
    print(f"Starting {script_path} in {script_dir}...")
    current_process = subprocess.Popen([sys.executable, script_path], cwd=script_dir)
    current_mode = mode
    
    # Wait for the server to come online before returning success
    if wait_for_port_5000():
        # 2. Restore the IP to the new backend
        if saved_ip:
            try:
                requests.post('http://127.0.0.1:5000/api/select_ip_direct', json={"ip": saved_ip}, timeout=2)
                print(f"Restored selected IP to {saved_ip}")
            except Exception as e:
                print(f"Failed to restore IP: {e}")
        return True
    else:
        print("Warning: Backend took too long to start.")
        return False

@app.route('/api/rifle', methods=['GET', 'POST'])
def rifle_mode():
    success = start_backend("rifle")
    if success:
        return jsonify({"status": "ok", "mode": "rifle"})
    return jsonify({"status": "error", "message": "Failed to start rifle backend"}), 500

@app.route('/api/pistol', methods=['GET', 'POST'])
def pistol_mode():
    success = start_backend("pistol")
    if success:
        return jsonify({"status": "ok", "mode": "pistol"})
    return jsonify({"status": "error", "message": "Failed to start pistol backend"}), 500

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({"status": "ok", "mode": current_mode})

if __name__ == '__main__':
    print("====================================")
    print(" LAKSHYA DASHBOARD MANAGER HOST")
    print(" Routing modes between Rifle/Pistol")
    print("====================================")
    
    # Start the default backend
    start_backend("rifle")
    
    # Run the manager API on port 5005
    app.run(port=5005, host='0.0.0.0', debug=False)
