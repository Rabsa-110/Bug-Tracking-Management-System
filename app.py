"""
app.py  -  Bug Tracking Management System
Configured for XAMPP MySQL (no password)
Run: python app.py
"""

from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, send_from_directory)
import mysql.connector
from mysql.connector import Error
from werkzeug.utils import secure_filename
from functools import wraps
import os, json
from datetime import datetime

# ── App Config ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = 'bugtracker-xampp-secret-2024'

UPLOAD_FOLDER      = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'txt','pdf','png','jpg','jpeg','gif','doc','docx','xlsx','zip','log'}
app.config['UPLOAD_FOLDER']      = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ── XAMPP MySQL Config ────────────────────────────────────────────────────────
DB_CONFIG = {
    'host':     'localhost',
    'user':     'root',
    'password': '',
    'database': 'bug_tracker',
    'charset':  'utf8mb4',
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrapped

def admin_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return wrapped

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

app.jinja_env.globals.update(now=datetime.now)

# ══════════════════════════════════════════════════════════════════════════════
# AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        conn = get_db(); cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM `User` WHERE email=%s", (email,))
        user = cur.fetchone(); conn.close()
        if user and user['password'] == password:
            session['user_id'] = user['user_id']
            session['name']    = user['name']
            session['role']    = user['role']
            flash(f"Welcome back, {user['name']}! 👋", 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    """Public registration — anyone can create an account."""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pwd   = request.form.get('password', '')
        pwd2  = request.form.get('confirm_password', '')
        role  = request.form.get('role', 'developer')

        # Validation
        errors = []
        if len(name) < 2:
            errors.append('Name must be at least 2 characters.')
        if '@' not in email or '.' not in email:
            errors.append('Please enter a valid email address.')
        if len(pwd) < 4:
            errors.append('Password must be at least 4 characters.')
        if pwd != pwd2:
            errors.append('Passwords do not match.')
        if role not in ('developer', 'tester', 'manager'):
            role = 'developer'  # admin cannot be self-assigned

        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            conn = get_db(); cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO `User` (name,email,password,role) VALUES (%s,%s,%s,%s)",
                    (name, email, pwd, role)
                )
                conn.commit()
                conn.close()
                flash('Account created successfully! Please sign in.', 'success')
                return redirect(url_for('login'))

            except Error:
                conn.close()
                flash('That email is already registered. Please login.', 'danger')
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/dashboard')
@login_required
def dashboard():
    conn = get_db(); cur = conn.cursor(dictionary=True)

    def scalar(sql, params=()):
        cur.execute(sql, params)
        r = cur.fetchone()
        return list(r.values())[0] if r else 0

    stats = {
        'total':       scalar("SELECT COUNT(*) FROM Issue"),
        'open':        scalar("SELECT COUNT(*) FROM Issue WHERE status='open'"),
        'in_progress': scalar("SELECT COUNT(*) FROM Issue WHERE status='in_progress'"),
        'resolved':    scalar("SELECT COUNT(*) FROM Issue WHERE status='resolved'"),
        'closed':      scalar("SELECT COUNT(*) FROM Issue WHERE status='closed'"),
        'projects':    scalar("SELECT COUNT(*) FROM Project"),
        'users':       scalar("SELECT COUNT(*) FROM `User`"),
    }

    # Recent issues with JOIN
    cur.execute("""
        SELECT i.issue_id, i.title, i.status, i.priority, i.created_at,
               p.project_name, u.name AS reporter, ua.name AS assignee
        FROM Issue i
        JOIN Project p ON i.project_id=p.project_id
        JOIN `User`  u ON i.reported_by=u.user_id
        LEFT JOIN `User` ua ON i.assigned_to=ua.user_id
        ORDER BY i.created_at DESC LIMIT 8
    """)
    recent = cur.fetchall()

    # My assigned issues
    cur.execute("""
        SELECT i.issue_id, i.title, i.status, i.priority, p.project_name
        FROM Issue i JOIN Project p ON i.project_id=p.project_id
        WHERE i.assigned_to=%s AND i.status NOT IN ('resolved','closed')
        ORDER BY FIELD(i.priority,'critical','high','medium','low') LIMIT 6
    """, (session['user_id'],))
    my_issues = cur.fetchall()

    # Charts data
    cur.execute("SELECT priority, COUNT(*) AS cnt FROM Issue GROUP BY priority")
    prio_data = {r['priority']: r['cnt'] for r in cur.fetchall()}

    cur.execute("SELECT status, COUNT(*) AS cnt FROM Issue GROUP BY status")
    status_data = {r['status']: r['cnt'] for r in cur.fetchall()}

    # Recent status changes
    cur.execute("""
        SELECT sh.changed_at, sh.old_status, sh.new_status,
               i.issue_id, i.title, u.name AS changed_by
        FROM Issue_Status_History sh
        JOIN Issue i ON sh.issue_id=i.issue_id
        JOIN `User` u ON sh.changed_by=u.user_id
        ORDER BY sh.changed_at DESC LIMIT 6
    """)
    recent_changes = cur.fetchall()
    conn.close()

    return render_template('dashboard.html',
        stats=stats, recent=recent, my_issues=my_issues,
        prio_data=json.dumps(prio_data),
        status_data=json.dumps(status_data),
        recent_changes=recent_changes)

# ══════════════════════════════════════════════════════════════════════════════
# PROJECTS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/projects')
@login_required
def projects():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT p.*,
               COUNT(i.issue_id)                      AS total,
               SUM(i.status='open')                   AS open_cnt,
               SUM(i.status='in_progress')            AS inprog_cnt,
               SUM(i.status IN ('resolved','closed')) AS done_cnt
        FROM Project p
        LEFT JOIN Issue i ON p.project_id=i.project_id
        GROUP BY p.project_id ORDER BY p.created_at DESC
    """)
    projects = cur.fetchall(); conn.close()
    return render_template('projects.html', projects=projects)


@app.route('/projects/new', methods=['GET', 'POST'])
@login_required
def new_project():
    if session['role'] not in ('admin', 'manager'):
        flash('Only admins and managers can create projects.', 'danger')
        return redirect(url_for('projects'))
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        desc = request.form.get('description', '').strip()
        if not name:
            flash('Project name is required.', 'danger')
        else:
            conn = get_db(); cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO Project (project_name,description) VALUES (%s,%s)",
                    (name, desc)
                )
                conn.commit(); conn.close()
                flash(f'Project "{name}" created!', 'success')
                return redirect(url_for('projects'))
            except Error:
                conn.close()
                flash('A project with that name already exists.', 'danger')
    return render_template('new_project.html')


@app.route('/projects/<int:pid>')
@login_required
def project_detail(pid):
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM Project WHERE project_id=%s", (pid,))
    project = cur.fetchone()
    if not project:
        flash('Project not found.', 'danger')
        return redirect(url_for('projects'))
    sf = request.args.get('status', '')
    pf = request.args.get('priority', '')
    q  = """SELECT i.*, u.name AS reporter, ua.name AS assignee
            FROM Issue i
            JOIN `User` u ON i.reported_by=u.user_id
            LEFT JOIN `User` ua ON i.assigned_to=ua.user_id
            WHERE i.project_id=%s"""
    params = [pid]
    if sf: q += " AND i.status=%s";   params.append(sf)
    if pf: q += " AND i.priority=%s"; params.append(pf)
    q += " ORDER BY FIELD(i.priority,'critical','high','medium','low'), i.created_at DESC"
    cur.execute(q, params)
    issues = cur.fetchall(); conn.close()
    return render_template('project_detail.html',
        project=project, issues=issues, sf=sf, pf=pf)


@app.route('/projects/<int:pid>/delete', methods=['POST'])
@login_required
def delete_project(pid):
    if session['role'] != 'admin':
        flash('Only admins can delete projects.', 'danger')
        return redirect(url_for('projects'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM Project WHERE project_id=%s", (pid,))
    conn.commit(); conn.close()
    flash('Project deleted.', 'info')
    return redirect(url_for('projects'))

@app.route('/users/<int:uid>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(uid):
    if session['role'] != 'admin' and session['user_id'] != uid:
        flash('Permission denied.', 'danger')
        return redirect(url_for('users'))
    conn = get_db(); cur = conn.cursor(dictionary=True)
    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        new_pwd  = request.form.get('new_password', '').strip()
        new_role = request.form.get('role', '')
        if not name:
            flash('Name cannot be empty.', 'danger')
        else:
            if new_pwd:
                cur.execute(
                    "UPDATE `User` SET name=%s, password=%s WHERE user_id=%s",
                    (name, new_pwd, uid)
                )
            else:
                cur.execute(
                    "UPDATE `User` SET name=%s WHERE user_id=%s",
                    (name, uid)
                )
            conn.commit()
            if new_role and session['role'] == 'admin':
                cur.execute(
                    "UPDATE `User` SET role=%s WHERE user_id=%s",
                    (new_role, uid)
                )
                conn.commit()
            if session['user_id'] == uid:
                session['name'] = name
            flash('User updated successfully!', 'success')
            conn.close()
            return redirect(url_for('users'))
    cur.execute("SELECT * FROM `User` WHERE user_id=%s", (uid,))
    user = cur.fetchone()
    conn.close()
    return render_template('edit_user.html', user=user)
# ══════════════════════════════════════════════════════════════════════════════
# ISSUES
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/issues')
@login_required
def issues():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    sf     = request.args.get('status', '')
    pf     = request.args.get('priority', '')
    pid    = request.args.get('project', '')
    search = request.args.get('q', '').strip()
    q = """SELECT i.issue_id, i.title, i.status, i.priority, i.created_at,
                  i.project_id, p.project_name,
                  r.name AS reporter, a.name AS assignee
           FROM Issue i
           JOIN  Project p ON i.project_id  = p.project_id
           JOIN  `User`  r ON i.reported_by = r.user_id
           LEFT JOIN `User` a ON i.assigned_to = a.user_id
           WHERE 1=1"""
    params = []
    if sf:     q += " AND i.status=%s";      params.append(sf)
    if pf:     q += " AND i.priority=%s";    params.append(pf)
    if pid:    q += " AND i.project_id=%s";  params.append(pid)
    if search:
        q += " AND (i.title LIKE %s OR i.description LIKE %s)"
        params += [f'%{search}%', f'%{search}%']
    q += " ORDER BY FIELD(i.priority,'critical','high','medium','low'), i.created_at DESC"
    cur.execute(q, params)
    all_issues = cur.fetchall()
    cur.execute("SELECT project_id,project_name FROM Project ORDER BY project_name")
    proj_list = cur.fetchall(); conn.close()
    return render_template('issues.html', issues=all_issues,
        sf=sf, pf=pf, pid=pid, search=search, proj_list=proj_list)


@app.route('/issues/new', methods=['GET', 'POST'])
@login_required
def new_issue():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    if request.method == 'POST':
        pid   = request.form.get('project_id')
        title = request.form.get('title', '').strip()
        desc  = request.form.get('description', '').strip()
        prio  = request.form.get('priority', 'medium')
        asgn  = request.form.get('assigned_to') or None
        if not title or not pid:
            flash('Project and title are required.', 'danger')
        else:
            cur.execute("""INSERT INTO Issue
                (project_id,title,description,priority,reported_by,assigned_to)
                VALUES (%s,%s,%s,%s,%s,%s)""",
                (pid, title, desc, prio, session['user_id'], asgn))
            conn.commit()
            iid = cur.lastrowid
            cur.execute("""INSERT INTO Issue_Status_History
                (issue_id,changed_by,old_status,new_status)
                VALUES (%s,%s,NULL,'open')""", (iid, session['user_id']))
            conn.commit(); conn.close()
            flash('Issue reported!', 'success')
            return redirect(url_for('issue_detail', iid=iid))
    cur.execute("SELECT project_id,project_name FROM Project ORDER BY project_name")
    proj_list = cur.fetchall()
    cur.execute("SELECT user_id,name,role FROM `User` ORDER BY name")
    users = cur.fetchall(); conn.close()
    return render_template('new_issue.html', proj_list=proj_list,
        users=users, preselect_pid=request.args.get('project_id', ''))


@app.route('/issues/<int:iid>')
@login_required
def issue_detail(iid):
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT i.*, p.project_name, p.project_id,
               u.name AS reporter, ua.name AS assignee,
               ua.user_id AS assignee_id
        FROM Issue i
        JOIN Project p ON i.project_id=p.project_id
        JOIN `User`  u ON i.reported_by=u.user_id
        LEFT JOIN `User` ua ON i.assigned_to=ua.user_id
        WHERE i.issue_id=%s""", (iid,))
    issue = cur.fetchone()
    if not issue:
        flash('Issue not found.', 'danger')
        return redirect(url_for('issues'))
    cur.execute("""SELECT c.*,u.name,u.role FROM Comment c
        JOIN `User` u ON c.user_id=u.user_id
        WHERE c.issue_id=%s ORDER BY c.timestamp ASC""", (iid,))
    comments = cur.fetchall()
    cur.execute("""SELECT a.*,u.name AS uploader FROM Attachment a
        JOIN `User` u ON a.user_id=u.user_id
        WHERE a.issue_id=%s ORDER BY a.uploaded_at DESC""", (iid,))
    attachments = cur.fetchall()
    cur.execute("""SELECT sh.*,u.name AS changer FROM Issue_Status_History sh
        JOIN `User` u ON sh.changed_by=u.user_id
        WHERE sh.issue_id=%s ORDER BY sh.changed_at DESC""", (iid,))
    history = cur.fetchall()
    cur.execute("SELECT user_id,name,role FROM `User` ORDER BY name")
    users = cur.fetchall(); conn.close()
    return render_template('issue_detail.html',
        issue=issue, comments=comments, attachments=attachments,
        history=history, users=users)


@app.route('/issues/<int:iid>/comment', methods=['POST'])
@login_required
def add_comment(iid):
    text = request.form.get('comment_text', '').strip()
    if text:
        conn = get_db(); cur = conn.cursor()
        cur.execute(
            "INSERT INTO Comment (issue_id,user_id,comment_text) VALUES (%s,%s,%s)",
            (iid, session['user_id'], text)
        )
        conn.commit(); conn.close()
        flash('Comment added!', 'success')
    else:
        flash('Comment cannot be empty.', 'warning')
    return redirect(url_for('issue_detail', iid=iid) + '#comments')


@app.route('/issues/<int:iid>/status', methods=['POST'])
@login_required
def update_status(iid):
    new_st = request.form.get('status')
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("SELECT status FROM Issue WHERE issue_id=%s", (iid,))
    row = cur.fetchone()
    if row and new_st != row['status']:
        old_st = row['status']
        cur.execute("UPDATE Issue SET status=%s WHERE issue_id=%s", (new_st, iid))
        cur.execute("""INSERT INTO Issue_Status_History
            (issue_id,changed_by,old_status,new_status) VALUES (%s,%s,%s,%s)""",
            (iid, session['user_id'], old_st, new_st))
        conn.commit()
        flash(f'Status updated: {old_st} → {new_st}', 'success')
    conn.close()
    return redirect(url_for('issue_detail', iid=iid))


@app.route('/issues/<int:iid>/assign', methods=['POST'])
@login_required
def assign_issue(iid):
    asgn = request.form.get('assigned_to') or None
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE Issue SET assigned_to=%s WHERE issue_id=%s", (asgn, iid))
    conn.commit(); conn.close()
    flash('Assignment updated!', 'success')
    return redirect(url_for('issue_detail', iid=iid))


@app.route('/issues/<int:iid>/attach', methods=['POST'])
@login_required
def upload_attachment(iid):
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('issue_detail', iid=iid))
    f = request.files['file']
    if not allowed_file(f.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('issue_detail', iid=iid))
    orig_name = f.filename
    safe_name = datetime.now().strftime('%Y%m%d_%H%M%S_') + secure_filename(orig_name)
    f.save(os.path.join(app.config['UPLOAD_FOLDER'], safe_name))
    conn = get_db(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO Attachment (issue_id,user_id,file_name,file_path) VALUES (%s,%s,%s,%s)",
        (iid, session['user_id'], orig_name, safe_name)
    )
    conn.commit(); conn.close()
    flash(f'File "{orig_name}" uploaded!', 'success')
    return redirect(url_for('issue_detail', iid=iid) + '#attachments')


@app.route('/uploads/<filename>')
@login_required
def download_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename, as_attachment=True)


@app.route('/issues/<int:iid>/delete', methods=['POST'])
@login_required
def delete_issue(iid):
    if session['role'] not in ('admin', 'manager'):
        flash('Permission denied.', 'danger')
        return redirect(url_for('issue_detail', iid=iid))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM Issue WHERE issue_id=%s", (iid,))
    conn.commit(); conn.close()
    flash('Issue deleted.', 'info')
    return redirect(url_for('issues'))

# ══════════════════════════════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/users')
@login_required
def users():
    if session['role'] not in ('admin', 'manager'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    conn = get_db(); cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT u.*,
               COUNT(DISTINCT i.issue_id)    AS assigned_open,
               COUNT(DISTINCT c.comment_id)  AS comment_count
        FROM `User` u
        LEFT JOIN Issue   i ON u.user_id=i.assigned_to
                            AND i.status NOT IN ('resolved','closed')
        LEFT JOIN Comment c ON u.user_id=c.user_id
        GROUP BY u.user_id ORDER BY u.name
    """)
    all_users = cur.fetchall(); conn.close()
    return render_template('users.html', users=all_users)


@app.route('/users/new', methods=['GET', 'POST'])
@login_required
def new_user():
    if session['role'] != 'admin':
        flash('Only admins can create users.', 'danger')
        return redirect(url_for('users'))
    if request.method == 'POST':
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        pwd   = request.form.get('password', '')
        role  = request.form.get('role', 'developer')
        if not all([name, email, pwd]):
            flash('All fields required.', 'danger')
        else:
            conn = get_db(); cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO `User` (name,email,password,role) VALUES (%s,%s,%s,%s)",
                    (name, email, pwd, role)
                )
                conn.commit()
                flash(f'User "{name}" created!', 'success')
                conn.close()
                return redirect(url_for('users'))
            except Error:
                flash('Email already exists.', 'danger')
            conn.close()
    return render_template('new_user.html')


@app.route('/users/<int:uid>/role', methods=['POST'])
@login_required
@admin_required
def change_role(uid):
    new_role = request.form.get('role')
    if new_role not in ('admin', 'manager', 'developer', 'tester'):
        flash('Invalid role.', 'danger')
        return redirect(url_for('users'))
    if uid == session['user_id']:
        flash("You cannot change your own role.", 'danger')
        return redirect(url_for('users'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("UPDATE `User` SET role=%s WHERE user_id=%s", (new_role, uid))
    conn.commit(); conn.close()
    flash('User role updated.', 'success')
    return redirect(url_for('users'))


@app.route('/users/<int:uid>/delete', methods=['POST'])
@login_required
def delete_user(uid):
    if session['role'] != 'admin':
        flash('Only admins can delete users.', 'danger')
        return redirect(url_for('users'))
    if uid == session['user_id']:
        flash("You can't delete yourself!", 'danger')
        return redirect(url_for('users'))
    conn = get_db(); cur = conn.cursor()
    cur.execute("DELETE FROM `User` WHERE user_id=%s", (uid,))
    conn.commit(); conn.close()
    flash('User deleted.', 'info')
    return redirect(url_for('users'))

# ══════════════════════════════════════════════════════════════════════════════
# PASTE THIS ROUTE INTO app.py BEFORE THE PROFILE ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/dbms-features')
@login_required
def dbms_features():
    """Live demonstration of Views, Functions and Triggers."""
    conn = get_db(); cur = conn.cursor(dictionary=True)

    # ── VIEW 1: v_issue_summary ───────────────────────────────────────────────
    try:
        cur.execute("SELECT * FROM v_issue_summary ORDER BY created_at DESC")
        issue_summary = cur.fetchall()
    except:
        issue_summary = []

    # ── VIEW 2: v_project_stats ───────────────────────────────────────────────
    try:
        cur.execute("SELECT * FROM v_project_stats ORDER BY total_issues DESC")
        project_stats = cur.fetchall()
    except:
        project_stats = []

    # ── VIEW 3: v_user_activity ───────────────────────────────────────────────
    try:
        cur.execute("SELECT * FROM v_user_activity ORDER BY total_comments DESC")
        user_activity = cur.fetchall()
    except:
        user_activity = []

    # ── FUNCTION 1: fn_count_open_issues ─────────────────────────────────────
    fn_open_issues = []
    try:
        cur.execute("SELECT project_id, project_name FROM Project")
        projects = cur.fetchall()
        for p in projects:
            cur.execute("SELECT fn_count_open_issues(%s) AS open_count", (p['project_id'],))
            row = cur.fetchone()
            fn_open_issues.append({
                'project_name': p['project_name'],
                'open_count':   row['open_count']
            })
    except:
        fn_open_issues = []

    # ── FUNCTION 2: fn_issue_priority_score ──────────────────────────────────
    fn_priority_scores = []
    try:
        cur.execute("SELECT issue_id, title, priority FROM Issue ORDER BY issue_id LIMIT 7")
        issues = cur.fetchall()
        for i in issues:
            cur.execute("SELECT fn_issue_priority_score(%s) AS score", (i['issue_id'],))
            row = cur.fetchone()
            fn_priority_scores.append({
                'title':    i['title'],
                'priority': i['priority'],
                'score':    row['score']
            })
    except:
        fn_priority_scores = []

    # ── TRIGGER LOG: Issue_Status_History ────────────────────────────────────
    try:
        cur.execute("""
            SELECT sh.*, u.name AS changer, i.title AS issue_title
            FROM Issue_Status_History sh
            JOIN Issue  i ON sh.issue_id   = i.issue_id
            JOIN `User` u ON sh.changed_by = u.user_id
            ORDER BY sh.changed_at DESC LIMIT 15
        """)
        trigger_log = cur.fetchall()
    except:
        trigger_log = []

    conn.close()
    return render_template('dbms_features.html',
        issue_summary=issue_summary,
        project_stats=project_stats,
        user_activity=user_activity,
        fn_open_issues=fn_open_issues,
        fn_priority_scores=fn_priority_scores,
        trigger_log=trigger_log)
# ══════════════════════════════════════════════════════════════════════════════
# PROFILE
# ══════════════════════════════════════════════════════════════════════════════

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    conn = get_db(); cur = conn.cursor(dictionary=True)
    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        new_pwd = request.form.get('new_password', '')
        cur_pwd = request.form.get('current_password', '')
        cur.execute("SELECT * FROM `User` WHERE user_id=%s", (session['user_id'],))
        user = cur.fetchone()
        if user['password'] != cur_pwd:
            flash('Current password incorrect.', 'danger')
        else:
            updates = ["name=%s"]; params = [name]
            if new_pwd:
                updates.append("password=%s")
                params.append(new_pwd)
            params.append(session['user_id'])
            cur.execute(
                f"UPDATE `User` SET {', '.join(updates)} WHERE user_id=%s", params
            )
            conn.commit()
            session['name'] = name
            flash('Profile updated!', 'success')
            conn.close()
            return redirect(url_for('profile'))
    cur.execute("SELECT * FROM `User` WHERE user_id=%s", (session['user_id'],))
    user = cur.fetchone()
    cur.execute("""SELECT i.issue_id,i.title,i.status,i.priority,p.project_name
        FROM Issue i JOIN Project p ON i.project_id=p.project_id
        WHERE i.assigned_to=%s ORDER BY i.created_at DESC LIMIT 10""",
        (session['user_id'],))
    my_issues = cur.fetchall()
    cur.execute("""SELECT c.comment_text,c.timestamp,i.title,i.issue_id
        FROM Comment c JOIN Issue i ON c.issue_id=i.issue_id
        WHERE c.user_id=%s ORDER BY c.timestamp DESC LIMIT 5""",
        (session['user_id'],))
    my_comments = cur.fetchall()
    conn.close()
    return render_template('profile.html', user=user,
        my_issues=my_issues, my_comments=my_comments)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("\n" + "="*50)
    print("  BUG TRACKER — XAMPP Edition")
    print("  URL: http://127.0.0.1:5000")
    print("  Make sure XAMPP MySQL is running!")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)