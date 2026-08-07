-- schema.sql - Bug_Tracker database structure, view, function, and trigger
-- Database: bug_tracker

CREATE DATABASE IF NOT EXISTS bug_tracker CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE bug_tracker;

CREATE TABLE IF NOT EXISTS Project (
    project_id   INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(150) NOT NULL,
    description  TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS `User` (
    user_id    INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(150) UNIQUE NOT NULL,
    password   VARCHAR(255) NOT NULL,
    role       ENUM('admin','tester','developer','manager') NOT NULL DEFAULT 'developer',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Issue (
    issue_id    INT AUTO_INCREMENT PRIMARY KEY,
    project_id  INT NOT NULL,
    title       VARCHAR(250) NOT NULL,
    description TEXT,
    status      ENUM('open','in_progress','resolved','closed') NOT NULL DEFAULT 'open',
    priority    ENUM('low','medium','high','critical') NOT NULL DEFAULT 'medium',
    reported_by INT NOT NULL,
    assigned_to INT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id)  REFERENCES Project(project_id) ON DELETE CASCADE,
    FOREIGN KEY (reported_by) REFERENCES `User`(user_id),
    FOREIGN KEY (assigned_to) REFERENCES `User`(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Comment (
    comment_id   INT AUTO_INCREMENT PRIMARY KEY,
    issue_id     INT NOT NULL,
    user_id      INT NOT NULL,
    comment_text TEXT NOT NULL,
    timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (issue_id) REFERENCES Issue(issue_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES `User`(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Attachment (
    attachment_id INT AUTO_INCREMENT PRIMARY KEY,
    issue_id      INT NOT NULL,
    user_id       INT NOT NULL,
    file_name     VARCHAR(255) NOT NULL,
    file_path     VARCHAR(500) NOT NULL,
    uploaded_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (issue_id) REFERENCES Issue(issue_id) ON DELETE CASCADE,
    FOREIGN KEY (user_id)  REFERENCES `User`(user_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS Issue_Status_History (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    issue_id   INT NOT NULL,
    changed_by INT NOT NULL,
    old_status ENUM('open','in_progress','resolved','closed'),
    new_status ENUM('open','in_progress','resolved','closed') NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (issue_id)   REFERENCES Issue(issue_id) ON DELETE CASCADE,
    FOREIGN KEY (changed_by) REFERENCES `User`(user_id)
) ENGINE=InnoDB;

DROP VIEW IF EXISTS Issue_Overview_View;
CREATE VIEW Issue_Overview_View AS
SELECT
    i.issue_id,
    i.title,
    i.description,
    i.status,
    i.priority,
    i.created_at,
    i.updated_at,
    p.project_id,
    p.project_name,
    reporter.user_id AS reporter_id,
    reporter.name AS reported_by,
    assignee.user_id AS assignee_id,
    assignee.name AS assigned_to
FROM Issue i
JOIN Project p ON i.project_id = p.project_id
JOIN `User` reporter ON i.reported_by = reporter.user_id
LEFT JOIN `User` assignee ON i.assigned_to = assignee.user_id;

DROP FUNCTION IF EXISTS issue_age_days;
DELIMITER $$
CREATE FUNCTION issue_age_days(p_issue_id INT)
RETURNS INT
DETERMINISTIC
READS SQL DATA
BEGIN
    DECLARE v_days INT DEFAULT 0;
    SELECT DATEDIFF(CURRENT_DATE, DATE(created_at))
    INTO v_days
    FROM Issue
    WHERE issue_id = p_issue_id;
    RETURN IFNULL(v_days, 0);
END$$
DELIMITER ;

DROP TRIGGER IF EXISTS trg_issue_status_after_update;
DELIMITER $$
CREATE TRIGGER trg_issue_status_after_update
AFTER UPDATE ON Issue
FOR EACH ROW
BEGIN
    IF OLD.status <> NEW.status THEN
        INSERT INTO Issue_Status_History
            (issue_id, changed_by, old_status, new_status)
        VALUES
            (NEW.issue_id, COALESCE(@current_user_id, NEW.reported_by), OLD.status, NEW.status);
    END IF;
END$$
DELIMITER ;
