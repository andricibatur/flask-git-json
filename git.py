from flask import Flask, request, jsonify, send_file
import subprocess
import os
import json
import sys
from datetime import datetime
import traceback

app = Flask(__name__)

# ==========================================
# KONFIGURASI
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
DATA_FILE = os.path.join(DATA_DIR, 'data.json')
LOG_FILE = os.path.join(BASE_DIR, 'app.log')

# Buat folder data jika belum ada
os.makedirs(DATA_DIR, exist_ok=True)

# Inisialisasi file data jika belum ada
if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, 'w') as f:
        json.dump([], f, indent=2)

# ==========================================
# FUNGSI BANTUAN
# ==========================================

def log_message(msg):
    """Catat log ke file"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] {msg}\n"
    with open(LOG_FILE, 'a') as f:
        f.write(log_entry)
    print(log_entry.strip())

def read_data():
    """Baca data dari file JSON"""
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        log_message("⚠️ Error: File JSON corrupt, reset ke []")
        return []
    except Exception as e:
        log_message(f"❌ Error baca data: {str(e)}")
        return []

def write_data(data):
    """Tulis data ke file JSON"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log_message(f"❌ Error tulis data: {str(e)}")
        return False

def git_command(cmd, check=True):
    """Jalankan perintah Git dengan error handling"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=30
        )
        if check and result.returncode != 0:
            log_message(f"⚠️ Git error: {result.stderr}")
            return False, result.stderr
        return True, result.stdout
    except subprocess.TimeoutExpired:
        log_message("⏰ Git timeout")
        return False, "Timeout"
    except Exception as e:
        log_message(f"❌ Git exception: {str(e)}")
        return False, str(e)

def git_pull():
    """Pull dari remote"""
    log_message("📥 Pulling from Git...")
    success, output = git_command("git pull origin main")
    if not success:
        # Coba branch master
        success, output = git_command("git pull origin master")
    if success:
        log_message(f"✅ Pull success: {output[:100]}")
    else:
        log_message(f"❌ Pull failed: {output}")
    return success, output

def git_push(message):
    """Push ke remote dengan commit"""
    log_message(f"📤 Pushing to Git: {message}")
    
    # Add file
    success, output = git_command(f"git add {DATA_FILE}")
    if not success:
        return False, f"Add failed: {output}"
    
    # Commit
    success, output = git_command(f'git commit -m "{message}"')
    if not success and "nothing to commit" not in output:
        return False, f"Commit failed: {output}"
    
    # Push
    success, output = git_command("git push origin main")
    if not success:
        success, output = git_command("git push origin master")
    
    if success:
        log_message("✅ Push success")
    else:
        log_message(f"❌ Push failed: {output}")
    
    return success, output

def is_git_repo():
    """Cek apakah folder adalah git repo"""
    return os.path.exists(os.path.join(BASE_DIR, '.git'))

# ==========================================
# ENDPOINTS API
# ==========================================

@app.route('/', methods=['GET'])
def home():
    """Halaman utama dengan daftar endpoint"""
    return jsonify({
        'status': 'online',
        'service': 'Flask Git JSON API',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat(),
        'git_repo': is_git_repo(),
        'data_file': DATA_FILE,
        'data_count': len(read_data()),
        'endpoints': {
            'GET /': 'Info API',
            'GET /data': 'Lihat semua data',
            'GET /data/<index>': 'Lihat data spesifik (index)',
            'GET /data/search?q=<keyword>': 'Cari data',
            'POST /upload': 'Upload data baru',
            'POST /upload/batch': 'Upload banyak data',
            'PUT /update/<index>': 'Update data (index)',
            'DELETE /delete/<index>': 'Hapus data (index)',
            'DELETE /delete/all': 'Hapus semua data',
            'POST /sync/pull': 'Pull dari Git',
            'POST /sync/push': 'Push ke Git',
            'GET /export': 'Download file data.json',
            'GET /stats': 'Statistik data',
            'GET /logs': 'Lihat log (10 baris terakhir)'
        }
    })

@app.route('/data', methods=['GET'])
def get_all_data():
    """Get semua data (auto pull)"""
    if is_git_repo():
        git_pull()
    
    data = read_data()
    return jsonify({
        'status': 'success',
        'count': len(data),
        'data': data
    })

@app.route('/data/<int:index>', methods=['GET'])
def get_data_by_index(index):
    """Get data berdasarkan index"""
    if is_git_repo():
        git_pull()
    
    data = read_data()
    if 0 <= index < len(data):
        return jsonify({
            'status': 'success',
            'index': index,
            'data': data[index]
        })
    return jsonify({
        'status': 'error',
        'message': f'Data index {index} tidak ditemukan',
        'total_data': len(data)
    }), 404

@app.route('/data/search', methods=['GET'])
def search_data():
    """Search data berdasarkan keyword"""
    if is_git_repo():
        git_pull()
    
    keyword = request.args.get('q', '').lower()
    if not keyword:
        return jsonify({
            'status': 'error',
            'message': 'Parameter q diperlukan. Contoh: ?q=budi'
        }), 400
    
    data = read_data()
    results = []
    for i, item in enumerate(data):
        # Cari di semua field
        item_str = json.dumps(item).lower()
        if keyword in item_str:
            results.append({
                'index': i,
                'data': item
            })
    
    return jsonify({
        'status': 'success',
        'keyword': keyword,
        'count': len(results),
        'results': results
    })

@app.route('/upload', methods=['POST'])
def upload_data():
    """Upload satu data baru"""
    if not request.is_json:
        return jsonify({
            'status': 'error',
            'message': 'Content-Type harus application/json'
        }), 400
    
    new_data = request.get_json()
    
    # Validasi
    if not isinstance(new_data, dict):
        return jsonify({
            'status': 'error',
            'message': 'Data harus berupa object JSON'
        }), 400
    
    # Baca data existing
    data = read_data()
    
    # Tambahkan metadata
    new_data['_id'] = len(data)  # ID auto increment
    new_data['_created_at'] = datetime.now().isoformat()
    
    # Append
    data.append(new_data)
    
    # Simpan
    if not write_data(data):
        return jsonify({
            'status': 'error',
            'message': 'Gagal menyimpan data'
        }), 500
    
    # Commit ke Git
    if is_git_repo():
        nama = new_data.get('nama', new_data.get('name', f'data-{new_data["_id"]}'))
        success, msg = git_push(f"Tambah data: {nama}")
    else:
        success, msg = False, "Bukan git repository"
    
    return jsonify({
        'status': 'success',
        'message': 'Data berhasil diupload',
        'data': new_data,
        'git': {
            'success': success,
            'message': msg
        }
    }), 201

@app.route('/upload/batch', methods=['POST'])
def upload_batch():
    """Upload banyak data sekaligus"""
    if not request.is_json:
        return jsonify({
            'status': 'error',
            'message': 'Content-Type harus application/json'
        }), 400
    
    items = request.get_json()
    if not isinstance(items, list):
        return jsonify({
            'status': 'error',
            'message': 'Data harus berupa array JSON'
        }), 400
    
    data = read_data()
    start_id = len(data)
    
    for i, item in enumerate(items):
        item['_id'] = start_id + i
        item['_created_at'] = datetime.now().isoformat()
        data.append(item)
    
    if not write_data(data):
        return jsonify({
            'status': 'error',
            'message': 'Gagal menyimpan data'
        }), 500
    
    if is_git_repo():
        success, msg = git_push(f"Batch upload: {len(items)} items")
    else:
        success, msg = False, "Bukan git repository"
    
    return jsonify({
        'status': 'success',
        'message': f'{len(items)} data berhasil diupload',
        'count': len(items),
        'git': {
            'success': success,
            'message': msg
        }
    }), 201

@app.route('/update/<int:index>', methods=['PUT'])
def update_data(index):
    """Update data berdasarkan index"""
    if not request.is_json:
        return jsonify({
            'status': 'error',
            'message': 'Content-Type harus application/json'
        }), 400
    
    data = read_data()
    if not (0 <= index < len(data)):
        return jsonify({
            'status': 'error',
            'message': f'Data index {index} tidak ditemukan',
            'total_data': len(data)
        }), 404
    
    update_data = request.get_json()
    data[index].update(update_data)
    data[index]['_updated_at'] = datetime.now().isoformat()
    
    if not write_data(data):
        return jsonify({
            'status': 'error',
            'message': 'Gagal menyimpan data'
        }), 500
    
    if is_git_repo():
        nama = data[index].get('nama', data[index].get('name', f'index-{index}'))
        success, msg = git_push(f"Update data: {nama}")
    else:
        success, msg = False, "Bukan git repository"
    
    return jsonify({
        'status': 'success',
        'message': 'Data berhasil diupdate',
        'index': index,
        'data': data[index],
        'git': {
            'success': success,
            'message': msg
        }
    })

@app.route('/delete/<int:index>', methods=['DELETE'])
def delete_data(index):
    """Hapus data berdasarkan index"""
    data = read_data()
    if not (0 <= index < len(data)):
        return jsonify({
            'status': 'error',
            'message': f'Data index {index} tidak ditemukan',
            'total_data': len(data)
        }), 404
    
    deleted_item = data.pop(index)
    
    if not write_data(data):
        return jsonify({
            'status': 'error',
            'message': 'Gagal menyimpan data'
        }), 500
    
    if is_git_repo():
        nama = deleted_item.get('nama', deleted_item.get('name', f'index-{index}'))
        success, msg = git_push(f"Hapus data: {nama}")
    else:
        success, msg = False, "Bukan git repository"
    
    return jsonify({
        'status': 'success',
        'message': 'Data berhasil dihapus',
        'deleted': deleted_item,
        'remaining': len(data),
        'git': {
            'success': success,
            'message': msg
        }
    })

@app.route('/delete/all', methods=['DELETE'])
def delete_all():
    """Hapus semua data"""
    count = len(read_data())
    
    if not write_data([]):
        return jsonify({
            'status': 'error',
            'message': 'Gagal menghapus data'
        }), 500
    
    if is_git_repo():
        success, msg = git_push(f"Hapus semua data ({count} items)")
    else:
        success, msg = False, "Bukan git repository"
    
    return jsonify({
        'status': 'success',
        'message': f'Semua data ({count} items) berhasil dihapus',
        'deleted_count': count,
        'git': {
            'success': success,
            'message': msg
        }
    })

@app.route('/sync/pull', methods=['POST'])
def sync_pull():
    """Pull dari Git"""
    if not is_git_repo():
        return jsonify({
            'status': 'error',
            'message': 'Bukan git repository'
        }), 400
    
    success, output = git_pull()
    return jsonify({
        'status': 'success' if success else 'error',
        'message': output[:500] if output else 'Pull completed',
        'full_output': output if success else None
    })

@app.route('/sync/push', methods=['POST'])
def sync_push():
    """Push ke Git"""
    if not is_git_repo():
        return jsonify({
            'status': 'error',
            'message': 'Bukan git repository'
        }), 400
    
    success, output = git_push("Manual push via API")
    return jsonify({
        'status': 'success' if success else 'error',
        'message': output[:500] if output else 'Push completed',
        'full_output': output if success else None
    })

@app.route('/export', methods=['GET'])
def export_data():
    """Download file data.json"""
    if not os.path.exists(DATA_FILE):
        return jsonify({
            'status': 'error',
            'message': 'File data tidak ditemukan'
        }), 404
    
    return send_file(
        DATA_FILE,
        as_attachment=True,
        download_name='data.json',
        mimetype='application/json'
    )

@app.route('/stats', methods=['GET'])
def get_stats():
    """Statistik data"""
    data = read_data()
    
    stats = {
        'total_data': len(data),
        'fields': {},
        'created_at_range': None
    }
    
    if data:
        # Hitung field yang ada
        all_keys = set()
        for item in data:
            all_keys.update(item.keys())
        stats['fields'] = list(all_keys)
        
        # Range tanggal
        dates = [item.get('_created_at') for item in data if '_created_at' in item]
        if dates:
            dates.sort()
            stats['created_at_range'] = {
                'first': dates[0],
                'last': dates[-1]
            }
    
    return jsonify({
        'status': 'success',
        'stats': stats
    })

@app.route('/logs', methods=['GET'])
def get_logs():
    """Lihat log terakhir"""
    if not os.path.exists(LOG_FILE):
        return jsonify({
            'status': 'error',
            'message': 'Log file tidak ditemukan'
        }), 404
    
    try:
        with open(LOG_FILE, 'r') as f:
            lines = f.readlines()
            last_lines = lines[-10:] if len(lines) > 10 else lines
        return jsonify({
            'status': 'success',
            'logs': [line.strip() for line in last_lines]
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# ==========================================
# ERROR HANDLER
# ==========================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'status': 'error',
        'message': 'Endpoint tidak ditemukan',
        'available_endpoints': [
            '/', '/data', '/data/<index>', '/data/search',
            '/upload', '/upload/batch', '/update/<index>',
            '/delete/<index>', '/delete/all', '/sync/pull',
            '/sync/push', '/export', '/stats', '/logs'
        ]
    }), 404

@app.errorhandler(500)
def internal_error(error):
    log_message(f"❌ Internal error: {str(error)}")
    return jsonify({
        'status': 'error',
        'message': 'Terjadi kesalahan internal server'
    }), 500

# ==========================================
# MAIN
# ==========================================

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 Flask Git JSON API")
    print("=" * 50)
    print(f"📂 Data dir: {DATA_DIR}")
    print(f"📄 Data file: {DATA_FILE}")
    print(f"📝 Log file: {LOG_FILE}")
    print(f"🔗 Git repo: {'Yes' if is_git_repo() else 'No'}")
    print("=" * 50)
    print("🌐 Server running on: http://localhost:5000")
    print("📡 Press CTRL+C to stop")
    print("=" * 50)
    
    # Jalankan server
    app.run(host='0.0.0.0', port=5000, debug=False)
