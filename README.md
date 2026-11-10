# BR Concepts Walk-in & Student Career Portal

Flask + MySQL recruitment portal with QR-based walk-in registration, Admin/Staff access, student self-service login, interview scheduling, application timeline, in-portal notifications, email and WhatsApp alerts.

## Features retained
- Public walk-in registration and resume upload (PDF/DOC/DOCX, max 10 MB)
- Unique BRW registration ID
- Admin and staff login; staff see only their assigned students
- Staff account management, student search, resume download, follow-ups and activity log
- Existing admin summary and health endpoint

## New student portal features
- A student account is created automatically at registration
- Registration ID is the student username; a random temporary password is generated
- Temporary password delivery is attempted by email and WhatsApp
- First login forces the student to set a new password (minimum 10 characters)
- Student dashboard shows public application status, published timeline, interviews and portal notifications
- Admin/staff can publish public status messages and schedule/cancel interviews
- Internal staff remarks and follow-up notes are not exposed to students

## 1. Requirements
- Windows 10/11
- Python 3.12 recommended
- XAMPP MySQL
- VS Code

## 2. Database
Start MySQL in XAMPP. In phpMyAdmin, run:

```sql
CREATE DATABASE br_walkin CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

The app calls `db.create_all()` on startup. For an existing BR Walk-in database, this creates the new portal tables (`student_account`, `portal_notification`, `application_history`, `interview`) without deleting existing student/staff data. Back up the database before upgrading.

## 3. Install and run

```powershell
cd br_walkin_management
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, set `DATABASE_URL`, a strong `SECRET_KEY`, and the admin password. For default XAMPP root with no password:

```env
DATABASE_URL=mysql+pymysql://root:@localhost/br_walkin
```

Start:

```powershell
python app.py
```

Open `http://127.0.0.1:5000`.

## 4. Login URLs
- Student registration: `/register`
- Student login: `/student/login`
- Admin/staff login: `/login`
- Admin dashboard: `/admin`
- Staff/admin student records: `/students`

Default admin values if not overridden in `.env`:
- Email: `admin@brconcepts.in`
- Password: `ChangeMe123!`

Change these immediately. Staff accounts are created by Admin from Manage Staff.

## 5. Email setup
Configure SMTP values in `.env`. For Gmail, enable 2-step verification and create a Google App Password. Use that app password as `SMTP_PASSWORD`. Test with a real registered email address. If SMTP is not configured, the registration page displays a one-time temporary password fallback only when neither email nor WhatsApp reports a successful send.

## 6. WhatsApp setup
Configure a Meta WhatsApp Cloud API access token and phone number ID. Create an approved Utility message template named by `WA_TEMPLATE_NAME` (default `br_student_update`) with two body placeholders, for example:

`Hello {{1}}, {{2}}`

The app sends the student's name as `{{1}}` and the update/credential text as `{{2}}`. Set the approved template language in `WA_TEMPLATE_LANGUAGE`. Meta approval and WhatsApp messaging rules apply; a configured token alone does not guarantee delivery.

## 7. Production checklist
- Set `FLASK_DEBUG=false`; never expose Flask debug mode publicly.
- Use HTTPS and set `STUDENT_PORTAL_URL` to the final HTTPS domain.
- Use a long random `SECRET_KEY` and a dedicated MySQL user with limited privileges.
- Store uploads outside the public static directory and configure backups/retention.
- Add CSRF protection, rate limiting, password reset, audit/retention policies and a production WSGI server before public launch.
- Keep `.env`, credentials and `private_uploads/` out of Git.
- Email/WhatsApp delivery is best-effort in this starter implementation. Check provider configuration and logs during deployment.

## Student-visible vs internal information
Only the public status and `public_note` are published to the student portal and external channels. The `remarks` field and follow-up notes remain internal to Admin/Staff.
