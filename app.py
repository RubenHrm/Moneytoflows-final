import os
from datetime import datetime
from flask import Flask, g, render_template, request, redirect, url_for, flash, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import secrets
import sqlite3

# Config
DATABASE = os.getenv("DATABASE", "moneytoflows.db")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "herolemiayoukou@gmail.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "Moneytoflows@gmail.com")
ACHAT_LINK = os.getenv("ACHAT_LINK", "https://sgzxfbtn.mychariow.shop/prd_8ind83")
PRODUCT_NAME = os.getenv("PRODUCT_NAME", "MoneyToFlows")
SEUIL_RECOMPENSE = int(os.getenv("SEUIL_RECOMPENSE", "5"))
REWARD_PER_REF = float(os.getenv("REWARD_PER_REF", "1700.0"))
WU_MIN = int(os.getenv("WU_MIN", "15000"))
MOBILE_MIN = int(os.getenv("MOBILE_MIN", "5000"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", secrets.token_urlsafe(32))

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        need_init = not os.path.exists(DATABASE)
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        db.row_factory = sqlite3.Row
        if need_init:
            init_db()
    return db

def init_db():
    db = sqlite3.connect(DATABASE)
    c = db.cursor()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        email TEXT UNIQUE,
        password TEXT,
        country TEXT,
        mobile TEXT,
        provider TEXT,
        ref_code TEXT UNIQUE,
        referrer_code TEXT,
        purchases INTEGER DEFAULT 0,
        created_at TEXT,
        is_admin INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS referrals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        referrer_code TEXT,
        referred_user_id INTEGER,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reference TEXT,
        validated INTEGER DEFAULT 0,
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS withdrawals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        provider TEXT,
        mobile_number TEXT,
        wu_fullname TEXT,
        wu_country TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        email TEXT,
        subject TEXT,
        message TEXT,
        status TEXT DEFAULT 'open',
        created_at TEXT
    );
    """)
    try:
        hashed = generate_password_hash(ADMIN_PASSWORD)
        c.execute("INSERT OR IGNORE INTO users (username,email,password,is_admin,created_at) VALUES (?, ?, ?, 1, ?)",
                  (ADMIN_EMAIL.split('@')[0], ADMIN_EMAIL, hashed, datetime.utcnow().isoformat()))
    except Exception:
        pass
    db.commit()
    db.close()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def generate_ref_code(user_id: int):
    import secrets
    return f"U{user_id:06d}{secrets.token_hex(2)}"

def query_db(query, args=(), one=False):
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    return (rv[0] if rv else None) if one else rv

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('is_admin'):
            flash('Accès administrateur requis', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

def commission_rate(buyers_count:int):
    if buyers_count >= 100:
        return 0.40
    if buyers_count >= 50:
        return 0.30
    return 0.20

@app.route('/')
def index():
    return render_template('index.html', product=PRODUCT_NAME, achat_link=ACHAT_LINK, support_email=SUPPORT_EMAIL)

@app.route('/register', methods=['GET','POST'])
def register():
    ref = request.args.get('ref') or request.form.get('referrer_code')
    if request.method == 'POST':
        username = request.form['username'].strip()
        email = request.form.get('email').strip()
        password = request.form['password']
        country = request.form.get('country')
        mobile = request.form.get('mobile')
        provider = request.form.get('provider')
        db = get_db()
        try:
            db.execute("INSERT INTO users (username,email,password,country,mobile,provider,referrer_code,created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (username, email, generate_password_hash(password), country, mobile, provider, ref or None, datetime.utcnow().isoformat()))
            db.commit()
            row = query_db('SELECT id FROM users WHERE email=?', (email,), one=True)
            uid = row['id']
            ref_code = generate_ref_code(uid)
            db.execute('UPDATE users SET ref_code=? WHERE id=?', (ref_code, uid))
            db.commit()
            if ref:
                db.execute('INSERT INTO referrals (referrer_code, referred_user_id, created_at) VALUES (?, ?, ?)',
                           (ref, uid, datetime.utcnow().isoformat()))
                db.commit()
            flash('Inscription réussie, connectez-vous', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash('Erreur lors de l\'inscription (email ou username déjà utilisé)', 'danger')
    return render_template('register.html', ref=ref)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip()
        pw = request.form['password']
        u = query_db('SELECT * FROM users WHERE email=?', (email,), one=True)
        if u and check_password_hash(u['password'], pw):
            session['user_id'] = u['id']
            session['username'] = u['username']
            session['is_admin'] = bool(u['is_admin'])
            flash('Connecté', 'success')
            return redirect(url_for('dashboard'))
        flash('Identifiants invalides', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    uid = session['user_id']
    user = query_db('SELECT * FROM users WHERE id=?', (uid,), one=True)
    code = user['ref_code']
    total_referrals = query_db('SELECT COUNT(*) as c FROM referrals WHERE referrer_code=?', (code,), one=True)['c']
    buyers_row = query_db("""SELECT COUNT(*) as c FROM referrals r
                           JOIN users u ON r.referred_user_id = u.id
                           WHERE r.referrer_code=? AND u.purchases>0""", (code,), one=True)
    buyers = buyers_row['c'] if buyers_row else 0
    rate = commission_rate(buyers)
    amount = int(buyers * REWARD_PER_REF * rate)
    ref_link = url_for('register', _external=True) + f'?ref={code}'
    return render_template('dashboard.html', user=user, total_referrals=total_referrals, buyers=buyers, amount=amount, ref_link=ref_link, threshold=SEUIL_RECOMPENSE, rate=rate)

@app.route('/confirm_purchase', methods=['GET','POST'])
def confirm_purchase():
    if request.method == 'POST':
        reference = request.form['reference'].strip()
        uid = session['user_id']
        db = get_db()
        db.execute('INSERT INTO purchases (user_id, reference, validated, created_at) VALUES (?, ?, 0, ?)', (uid, reference, 0, datetime.utcnow().isoformat()))
        db.commit()
        flash('Référence envoyée à l\'admin pour validation', 'info')
        return redirect(url_for('dashboard'))
    return render_template('confirm_purchase.html')

@app.route('/withdraw', methods=['GET','POST'])
def withdraw():
    uid = session['user_id']
    user = query_db('SELECT * FROM users WHERE id=?', (uid,), one=True)
    code = user['ref_code']
    buyers_row = query_db("""SELECT COUNT(*) as c FROM referrals r
                           JOIN users u ON r.referred_user_id = u.id
                           WHERE r.referrer_code=? AND u.purchases>0""", (code,), one=True)
    buyers = buyers_row['c'] if buyers_row else 0
    if buyers < SEUIL_RECOMPENSE:
        flash(f'Vous avez {buyers} filleuls acheteurs. Il faut {SEUIL_RECOMPENSE} pour demander un retrait.', 'warning')
        return redirect(url_for('dashboard'))
    providers = ['MTN MoMo', 'Airtel Money', 'Orange Money', 'Moov Money', 'Wave', 'Western Union']
    if request.method == 'POST':
        provider = request.form['provider']
        mobile = request.form.get('mobile','').strip()
        wu_name = request.form.get('wu_name','').strip()
        wu_country = request.form.get('wu_country','').strip()
        if provider == 'Western Union':
            if not wu_name or not wu_country or len(mobile) < 6:
                flash('Veuillez fournir toutes les informations requises pour Western Union', 'danger')
                return redirect(url_for('withdraw'))
            db = get_db()
            db.execute('INSERT INTO withdrawals (user_id, provider, mobile_number, wu_fullname, wu_country, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                       (uid, provider, mobile, wu_name, wu_country, 'pending', datetime.utcnow().isoformat()))
            db.commit()
            flash('Demande de retrait WU envoyée à l\'admin', 'success')
            return redirect(url_for('dashboard'))
        else:
            if len(mobile) < 6:
                flash('Numéro mobile invalide', 'danger')
                return redirect(url_for('withdraw'))
            db = get_db()
            db.execute('INSERT INTO withdrawals (user_id, provider, mobile_number, status, created_at) VALUES (?, ?, ?, ?, ?)',
                       (uid, provider, mobile, 'pending', datetime.utcnow().isoformat()))
            db.commit()
            flash('Demande de retrait envoyée à l\'admin', 'success')
            return redirect(url_for('dashboard'))
    return render_template('withdraw.html', buyers=buyers, providers=providers, mobile_min=MOBILE_MIN, wu_min=WU_MIN)

@app.route('/admin')
@login_required
def admin_panel():
    users = query_db('SELECT * FROM users ORDER BY created_at DESC')
    pending = query_db('SELECT p.id, p.user_id, p.reference, p.validated, p.created_at, u.username FROM purchases p JOIN users u ON p.user_id=u.id WHERE p.validated=0')
    withdrawals = query_db('SELECT w.id, w.user_id, w.provider, w.mobile_number, w.wu_fullname, w.wu_country, w.status, w.created_at, u.username FROM withdrawals w JOIN users u ON w.user_id=u.id WHERE w.status!="validated"')
    tickets = query_db('SELECT t.id, t.user_id, t.email, t.subject, t.message, t.status, t.created_at, u.username FROM tickets t LEFT JOIN users u ON t.user_id=u.id ORDER BY t.created_at DESC')
    return render_template('admin.html', users=users, pending=pending, withdrawals=withdrawals, tickets=tickets, support_email=SUPPORT_EMAIL)

@app.route('/admin/validate_purchase/<int:pid>', methods=['POST'])
def validate_purchase(pid):
    db = get_db()
    db.execute('UPDATE purchases SET validated=1 WHERE id=?', (pid,))
    user_id = query_db('SELECT user_id FROM purchases WHERE id=?', (pid,), one=True)['user_id']
    db.execute('UPDATE users SET purchases = purchases + 1 WHERE id=?', (user_id,))
    db.commit()
    flash('Achat validé', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/validate_withdraw/<int:wid>', methods=['POST'])
def validate_withdraw(wid):
    db = get_db()
    db.execute('UPDATE withdrawals SET status="validated" WHERE id=?', (wid,))
    db.commit()
    flash('Retrait validé', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/refuse_withdraw/<int:wid>', methods=['POST'])
def refuse_withdraw(wid):
    db = get_db()
    db.execute('UPDATE withdrawals SET status="refused" WHERE id=?', (wid,))
    db.commit()
    flash('Retrait refusé', 'info')
    return redirect(url_for('admin_panel'))

@app.route('/support', methods=['GET','POST'])
def support():
    if request.method == 'POST':
        email = request.form.get('email') or session.get('username') or ''
        subject = request.form.get('subject','')
        message = request.form.get('message','')
        db = get_db()
        db.execute('INSERT INTO tickets (user_id, email, subject, message, status, created_at) VALUES (?, ?, ?, ?, "open", ?)',
                   (session.get('user_id'), email, subject, message, datetime.utcnow().isoformat()))
        db.commit()
        flash('Ticket envoyé. Notre équipe support vous répondra via email.', 'success')
        return redirect(url_for('index'))
    return render_template('support.html', support_email=SUPPORT_EMAIL)

@app.route('/init')
def init_route():
    init_db()
    return 'Database initialized and admin created (if not existed).'

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
