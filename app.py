from flask import Flask, jsonify, request, abort, send_from_directory
from flask_cors import CORS
import sqlite3, uuid, os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR)
CORS(app)
DB_PATH = os.path.join(BASE_DIR, "notex.db")
FRONTEND_FILE = "frontend.html"

@app.route("/")
def index():
    candidates = [FRONTEND_FILE, "index.html", "notex.html", "NoteX.html"]
    for name in candidates:
        if os.path.exists(os.path.join(BASE_DIR, name)):
            return send_from_directory(BASE_DIR, name)
    return ("<h2 style='font-family:sans-serif;padding:40px'>frontend.html not found</h2>"
            "<p style='font-family:sans-serif;padding:0 40px'>Put frontend.html in the same folder as backend.py</p>"), 404

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.execute("""CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT 'Untitled Note',
        content TEXT NOT NULL DEFAULT '', folder TEXT NOT NULL DEFAULT 'General',
        pinned INTEGER NOT NULL DEFAULT 0, in_trash INTEGER NOT NULL DEFAULT 0,
        created TEXT NOT NULL, updated TEXT NOT NULL)""")
    conn.commit()
    conn.close()

def _now():
    return datetime.utcnow().isoformat() + "Z"

def row_to_dict(row):
    d = dict(row)
    d["pinned"] = bool(d["pinned"])
    d["in_trash"] = bool(d["in_trash"])
    return d

@app.route("/api/notes", methods=["GET"])
def list_notes():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM notes WHERE in_trash=0 ORDER BY pinned DESC, updated DESC").fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])

@app.route("/api/notes", methods=["POST"])
def create_note():
    data = request.get_json(silent=True) or {}
    now = _now()
    note = {"id": str(uuid.uuid4()), "title": data.get("title", "").strip() or "Untitled Note",
            "content": data.get("content", ""), "folder": data.get("folder", "General"),
            "pinned": int(bool(data.get("pinned", False))), "in_trash": 0, "created": now, "updated": now}
    conn = get_conn()
    conn.execute("INSERT INTO notes (id,title,content,folder,pinned,in_trash,created,updated) VALUES (:id,:title,:content,:folder,:pinned,:in_trash,:created,:updated)", note)
    conn.commit()
    conn.close()
    note["pinned"] = bool(note["pinned"])
    note["in_trash"] = False
    return jsonify(note), 201

@app.route("/api/notes/<note_id>", methods=["GET"])
def get_note(note_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone()
    conn.close()
    if not row: abort(404, description="Note not found")
    return jsonify(row_to_dict(row))

@app.route("/api/notes/<note_id>", methods=["PUT"])
def update_note(note_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM notes WHERE id=? AND in_trash=0", (note_id,)).fetchone()
    if not row: conn.close(); abort(404)
    data = request.get_json(silent=True) or {}
    current = row_to_dict(row)
    title = data.get("title", current["title"]).strip() or "Untitled Note"
    content = data.get("content", current["content"])
    folder = data.get("folder", current["folder"])
    pinned = int(bool(data.get("pinned", current["pinned"])))
    conn.execute("UPDATE notes SET title=?,content=?,folder=?,pinned=?,updated=? WHERE id=?", (title, content, folder, pinned, _now(), note_id))
    conn.commit()
    updated = row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone())
    conn.close()
    return jsonify(updated)

@app.route("/api/notes/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM notes WHERE id=? AND in_trash=0", (note_id,)).fetchone()
    if not row: conn.close(); abort(404)
    conn.execute("UPDATE notes SET in_trash=1, updated=? WHERE id=?", (_now(), note_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Moved to trash", "id": note_id})

@app.route("/api/notes/<note_id>/pin", methods=["PATCH"])
def toggle_pin(note_id):
    conn = get_conn()
    row = conn.execute("SELECT pinned FROM notes WHERE id=? AND in_trash=0", (note_id,)).fetchone()
    if not row: conn.close(); abort(404)
    new_pin = 0 if row["pinned"] else 1
    conn.execute("UPDATE notes SET pinned=?, updated=? WHERE id=?", (new_pin, _now(), note_id))
    conn.commit()
    updated = row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone())
    conn.close()
    return jsonify(updated)

@app.route("/api/trash", methods=["GET"])
def list_trash():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM notes WHERE in_trash=1 ORDER BY updated DESC").fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])

@app.route("/api/trash/<note_id>/restore", methods=["POST"])
def restore_note(note_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM notes WHERE id=? AND in_trash=1", (note_id,)).fetchone()
    if not row: conn.close(); abort(404)
    conn.execute("UPDATE notes SET in_trash=0, updated=? WHERE id=?", (_now(), note_id))
    conn.commit()
    restored = row_to_dict(conn.execute("SELECT * FROM notes WHERE id=?", (note_id,)).fetchone())
    conn.close()
    return jsonify(restored)

@app.route("/api/trash/<note_id>", methods=["DELETE"])
def permanent_delete(note_id):
    conn = get_conn()
    row = conn.execute("SELECT id FROM notes WHERE id=? AND in_trash=1", (note_id,)).fetchone()
    if not row: conn.close(); abort(404)
    conn.execute("DELETE FROM notes WHERE id=?", (note_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Permanently deleted", "id": note_id})

@app.route("/api/stats", methods=["GET"])
def stats():
    conn = get_conn()
    folder_rows = conn.execute("SELECT folder, COUNT(*) as count FROM notes WHERE in_trash=0 GROUP BY folder").fetchall()
    total = conn.execute("SELECT COUNT(*) FROM notes WHERE in_trash=0").fetchone()[0]
    pinned = conn.execute("SELECT COUNT(*) FROM notes WHERE in_trash=0 AND pinned=1").fetchone()[0]
    trash_count = conn.execute("SELECT COUNT(*) FROM notes WHERE in_trash=1").fetchone()[0]
    conn.close()
    return jsonify({"total": total, "pinned": pinned, "trash": trash_count,
                    "folders": {r["folder"]: r["count"] for r in folder_rows}})

@app.route("/api/search", methods=["GET"])
def search():
    q = request.args.get("q", "").strip()
    if not q: return jsonify([])
    like = f"%{q}%"
    conn = get_conn()
    rows = conn.execute("SELECT * FROM notes WHERE in_trash=0 AND (title LIKE ? OR content LIKE ?) ORDER BY pinned DESC, updated DESC", (like, like)).fetchall()
    conn.close()
    return jsonify([row_to_dict(r) for r in rows])

@app.errorhandler(404)
def not_found(e): return jsonify({"error": str(e)}), 404

@app.errorhandler(400)
def bad_request(e): return jsonify({"error": str(e)}), 400

if __name__ == "__main__":
    init_db()
    print("\nNoteX running at http://localhost:5000\n")
    app.run(debug=True, port=5000)