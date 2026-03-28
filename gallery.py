"""Photo Gallery v3 — login, dedup, tagging, CLIP auto-tag"""
from pathlib import Path
import hashlib, os, threading, uuid, struct
from functools import wraps
from flask import (Flask, render_template, jsonify, request,
                   send_file, abort, session, redirect, url_for)

IMAGES_ROOT       = Path("/mnt/c/photo/Images")
ALLOWED_ROOT      = "/mnt/c/photo/"
THUMB_DIR         = Path("/tmp/gi_thumbs")
THUMB_SIZE        = (300, 300)
PAGE_SIZE         = 60
AUTOTAG_THRESHOLD = 0.72

DB_CFG = dict(host="localhost", user="root", password="zerocall",
              database="photo_manager", autocommit=False, connection_timeout=10)

app = Flask(__name__)
app.secret_key = os.urandom(32)

# ── CLIP global (lazy-loaded) ─────────────────────────────────────────────────
_clip      = {"model": None, "proc": None, "torch": None, "lock": threading.Lock()}
_emb_cache = {}   # file_id -> [512 floats]
_jobs      = {}   # job_id -> {status, progress, total, tagged}

# ── DB ────────────────────────────────────────────────────────────────────────
def get_db():
    import mysql.connector
    return mysql.connector.connect(**DB_CFG)

# ── Auth ──────────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

def check_credentials(username, password):
    ph  = hashlib.sha256(password.encode()).hexdigest()
    db  = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT id, username, is_admin FROM users "
                "WHERE username=%s AND password_hash=%s", (username, ph))
    row = cur.fetchone(); cur.close(); db.close()
    return row

# ── Path security ─────────────────────────────────────────────────────────────
def safe_path(p):
    resolved = Path(p).resolve()
    if not str(resolved).startswith(ALLOWED_ROOT): abort(403)
    return resolved

# ── Thumbnails ────────────────────────────────────────────────────────────────
def make_thumb(src, dest):
    from PIL import Image
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img.thumbnail(THUMB_SIZE, Image.LANCZOS)
        img.convert("RGB").save(dest, "JPEG", quality=82, optimize=True)

# ── CLIP helpers ──────────────────────────────────────────────────────────────
def load_clip():
    with _clip["lock"]:
        if _clip["model"] is None:
            import torch
            from transformers import CLIPModel, CLIPProcessor
            _clip["model"] = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
            _clip["proc"]  = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
            _clip["model"].eval()
            _clip["torch"] = torch
    return _clip["model"], _clip["proc"], _clip["torch"]

def embed_paths(paths):
    from PIL import Image
    model, proc, torch = load_clip()
    imgs, valid = [], []
    for i, p in enumerate(paths):
        try:
            imgs.append(Image.open(p).convert("RGB"))
            valid.append(i)
        except Exception:
            pass
    if not imgs:
        return [None] * len(paths)
    with torch.no_grad():
        enc  = proc(images=imgs, return_tensors="pt", padding=True)
        vis  = model.vision_model(pixel_values=enc["pixel_values"])
        feat = model.visual_projection(vis.pooler_output)
        feat = feat / feat.norm(dim=-1, keepdim=True)
    vecs = feat.tolist()
    out  = [None] * len(paths)
    for li, oi in enumerate(valid):
        out[oi] = vecs[li]
    return out

def cosine(a, b):
    return sum(x * y for x, y in zip(a, b))   # both pre-normalized

# ── Tag DB helpers ────────────────────────────────────────────────────────────
def get_or_create_tag(cur, name):
    cur.execute("INSERT IGNORE INTO tags (name) VALUES (%s)", (name,))
    cur.execute("SELECT id FROM tags WHERE name=%s", (name,))
    return cur.fetchone()[0]

# ── Category query helper ─────────────────────────────────────────────────────
CAT_FILTER = ("(f.category_id = (SELECT id FROM categories WHERE name=%s) "
              "OR (f.category_id IS NULL AND f.category = %s))")

# ───────────────────────────────────────────────────────────────────────────────
# ROUTES
# ───────────────────────────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        if not u or not p:
            error = "Username and password are required."
        else:
            user = check_credentials(u, p)
            if user:
                session["user"]     = user["username"]
                session["is_admin"] = bool(user["is_admin"])
                nxt = request.args.get("next", "/")
                if not nxt.startswith("/"): nxt = "/"
                return redirect(nxt)
            else:
                error = "Invalid username or password."
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    db = get_db(); cur = db.cursor()
    cur.execute(
        "SELECT c.name, COUNT(f.id) n "
        "FROM categories c "
        "LEFT JOIN files f ON "
        "  (f.category_id = c.id OR (f.category_id IS NULL AND f.category = c.name)) "
        "  AND f.file_type='image' "
        "GROUP BY c.id, c.name ORDER BY n DESC"
    )
    cats = [{"name": r[0], "count": r[1]} for r in cur.fetchall()]
    cur.close(); db.close()
    return render_template("index.html", categories=cats,
                           username=session.get("user"),
                           is_admin=session.get("is_admin"))

@app.route("/api/files/<category>")
@login_required
def api_files(category):
    page = max(0, int(request.args.get("page", 0)))
    db   = get_db(); cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT f.id, f.name, f.path, f.hash "
        "FROM files f "
        "WHERE " + CAT_FILTER + " AND f.file_type='image' "
        "ORDER BY f.name LIMIT %s OFFSET %s",
        (category, category, PAGE_SIZE, page * PAGE_SIZE)
    )
    rows = cur.fetchall()
    if rows:
        ids  = [r["id"] for r in rows]
        fmt  = ",".join(["%s"] * len(ids))
        tmap = {}
        tcur = db.cursor()   # plain cursor - returns tuples
        tcur.execute(
            "SELECT ft.file_id, t.name, ft.confidence, ft.is_manual "
            "FROM file_tags ft JOIN tags t ON ft.tag_id = t.id "
            "WHERE ft.file_id IN (" + fmt + ")", ids
        )
        for fid, tname, conf, manual in tcur.fetchall():
            tmap.setdefault(fid, []).append(
                {"name": tname, "confidence": round(float(conf), 2), "manual": bool(manual)}
            )
        tcur.close()
        for r in rows:
            r["tags"] = tmap.get(r["id"], [])
    cur.close(); db.close()
    return jsonify(rows)

@app.route("/api/dedup/<category>", methods=["POST"])
@login_required
def dedup_category(category):
    import re
    db  = get_db(); cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT f.id, f.hash, f.path, f.name FROM files f "
        "WHERE " + CAT_FILTER + " AND f.file_type='image' ORDER BY f.name",
        (category, category)
    )
    rows = cur.fetchall()
    groups = {}
    for r in rows:
        groups.setdefault(r["hash"], []).append(r)
    deleted = []
    for h, group in groups.items():
        if len(group) < 2:
            continue
        def score(r):
            m = re.findall(r"\((\d+)\)", Path(r["name"]).stem)
            s = len(r["name"])
            if m: s += 10000 if max(int(x) for x in m) >= 2 else 500
            return s
        group.sort(key=score)
        for dup in group[1:]:
            try:
                fp = Path(dup["path"])
                if fp.exists(): fp.unlink()
                c2 = db.cursor()
                c2.execute("DELETE FROM file_tags WHERE file_id=%s", (dup["id"],))
                c2.execute("DELETE FROM files WHERE id=%s", (dup["id"],))
                c2.close()
                deleted.append(dup["name"])
            except Exception:
                pass
    db.commit(); cur.close(); db.close()
    return jsonify({"deleted": len(deleted), "sample": deleted[:10]})


@app.route("/api/file/<hash_>/tags")
@login_required
def file_tags_by_hash(hash_):
    db  = get_db(); cur = db.cursor()
    cur.execute("SELECT id FROM files WHERE hash=%s", (hash_,))
    row = cur.fetchone()
    if not row:
        cur.close(); db.close()
        return jsonify([])
    cur.execute(
        "SELECT t.name, ft.confidence, ft.is_manual "
        "FROM file_tags ft JOIN tags t ON ft.tag_id = t.id "
        "WHERE ft.file_id = %s ORDER BY ft.is_manual DESC, t.name", (row[0],)
    )
    tags = [{"name": r[0], "confidence": round(float(r[1]), 2), "manual": bool(r[2])}
            for r in cur.fetchall()]
    cur.close(); db.close()
    return jsonify(tags)

@app.route("/api/tags")
@login_required
def all_tags():
    db = get_db(); cur = db.cursor()
    cur.execute("SELECT id, name FROM tags ORDER BY name")
    tags = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    cur.close(); db.close()
    return jsonify(tags)

@app.route("/api/tag", methods=["POST"])
@login_required
def add_tag():
    data  = request.get_json(force=True) or {}
    hash_ = data.get("hash", "").strip()
    name  = data.get("tag", "").strip()
    if not hash_ or not name: abort(400)
    db  = get_db(); cur = db.cursor()
    cur.execute("SELECT id FROM files WHERE hash=%s", (hash_,))
    row = cur.fetchone()
    if not row: abort(404)
    tag_id = get_or_create_tag(cur, name)
    cur.execute(
        "INSERT IGNORE INTO file_tags (file_id, tag_id, confidence, is_manual) "
        "VALUES (%s, %s, 1.0, 1)", (row[0], tag_id)
    )
    db.commit(); cur.close(); db.close()
    return jsonify({"ok": True})

@app.route("/api/tag", methods=["DELETE"])
@login_required
def remove_tag():
    data  = request.get_json(force=True) or {}
    hash_ = data.get("hash", "").strip()
    name  = data.get("tag", "").strip()
    if not hash_ or not name: abort(400)
    db = get_db(); cur = db.cursor()
    cur.execute(
        "DELETE ft FROM file_tags ft "
        "JOIN tags t ON ft.tag_id = t.id "
        "JOIN files f ON ft.file_id = f.id "
        "WHERE f.hash=%s AND t.name=%s", (hash_, name)
    )
    db.commit(); cur.close(); db.close()
    return jsonify({"ok": True})

@app.route("/api/autotag", methods=["POST"])
@login_required
def start_autotag():
    data     = request.get_json(force=True) or {}
    hash_    = data.get("hash", "").strip()
    tag_name = data.get("tag", "").strip()
    category = data.get("category", "").strip()
    if not hash_ or not tag_name or not category: abort(400)
    job_id = str(uuid.uuid4())[:8]
    _jobs[job_id] = {"status": "starting", "progress": 0, "total": 0, "tagged": 0}
    threading.Thread(target=_autotag_worker,
                     args=(job_id, hash_, tag_name, category),
                     daemon=True).start()
    return jsonify({"job_id": job_id})

def _autotag_worker(job_id, seed_hash, tag_name, category):
    try:
        db  = get_db(); cur = db.cursor(dictionary=True)
        cur.execute("SELECT id, path FROM files WHERE hash=%s", (seed_hash,))
        seed = cur.fetchone()
        if not seed:
            _jobs[job_id]["status"] = "error: seed photo not found"; return
        seed_id = seed["id"]
        _jobs[job_id]["status"] = "loading photos in category..."
        cur.execute(
            "SELECT f.id, f.path FROM files f "
            "WHERE " + CAT_FILTER + " AND f.file_type='image'",
            (category, category)
        )
        all_files = cur.fetchall()
        total = len(all_files)
        _jobs[job_id]["total"] = total
        _jobs[job_id]["status"] = f"computing embeddings (0/{total})..."
        BATCH = 48
        for i in range(0, len(all_files), BATCH):
            batch  = all_files[i:i + BATCH]
            needed = [r for r in batch if r["id"] not in _emb_cache]
            if needed:
                vecs = embed_paths([Path(r["path"]) for r in needed])
                for r, v in zip(needed, vecs):
                    if v: _emb_cache[r["id"]] = v
            _jobs[job_id]["progress"] = min(i + BATCH, total)
            _jobs[job_id]["status"]   = f"computing embeddings ({_jobs[job_id]['progress']}/{total})..."
        seed_vec = _emb_cache.get(seed_id)
        if seed_vec is None:
            vecs = embed_paths([Path(seed["path"])])
            seed_vec = vecs[0]
        if seed_vec is None:
            _jobs[job_id]["status"] = "error: could not embed seed photo"; return
        _emb_cache[seed_id] = seed_vec
        _jobs[job_id]["status"] = "finding similar photos..."
        similar = []
        for r in all_files:
            if r["id"] == seed_id: continue
            v = _emb_cache.get(r["id"])
            if v and cosine(seed_vec, v) >= AUTOTAG_THRESHOLD:
                similar.append(r["id"])
        tag_cur = db.cursor()
        tag_id  = get_or_create_tag(tag_cur, tag_name)
        tag_cur.execute(
            "INSERT IGNORE INTO file_tags (file_id,tag_id,confidence,is_manual) "
            "VALUES (%s,%s,1.0,1)", (seed_id, tag_id)
        )
        for fid in similar:
            tag_cur.execute(
                "INSERT IGNORE INTO file_tags (file_id,tag_id,confidence,is_manual) "
                "VALUES (%s,%s,0.9,0)", (fid, tag_id)
            )
        db.commit(); tag_cur.close(); cur.close(); db.close()
        _jobs[job_id].update({"status": "done", "tagged": len(similar), "progress": total})
    except Exception as e:
        _jobs[job_id]["status"] = f"error: {str(e)[:120]}"

@app.route("/api/autotag/status/<job_id>")
@login_required
def autotag_status(job_id):
    return jsonify(_jobs.get(job_id, {"status": "not found"}))

@app.route("/img")
@login_required
def serve_img():
    path = safe_path(request.args.get("p", ""))
    if not path.exists(): abort(404)
    return send_file(path)

@app.route("/thumb")
@login_required
def serve_thumb():
    path = safe_path(request.args.get("p", ""))
    if not path.exists(): abort(404)
    key  = hashlib.md5(str(path).encode()).hexdigest() + ".jpg"
    dest = THUMB_DIR / key
    if not dest.exists():
        try: make_thumb(path, dest)
        except Exception: return send_file(path)
    return send_file(dest)

@app.route("/delete", methods=["POST"])
@login_required
def delete_files():
    data  = request.get_json(force=True) or {}
    paths = data.get("paths", [])
    if not isinstance(paths, list): abort(400)
    safe_paths = []
    for p in paths:
        try: safe_paths.append(str(safe_path(p)))
        except Exception: pass
    deleted, errors = [], []
    db  = get_db(); cur = db.cursor()
    for p in safe_paths:
        try:
            fp = Path(p)
            if fp.exists(): fp.unlink()
            cur.execute("SELECT id FROM files WHERE path=%s", (p,))
            row = cur.fetchone()
            if row:
                cur.execute("DELETE FROM file_tags WHERE file_id=%s", (row[0],))
                cur.execute("DELETE FROM files WHERE id=%s", (row[0],))
            deleted.append(p)
        except Exception as e:
            errors.append(str(e))
    db.commit(); cur.close(); db.close()
    return jsonify({"deleted": len(deleted), "errors": errors})

if __name__ == "__main__":
    THUMB_DIR.mkdir(parents=True, exist_ok=True)
    print("Gallery v3 running \u2192 http://localhost:5050")
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
