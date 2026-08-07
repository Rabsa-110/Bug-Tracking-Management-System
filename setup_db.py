"""
setup_db.py  -  Run ONCE to create database, tables, and sample data
Configured for XAMPP MySQL (root, no password)
Usage: python setup_db.py

Covers:
 - Table Creation with full constraints (PK, FK, UNIQUE, NOT NULL, CHECK, DEFAULT)
 - Data Insertion (sample users, projects, issues, comments, attachments, history)
 - JOIN-ready table structure (foreign keys across all tables)
 - VIEWs: v_issue_summary, v_project_stats, v_user_activity
 - FUNCTION: fn_count_open_issues(project_id), fn_issue_priority_score(issue_id)
 - TRIGGER: trg_after_issue_status_update (auto-inserts status history on UPDATE)
"""

import mysql.connector
# no hashing

# ── XAMPP MySQL Settings ───────────────────────────────────────────────────────
DB_HOST     = 'localhost'
DB_USER     = 'root'
DB_PASSWORD = ''           # XAMPP default = no password
DB_NAME     = 'bug_tracker'
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print("="*60)
    print("  BUG TRACKER - Database Setup (XAMPP)")
    print("="*60)
    print("\nConnecting to XAMPP MySQL...")

    try:
        conn = mysql.connector.connect(
            host=DB_HOST, user=DB_USER, password=DB_PASSWORD)
        cur  = conn.cursor()
    except Exception as e:
        print(f"\n❌ Cannot connect to MySQL: {e}")
        print("\nMake sure:")
        print("  1. XAMPP Control Panel is open")
        print("  2. MySQL is STARTED (green)")
        return

    # ── Create / select database ───────────────────────────────────────────────
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
    cur.execute(f"USE `{DB_NAME}`")
    print(f"✅ Database '{DB_NAME}' ready.")

    # Allow re-running safely
    cur.execute("SET FOREIGN_KEY_CHECKS = 0")

    # ══════════════════════════════════════════════════════════════════════════
    # TABLE CREATION  (with full constraints)
    # ══════════════════════════════════════════════════════════════════════════

    cur.execute("DROP TABLE IF EXISTS Issue_Status_History")
    cur.execute("DROP TABLE IF EXISTS Attachment")
    cur.execute("DROP TABLE IF EXISTS Comment")
    cur.execute("DROP TABLE IF EXISTS Issue")
    cur.execute("DROP TABLE IF EXISTS `User`")
    cur.execute("DROP TABLE IF EXISTS Project")

    # Project ─────────────────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE Project (
        project_id   INT AUTO_INCREMENT,
        project_name VARCHAR(150) NOT NULL,
        description  TEXT,
        created_at   TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT pk_project PRIMARY KEY (project_id),
        CONSTRAINT uq_project_name UNIQUE (project_name),
        CONSTRAINT chk_project_name_len CHECK (CHAR_LENGTH(project_name) >= 3)
    ) ENGINE=InnoDB
    """)

    # User ────────────────────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE `User` (
        user_id    INT AUTO_INCREMENT,
        name       VARCHAR(100)  NOT NULL,
        email      VARCHAR(150)  NOT NULL,
        password   VARCHAR(255)  NOT NULL,
        role       ENUM('admin','tester','developer','manager') NOT NULL DEFAULT 'developer',
        created_at TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT pk_user    PRIMARY KEY (user_id),
        CONSTRAINT uq_email   UNIQUE (email),
        CONSTRAINT chk_email  CHECK (email LIKE '%@%.%'),
        CONSTRAINT chk_name_len CHECK (CHAR_LENGTH(name) >= 2)
    ) ENGINE=InnoDB
    """)

    # Issue ───────────────────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE Issue (
        issue_id    INT AUTO_INCREMENT,
        project_id  INT         NOT NULL,
        title       VARCHAR(250) NOT NULL,
        description TEXT,
        status      ENUM('open','in_progress','resolved','closed') NOT NULL DEFAULT 'open',
        priority    ENUM('low','medium','high','critical')         NOT NULL DEFAULT 'medium',
        reported_by INT         NOT NULL,
        assigned_to INT,
        created_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT pk_issue       PRIMARY KEY (issue_id),
        CONSTRAINT chk_title_len  CHECK (CHAR_LENGTH(title) >= 5),
        CONSTRAINT fk_issue_project  FOREIGN KEY (project_id)  REFERENCES Project(project_id) ON DELETE CASCADE,
        CONSTRAINT fk_issue_reporter FOREIGN KEY (reported_by) REFERENCES `User`(user_id)     ON DELETE RESTRICT,
        CONSTRAINT fk_issue_assignee FOREIGN KEY (assigned_to) REFERENCES `User`(user_id)     ON DELETE SET NULL
    ) ENGINE=InnoDB
    """)

    # Comment ─────────────────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE Comment (
        comment_id   INT AUTO_INCREMENT,
        issue_id     INT  NOT NULL,
        user_id      INT  NOT NULL,
        comment_text TEXT NOT NULL,
        timestamp    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT pk_comment     PRIMARY KEY (comment_id),
        CONSTRAINT fk_comment_issue FOREIGN KEY (issue_id) REFERENCES Issue(issue_id) ON DELETE CASCADE,
        CONSTRAINT fk_comment_user  FOREIGN KEY (user_id)  REFERENCES `User`(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """)

    # Attachment ──────────────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE Attachment (
        attachment_id INT AUTO_INCREMENT,
        issue_id      INT          NOT NULL,
        user_id       INT          NOT NULL,
        file_name     VARCHAR(255) NOT NULL,
        file_path     VARCHAR(500) NOT NULL,
        uploaded_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT pk_attachment      PRIMARY KEY (attachment_id),
        CONSTRAINT fk_attach_issue    FOREIGN KEY (issue_id) REFERENCES Issue(issue_id) ON DELETE CASCADE,
        CONSTRAINT fk_attach_user     FOREIGN KEY (user_id)  REFERENCES `User`(user_id) ON DELETE CASCADE
    ) ENGINE=InnoDB
    """)

    # Issue_Status_History ────────────────────────────────────────────────────
    cur.execute("""
    CREATE TABLE Issue_Status_History (
        history_id INT AUTO_INCREMENT,
        issue_id   INT NOT NULL,
        changed_by INT NOT NULL,
        old_status ENUM('open','in_progress','resolved','closed'),
        new_status ENUM('open','in_progress','resolved','closed') NOT NULL,
        changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT pk_history       PRIMARY KEY (history_id),
        CONSTRAINT chk_status_diff  CHECK (old_status IS NULL OR old_status <> new_status),
        CONSTRAINT fk_hist_issue    FOREIGN KEY (issue_id)   REFERENCES Issue(issue_id)  ON DELETE CASCADE,
        CONSTRAINT fk_hist_changer  FOREIGN KEY (changed_by) REFERENCES `User`(user_id)  ON DELETE RESTRICT
    ) ENGINE=InnoDB
    """)

    cur.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    print("✅ All 6 tables created (with full constraints).")
    print("   - Project  (PK, UNIQUE name, CHECK length)")
    print("   - User     (PK, UNIQUE email, CHECK email format)")
    print("   - Issue    (PK, FK×3, CHECK title length)")
    print("   - Comment  (PK, FK×2)")
    print("   - Attachment (PK, FK×2)")
    print("   - Issue_Status_History (PK, FK×2, CHECK status_diff)")

    # ══════════════════════════════════════════════════════════════════════════
    # DATA INSERTION
    # ══════════════════════════════════════════════════════════════════════════

    # Users
    users = [
        ('Admin User',    'admin@bugtracker.com', 'admin123', 'admin'),
        ('Alice Tester',  'alice@bugtracker.com', 'test123',  'tester'),
        ('Bob Developer', 'bob@bugtracker.com',   'dev123',   'developer'),
        ('Carol Manager', 'carol@bugtracker.com', 'mgr123',   'manager'),
        ('Dave Developer','dave@bugtracker.com',  'dev456',   'developer'),
    ]
    for name, email, pwd, role in users:
        cur.execute("INSERT INTO `User` (name,email,password,role) VALUES (%s,%s,%s,%s)",
    (name, email, pwd, role))
    conn.commit()
    print("✅ Users inserted.")

    # Projects
    projects = [
        ('E-Commerce Platform',  'Online shopping portal with cart, checkout, and payment.'),
        ('Mobile Banking App',   'Secure mobile banking and fund transfer application.'),
        ('HR Management System', 'Employee records, leave management, and payroll system.'),
    ]
    for pname, pdesc in projects:
        cur.execute("INSERT INTO Project (project_name,description) VALUES (%s,%s)", (pname,pdesc))
    conn.commit()
    print("✅ Projects inserted.")

    # Issues
    issues = [
        (1,'Checkout button not responding','Button does nothing on Safari browser.','open','critical',2,3),
        (1,'Wrong tax calculation','Tax calculated before applying discount codes.','in_progress','high',2,3),
        (1,'Product images not loading','Images fail to load on slow 3G connections.','open','medium',2,None),
        (2,'Login OTP not received','OTP SMS not arriving on Airtel numbers.','open','critical',2,4),
        (2,'Balance not refreshing','Account balance cached after transfer.','resolved','high',4,3),
        (3,'Leave balance calculation wrong','Annual leave balance shows wrong days.','open','high',2,5),
        (3,'Employee export to Excel broken','Export fails for more than 500 employees.','in_progress','medium',2,5),
    ]
    for pid,title,desc,status,priority,rep,asgn in issues:
        cur.execute("""INSERT INTO Issue
            (project_id,title,description,status,priority,reported_by,assigned_to)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (pid,title,desc,status,priority,rep,asgn))
    conn.commit()
    print("✅ Issues inserted.")

    # Status history (initial creation records)
    cur.execute("SELECT issue_id, status FROM Issue ORDER BY issue_id")
    for iid, st in cur.fetchall():
        cur.execute("""INSERT INTO Issue_Status_History
            (issue_id,changed_by,old_status,new_status) VALUES (%s,1,NULL,%s)""", (iid,st))
    # Additional history
    extra_history = [
        (2, 3, 'open', 'in_progress'),
        (5, 3, 'open', 'in_progress'),
        (5, 3, 'in_progress', 'resolved'),
        (7, 5, 'open', 'in_progress'),
    ]
    for iid, uid, old, new in extra_history:
        cur.execute("""INSERT INTO Issue_Status_History
            (issue_id,changed_by,old_status,new_status) VALUES (%s,%s,%s,%s)""",
            (iid,uid,old,new))
    conn.commit()
    print("✅ Status history inserted.")

    # Comments
    comments = [
        (1, 3, 'Reproduced on Safari 16. Looks like a JS event listener issue.'),
        (1, 2, 'Also confirmed broken on Firefox iOS.'),
        (2, 3, 'Fix in progress. PR #42 addresses this.'),
        (4, 4, 'Contacted Airtel. Might be their SMS gateway issue.'),
        (5, 3, 'Fixed. Implemented cache invalidation after each transaction.'),
        (6, 5, 'Checking the leave calculation formula now.'),
    ]
    for iid, uid, txt in comments:
        cur.execute("INSERT INTO Comment (issue_id,user_id,comment_text) VALUES (%s,%s,%s)",
            (iid,uid,txt))
    conn.commit()
    print("✅ Comments inserted.")

    # Attachments
    attachments = [
        (1, 2, 'screenshot_safari.png', 'screenshot_safari.png'),
        (2, 3, 'tax_bug_report.pdf',    'tax_bug_report.pdf'),
        (4, 4, 'otp_logs.txt',          'otp_logs.txt'),
    ]
    for iid, uid, fname, fpath in attachments:
        cur.execute("""INSERT INTO Attachment
            (issue_id,user_id,file_name,file_path) VALUES (%s,%s,%s,%s)""",
            (iid,uid,fname,fpath))
    conn.commit()
    print("✅ Attachments inserted.")

    # ══════════════════════════════════════════════════════════════════════════
    # VIEWS
    # ══════════════════════════════════════════════════════════════════════════

    cur.execute("DROP VIEW IF EXISTS v_issue_summary")
    cur.execute("""
    CREATE VIEW v_issue_summary AS
        SELECT
            i.issue_id,
            i.title,
            i.status,
            i.priority,
            i.created_at,
            i.updated_at,
            p.project_name,
            reporter.name  AS reporter_name,
            assignee.name  AS assignee_name,
            COUNT(c.comment_id) AS comment_count
        FROM Issue i
        JOIN  Project p           ON i.project_id  = p.project_id
        JOIN  `User`  reporter    ON i.reported_by  = reporter.user_id
        LEFT JOIN `User`  assignee ON i.assigned_to  = assignee.user_id
        LEFT JOIN Comment c        ON i.issue_id     = c.issue_id
        GROUP BY i.issue_id, i.title, i.status, i.priority, i.created_at,
                 i.updated_at, p.project_name, reporter.name, assignee.name
    """)

    cur.execute("DROP VIEW IF EXISTS v_project_stats")
    cur.execute("""
    CREATE VIEW v_project_stats AS
        SELECT
            p.project_id,
            p.project_name,
            COUNT(i.issue_id)                      AS total_issues,
            SUM(i.status = 'open')                 AS open_issues,
            SUM(i.status = 'in_progress')          AS inprog_issues,
            SUM(i.status IN ('resolved','closed'))  AS done_issues,
            SUM(i.priority = 'critical')           AS critical_count
        FROM Project p
        LEFT JOIN Issue i ON p.project_id = i.project_id
        GROUP BY p.project_id, p.project_name
    """)

    cur.execute("DROP VIEW IF EXISTS v_user_activity")
    cur.execute("""
    CREATE VIEW v_user_activity AS
        SELECT
            u.user_id,
            u.name,
            u.email,
            u.role,
            COUNT(DISTINCT i.issue_id)   AS open_assigned,
            COUNT(DISTINCT c.comment_id) AS total_comments,
            COUNT(DISTINCT a.attachment_id) AS total_attachments
        FROM `User` u
        LEFT JOIN Issue   i ON u.user_id = i.assigned_to AND i.status NOT IN ('resolved','closed')
        LEFT JOIN Comment c ON u.user_id = c.user_id
        LEFT JOIN Attachment a ON u.user_id = a.user_id
        GROUP BY u.user_id, u.name, u.email, u.role
    """)

    conn.commit()
    print("✅ Views created:")
    print("   - v_issue_summary   (issues with project, reporter, assignee, comment count)")
    print("   - v_project_stats   (per-project issue counts by status/priority)")
    print("   - v_user_activity   (per-user open issues, comments, attachments)")

    # ══════════════════════════════════════════════════════════════════════════
    # FUNCTIONS
    # ══════════════════════════════════════════════════════════════════════════

    cur.execute("DROP FUNCTION IF EXISTS fn_count_open_issues")
    cur.execute("""
    CREATE FUNCTION fn_count_open_issues(p_project_id INT)
    RETURNS INT
    READS SQL DATA
    DETERMINISTIC
    BEGIN
        DECLARE v_count INT DEFAULT 0;
        SELECT COUNT(*) INTO v_count
        FROM Issue
        WHERE project_id = p_project_id
          AND status = 'open';
        RETURN v_count;
    END
    """)

    cur.execute("DROP FUNCTION IF EXISTS fn_issue_priority_score")
    cur.execute("""
    CREATE FUNCTION fn_issue_priority_score(p_issue_id INT)
    RETURNS INT
    READS SQL DATA
    DETERMINISTIC
    BEGIN
        DECLARE v_priority VARCHAR(20);
        DECLARE v_score    INT DEFAULT 0;
        SELECT priority INTO v_priority FROM Issue WHERE issue_id = p_issue_id;
        CASE v_priority
            WHEN 'critical' THEN SET v_score = 4;
            WHEN 'high'     THEN SET v_score = 3;
            WHEN 'medium'   THEN SET v_score = 2;
            WHEN 'low'      THEN SET v_score = 1;
            ELSE                 SET v_score = 0;
        END CASE;
        RETURN v_score;
    END
    """)

    conn.commit()
    print("✅ Functions created:")
    print("   - fn_count_open_issues(project_id) → INT")
    print("   - fn_issue_priority_score(issue_id) → INT (critical=4, high=3, medium=2, low=1)")

    # ══════════════════════════════════════════════════════════════════════════
    # TRIGGERS
    # ══════════════════════════════════════════════════════════════════════════

    cur.execute("DROP TRIGGER IF EXISTS trg_after_issue_status_update")
    cur.execute("""
    CREATE TRIGGER trg_after_issue_status_update
    AFTER UPDATE ON Issue
    FOR EACH ROW
    BEGIN
        IF OLD.status <> NEW.status THEN
            INSERT INTO Issue_Status_History
                (issue_id, changed_by, old_status, new_status)
            VALUES
                (NEW.issue_id, NEW.reported_by, OLD.status, NEW.status);
        END IF;
    END
    """)

    cur.execute("DROP TRIGGER IF EXISTS trg_before_user_insert")
    cur.execute("""
    CREATE TRIGGER trg_before_user_insert
    BEFORE INSERT ON `User`
    FOR EACH ROW
    BEGIN
        SET NEW.email = LOWER(TRIM(NEW.email));
        SET NEW.name  = TRIM(NEW.name);
    END
    """)

    conn.commit()
    print("✅ Triggers created:")
    print("   - trg_after_issue_status_update  (auto-logs status changes to history table)")
    print("   - trg_before_user_insert         (normalises email to lowercase, trims whitespace)")

    # ══════════════════════════════════════════════════════════════════════════
    # Finish
    # ══════════════════════════════════════════════════════════════════════════
    cur.close(); conn.close()

    print("\n" + "="*60)
    print("  ✅  SETUP COMPLETE!")
    print("="*60)
    print("""
DBMS Features Implemented:
  ✔ Table Creation    — 6 tables, PK/FK/UNIQUE/NOT NULL/CHECK/DEFAULT constraints
  ✔ Data Insertion    — 5 users, 3 projects, 7 issues, 6 comments, 3 attachments
  ✔ JOIN Operations   — views & app queries use JOIN across all related tables
  ✔ Views (3)         — v_issue_summary, v_project_stats, v_user_activity
  ✔ Functions (2)     — fn_count_open_issues, fn_issue_priority_score
  ✔ Triggers (2)      — auto status-history logging, email normalisation
  ✔ Update/Search     — supported in app.py (status update, filter/search)
""")
    print("Demo Login Credentials:")
    print("┌─────────────────────────────────────────┐")
    print("│ admin@bugtracker.com   / admin123 (Admin)│")
    print("│ alice@bugtracker.com   / test123  (Tester)│")
    print("│ bob@bugtracker.com     / dev123   (Dev)  │")
    print("│ carol@bugtracker.com   / mgr123   (Mgr)  │")
    print("│ dave@bugtracker.com    / dev456   (Dev)  │")
    print("└─────────────────────────────────────────┘")
    print("\nNow run: python app.py")
    print("Open:    http://127.0.0.1:5000\n")

if __name__ == '__main__':
    main()
