import os
import re
import secrets
import uuid
from datetime import date, datetime
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
    url_for,
)
from flask_sqlalchemy import SQLAlchemy
from notifications import send_student_email, send_student_whatsapp
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv(
    "SECRET_KEY", "change-this-secret-before-deployment"
)

# Database URI configuration with Render / Supabase PostgreSQL URL fix
database_url = os.getenv("DATABASE_URL")
if database_url:
  if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
  app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
  # Local development fallback
  app.config["SQLALCHEMY_DATABASE_URI"] = (
      "mysql+pymysql://root:@localhost/br_walkin"
  )

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB upload limit
app.config["UPLOAD_FOLDER"] = os.getenv("UPLOAD_FOLDER", "private_uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
db = SQLAlchemy(app)

PUBLIC_STATUSES = [
    "New",
    "Under Review",
    "Contacted",
    "Shortlisted",
    "Interview Scheduled",
    "Interview Rescheduled",
    "Interview Completed",
    "Selected",
    "Rejected",
    "On Hold",
    "Joined",
    "Follow-up",
    "Interested",
    "Enrolled",
    "Not Interested",
]
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx"}


class Staff(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  name = db.Column(db.String(120), nullable=False)
  email = db.Column(db.String(160), unique=True, nullable=False)
  phone = db.Column(db.String(20), nullable=False)
  password_hash = db.Column(db.String(255), nullable=False)
  active = db.Column(db.Boolean, default=True, nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Student(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  registration_id = db.Column(db.String(30), unique=True, nullable=False)
  full_name = db.Column(db.String(120), nullable=False)
  phone = db.Column(db.String(20), nullable=False)
  email = db.Column(db.String(160), nullable=False)
  qualification = db.Column(db.String(100), nullable=False)
  college = db.Column(db.String(180))
  course_interest = db.Column(db.String(120), nullable=False)
  source = db.Column(db.String(80))
  reference_staff_id = db.Column(
      db.Integer, db.ForeignKey("staff.id"), nullable=False
  )
  resume_filename = db.Column(db.String(255), nullable=False)
  status = db.Column(db.String(40), default="New", nullable=False)
  remarks = db.Column(db.Text)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  staff = db.relationship("Staff", backref="students")


class StudentAccount(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), unique=True, nullable=False
  )
  password_hash = db.Column(db.String(255), nullable=False)
  must_change_password = db.Column(db.Boolean, default=True, nullable=False)
  active = db.Column(db.Boolean, default=True, nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  student = db.relationship(
      "Student", backref=db.backref("account", uselist=False)
  )


class PortalNotification(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  title = db.Column(db.String(180), nullable=False)
  message = db.Column(db.Text, nullable=False)
  category = db.Column(db.String(40), default="Update", nullable=False)
  is_read = db.Column(db.Boolean, default=False, nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  student = db.relationship("Student", backref="notifications")


class ApplicationHistory(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  status = db.Column(db.String(40), nullable=False)
  public_note = db.Column(db.Text)
  actor = db.Column(db.String(160), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  student = db.relationship("Student", backref="history")


class Interview(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  round_name = db.Column(db.String(100), nullable=False)
  scheduled_at = db.Column(db.DateTime, nullable=False)
  mode = db.Column(db.String(30), nullable=False, default="Online")
  venue_or_link = db.Column(db.String(500))
  instructions = db.Column(db.Text)
  status = db.Column(db.String(30), nullable=False, default="Scheduled")
  created_by = db.Column(db.String(160), nullable=False)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  student = db.relationship("Student", backref="interviews")


class FollowUp(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  student_id = db.Column(
      db.Integer, db.ForeignKey("student.id"), nullable=False
  )
  staff_id = db.Column(db.Integer, db.ForeignKey("staff.id"), nullable=False)
  followup_date = db.Column(db.Date, nullable=False)
  note = db.Column(db.Text)
  outcome = db.Column(db.String(40), default="Pending")
  created_at = db.Column(db.DateTime, default=datetime.utcnow)
  student = db.relationship("Student", backref="followups")
  staff = db.relationship("Staff")


class ActivityLog(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  actor = db.Column(db.String(160), nullable=False)
  action = db.Column(db.String(100), nullable=False)
  details = db.Column(db.Text)
  created_at = db.Column(db.DateTime, default=datetime.utcnow)


def log_action(actor, action, details=""):
  db.session.add(ActivityLog(actor=actor, action=action, details=details))
  db.session.commit()


def admin_required(fn):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    if session.get("role") != "admin":
      return redirect(url_for("login"))
    return fn(*args, **kwargs)

  return wrapper


def staff_required(fn):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    if session.get("role") not in ("admin", "staff"):
      return redirect(url_for("login"))
    return fn(*args, **kwargs)

  return wrapper


def student_required(fn):
  @wraps(fn)
  def wrapper(*args, **kwargs):
    if session.get("role") != "student":
      return redirect(url_for("student_login"))
    account = db.session.get(StudentAccount, session.get("student_account_id"))
    if not account or not account.active:
      session.clear()
      flash(
          "Your student portal account is inactive. Contact BR Concepts.",
          "warning",
      )
      return redirect(url_for("student_login"))
    if (
        account.must_change_password
        and request.endpoint != "student_change_password"
    ):
      return redirect(url_for("student_change_password"))
    return fn(*args, **kwargs)

  return wrapper


def allowed_file(filename):
  return (
      "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
  )


def current_actor():
  return session.get("user_name", "Unknown")


def publish_update(student, title, message, category="Update"):
  db.session.add(
      PortalNotification(
          student_id=student.id,
          title=title,
          message=message,
          category=category,
      )
  )
  db.session.commit()
  results = {}
  try:
    results["Email"] = send_student_email(student, title, message)
  except Exception:
    results["Email"] = "Failed – check SMTP configuration"
  try:
    results["WhatsApp"] = send_student_whatsapp(student, title, message)
  except Exception:
    results["WhatsApp"] = "Failed – check Meta template/configuration"
  return results


@app.route("/")
def home():
  if session.get("role") == "student":
    return redirect(url_for("student_dashboard"))
  return redirect(url_for("register"))


@app.route("/register", methods=["GET", "POST"])
def register():
  staff_list = Staff.query.filter_by(active=True).order_by(Staff.name).all()
  if request.method == "POST":
    required = [
        "full_name",
        "phone",
        "email",
        "qualification",
        "course_interest",
        "reference_staff_id",
    ]
    if any(not request.form.get(k, "").strip() for k in required):
      flash("Please complete all required fields.", "danger")
      return render_template("register.html", staff=staff_list)
    phone = re.sub(r"\D", "", request.form["phone"])
    email = request.form["email"].strip().lower()
    if len(phone) < 10 or len(phone) > 15:
      flash(
          "Enter a valid phone number with country code if required.", "danger"
      )
      return render_template("register.html", staff=staff_list)
    staff = db.session.get(Staff, int(request.form["reference_staff_id"]))
    if not staff or not staff.active:
      flash("Please select a valid reference staff member.", "danger")
      return render_template("register.html", staff=staff_list)
    upload = request.files.get("resume")
    if not upload or not upload.filename or not allowed_file(upload.filename):
      flash(
          "Please upload your resume as PDF, DOC or DOCX (maximum 10 MB).",
          "danger",
      )
      return render_template("register.html", staff=staff_list)
    original = secure_filename(upload.filename)
    stored = f"{uuid.uuid4().hex}_{original}"
    upload.save(os.path.join(app.config["UPLOAD_FOLDER"], stored))
    reg_id = (
        "BRW-"
        + datetime.now().strftime("%Y%m")
        + "-"
        + secrets.token_hex(3).upper()
    )
    student = Student(
        registration_id=reg_id,
        full_name=request.form["full_name"].strip(),
        phone=phone,
        email=email,
        qualification=request.form["qualification"].strip(),
        college=request.form.get("college", "").strip(),
        course_interest=request.form["course_interest"].strip(),
        source=request.form.get("source", "").strip(),
        reference_staff_id=staff.id,
        resume_filename=stored,
    )
    db.session.add(student)
    db.session.flush()
    temporary_password = secrets.token_urlsafe(9)
    account = StudentAccount(
        student_id=student.id,
        password_hash=generate_password_hash(temporary_password),
        must_change_password=True,
    )
    db.session.add(account)
    db.session.add(
        ApplicationHistory(
            student_id=student.id,
            status="New",
            public_note="Your registration was received successfully.",
            actor="BR Concepts",
        )
    )
    db.session.add(
        PortalNotification(
            student_id=student.id,
            title="Registration successful",
            message=(
                f"Your BR Concepts registration is confirmed. Your Registration"
                f" ID is {reg_id}. You can track published updates in this"
                " portal."
            ),
            category="Registration",
        )
    )
    db.session.commit()
    log_action(
        "Student portal",
        "New walk-in registration",
        f"{reg_id} assigned to {staff.name}",
    )
    login_url = (
        os.getenv("STUDENT_PORTAL_URL", request.url_root.rstrip("/"))
        + url_for("student_login")
    )
    credential_message = (
        f"Your BR Concepts student portal is ready. Registration ID: {reg_id}."
        f" Temporary password: {temporary_password}. Login: {login_url}. Please"
        " change this password after your first login."
    )
    channels = {}
    try:
      channels["Email"] = send_student_email(
          student, "BR Concepts student portal login", credential_message
      )
    except Exception:
      channels["Email"] = "Failed – check SMTP configuration"
    try:
      channels["WhatsApp"] = send_student_whatsapp(
          student, "Your BR Concepts portal login", credential_message
      )
    except Exception:
      channels["WhatsApp"] = "Failed – check Meta template/configuration"
    session["last_registration"] = {
        "registration_id": reg_id,
        "name": student.full_name,
        "channels": channels,
        "temporary_password": (
            temporary_password
            if not any(v == "Sent" for v in channels.values())
            else None
        ),
    }
    return redirect(url_for("registration_success"))
  return render_template("register.html", staff=staff_list)


@app.route("/success")
def registration_success():
  data = session.pop("last_registration", None)
  if not data:
    return redirect(url_for("register"))
  return render_template("success.html", data=data)


@app.route("/login", methods=["GET", "POST"])
def login():
  if request.method == "POST":
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    admin_hash = generate_password_hash(
        os.getenv("ADMIN_PASSWORD", "ChangeMe123!")
    )
    if email == os.getenv(
        "ADMIN_EMAIL", "admin@brconcepts.in"
    ).lower() and check_password_hash(admin_hash, password):
      session.clear()
      session.update(role="admin", user_name="BR Concepts Admin")
      return redirect(url_for("admin_dashboard"))
    staff = Staff.query.filter_by(email=email, active=True).first()
    if staff and check_password_hash(staff.password_hash, password):
      session.clear()
      session.update(role="staff", staff_id=staff.id, user_name=staff.name)
      return redirect(url_for("students"))
    flash("Invalid login details.", "danger")
  return render_template("login.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
  if request.method == "POST":
    reg_id = request.form.get("registration_id", "").strip().upper()
    password = request.form.get("password", "")
    student = Student.query.filter_by(registration_id=reg_id).first()
    account = (
        StudentAccount.query.filter_by(student_id=student.id, active=True).first()
        if student
        else None
    )
    if account and check_password_hash(account.password_hash, password):
      session.clear()
      session.update(
          role="student",
          student_account_id=account.id,
          student_id=student.id,
          user_name=student.full_name,
      )
      return redirect(
          url_for(
              "student_change_password"
              if account.must_change_password
              else "student_dashboard"
          )
      )
    flash("Invalid registration ID or password.", "danger")
  return render_template("student_login.html")


@app.route("/student/change-password", methods=["GET", "POST"])
@student_required
def student_change_password():
  account = db.session.get(StudentAccount, session["student_account_id"])
  if request.method == "POST":
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    if len(password) < 10:
      flash("Use at least 10 characters for your new password.", "danger")
    elif password != confirm:
      flash("Passwords do not match.", "danger")
    else:
      account.password_hash = generate_password_hash(password)
      account.must_change_password = False
      db.session.commit()
      log_action(
          account.student.registration_id, "Changed student portal password"
      )
      flash("Password updated successfully.", "success")
      return redirect(url_for("student_dashboard"))
  return render_template("student_change_password.html")


@app.route("/student/portal")
@student_required
def student_dashboard():
  student = db.session.get(Student, session["student_id"])
  notifications = (
      PortalNotification.query.filter_by(student_id=student.id)
      .order_by(PortalNotification.created_at.desc())
      .limit(10)
      .all()
  )
  interviews = (
      Interview.query.filter_by(student_id=student.id)
      .order_by(Interview.scheduled_at.desc())
      .all()
  )
  history = (
      ApplicationHistory.query.filter_by(student_id=student.id)
      .order_by(ApplicationHistory.created_at.desc())
      .all()
  )
  unread = PortalNotification.query.filter_by(
      student_id=student.id, is_read=False
  ).count()
  return render_template(
      "student_dashboard.html",
      student=student,
      notifications=notifications,
      interviews=interviews,
      history=history,
      unread=unread,
  )


@app.route("/student/resume")
@student_required
def student_resume():
  student = db.session.get(Student, session["student_id"])
  return send_from_directory(
      app.config["UPLOAD_FOLDER"], student.resume_filename, as_attachment=True
  )


@app.route("/student/notifications/read/<int:notification_id>", methods=["POST"])
@student_required
def read_notification(notification_id):
  item = db.get_or_404(PortalNotification, notification_id)
  if item.student_id != session["student_id"]:
    abort(403)
  item.is_read = True
  db.session.commit()
  return redirect(url_for("student_dashboard"))


@app.route("/logout")
def logout():
  session.clear()
  return redirect(url_for("login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
  total = Student.query.count()
  statuses = {s: Student.query.filter_by(status=s).count() for s in PUBLIC_STATUSES}
  staff = Staff.query.order_by(Staff.name).all()
  recent = Student.query.order_by(Student.created_at.desc()).limit(12).all()
  return render_template(
      "admin.html",
      total=total,
      statuses=statuses,
      staff=staff,
      recent=recent,
  )


@app.route("/admin/staff", methods=["GET", "POST"])
@admin_required
def manage_staff():
  if request.method == "POST":
    name, email, phone, password = [
        request.form.get(k, "").strip()
        for k in ("name", "email", "phone", "password")
    ]
    if not all([name, email, phone, password]) or len(password) < 10:
      flash(
          "Complete all fields. Password must contain at least 10 characters.",
          "danger",
      )
    elif Staff.query.filter_by(email=email.lower()).first():
      flash("That email is already registered.", "danger")
    else:
      db.session.add(
          Staff(
              name=name,
              email=email.lower(),
              phone=phone,
              password_hash=generate_password_hash(password),
          )
      )
      db.session.commit()
      log_action(current_actor(), "Created staff account", email.lower())
      flash("Staff account created.", "success")
    return redirect(url_for("manage_staff"))
  return render_template("staff.html", staff=Staff.query.order_by(Staff.name).all())


@app.route("/admin/staff/<int:staff_id>/toggle", methods=["POST"])
@admin_required
def toggle_staff(staff_id):
  staff = db.get_or_404(Staff, staff_id)
  staff.active = not staff.active
  db.session.commit()
  log_action(
      current_actor(),
      "Changed staff active status",
      f"{staff.email}: {staff.active}",
  )
  return redirect(url_for("manage_staff"))


@app.route("/students")
@staff_required
def students():
  query = Student.query
  if session["role"] == "staff":
    query = query.filter_by(reference_staff_id=session["staff_id"])
  search = request.args.get("q", "").strip()
  status = request.args.get("status", "").strip()
  if search:
    query = query.filter(
        db.or_(
            Student.full_name.ilike(f"%{search}%"),
            Student.phone.ilike(f"%{search}%"),
            Student.registration_id.ilike(f"%{search}%"),
        )
    )
  if status:
    query = query.filter_by(status=status)
  rows = query.order_by(Student.created_at.desc()).all()
  return render_template(
      "students.html", students=rows, statuses=PUBLIC_STATUSES
  )


@app.route("/student/<int:student_id>", methods=["GET", "POST"])
@staff_required
def student_detail(student_id):
  student = db.get_or_404(Student, student_id)
  if (
      session["role"] == "staff"
      and student.reference_staff_id != session["staff_id"]
  ):
    abort(403)
  if request.method == "POST":
    new_status = request.form.get("status", student.status)
    if new_status not in PUBLIC_STATUSES:
      abort(400)
    old_status = student.status
    student.status = new_status
    student.remarks = request.form.get("remarks", "").strip()
    public_note = request.form.get("public_note", "").strip()
    if old_status != new_status or public_note:
      db.session.add(
          ApplicationHistory(
              student_id=student.id,
              status=new_status,
              public_note=public_note,
              actor=current_actor(),
          )
      )
      db.session.commit()
      message = (
          f"Your application status is now: {new_status}."
          + (f"\nUpdate: {public_note}" if public_note else "")
      )
      publish_update(student, "Application status updated", message, "Application")
    else:
      db.session.commit()
    log_action(current_actor(), "Updated student record", student.registration_id)
    flash(
        "Student record updated. Student-visible updates were published where"
        " provided.",
        "success",
    )
    return redirect(url_for("student_detail", student_id=student.id))
  return render_template(
      "student_detail.html", student=student, statuses=PUBLIC_STATUSES
  )


@app.route("/admin/student/<int:student_id>/provision-account", methods=["POST"])
@admin_required
def provision_student_account(student_id):
  student = db.get_or_404(Student, student_id)
  temporary_password = secrets.token_urlsafe(9)
  account = StudentAccount.query.filter_by(student_id=student.id).first()
  if account:
    account.password_hash = generate_password_hash(temporary_password)
    account.must_change_password = True
    account.active = True
  else:
    db.session.add(
        StudentAccount(
            student_id=student.id,
            password_hash=generate_password_hash(temporary_password),
            must_change_password=True,
        )
    )
  db.session.add(
      PortalNotification(
          student_id=student.id,
          title="Student portal account activated",
          message=(
              "Your BR Concepts student portal account is ready. Sign in with"
              " your Registration ID and the temporary password sent to your"
              " registered contact details."
          ),
          category="Account",
      )
  )
  db.session.commit()
  login_url = (
      os.getenv("STUDENT_PORTAL_URL", request.url_root.rstrip("/"))
      + url_for("student_login")
  )
  message = (
      f"Your BR Concepts Student Career Portal account is ready. Registration"
      f" ID: {student.registration_id}. Temporary password:"
      f" {temporary_password}. Login: {login_url}. Please change this password"
      " after login."
  )
  results = {}
  try:
    results["Email"] = send_student_email(
        student, "BR Concepts student portal account", message
    )
  except Exception:
    results["Email"] = "Failed"
  try:
    results["WhatsApp"] = send_student_whatsapp(
        student, "BR Concepts portal account", message
    )
  except Exception:
    results["WhatsApp"] = "Failed"
  log_action(
      current_actor(),
      "Provisioned student portal account",
      student.registration_id,
  )
  if not any(value == "Sent" for value in results.values()):
    flash(
        "No credential channel confirmed delivery. Temporary password (share"
        f" securely with student): {temporary_password}",
        "warning",
    )
  else:
    flash(f"Student portal account credentials sent. Delivery: {results}", "success")
  return redirect(url_for("student_detail", student_id=student.id))


@app.route("/student/<int:student_id>/interview", methods=["POST"])
@staff_required
def schedule_interview(student_id):
  student = db.get_or_404(Student, student_id)
  if (
      session["role"] == "staff"
      and student.reference_staff_id != session["staff_id"]
  ):
    abort(403)
  try:
    scheduled_at = datetime.fromisoformat(request.form.get("scheduled_at", ""))
  except ValueError:
    flash("Enter a valid interview date and time.", "danger")
    return redirect(url_for("student_detail", student_id=student.id))
  round_name = request.form.get("round_name", "").strip()
  if not round_name:
    flash("Interview round is required.", "danger")
    return redirect(url_for("student_detail", student_id=student.id))
  interview = Interview(
      student_id=student.id,
      round_name=round_name,
      scheduled_at=scheduled_at,
      mode=request.form.get("mode", "Online"),
      venue_or_link=request.form.get("venue_or_link", "").strip(),
      instructions=request.form.get("instructions", "").strip(),
      created_by=current_actor(),
  )
  db.session.add(interview)
  student.status = "Interview Scheduled"
  public_note = (
      f"{round_name} scheduled for"
      f" {scheduled_at.strftime('%d %b %Y, %I:%M %p')} ({interview.mode})."
  )
  db.session.add(
      ApplicationHistory(
          student_id=student.id,
          status=student.status,
          public_note=public_note,
          actor=current_actor(),
      )
  )
  db.session.commit()
  message = (
      f"Interview: {round_name}\nDate & time:"
      f" {scheduled_at.strftime('%d %b %Y, %I:%M %p')}\nMode:"
      f" {interview.mode}\nVenue / meeting link:"
      f" {interview.venue_or_link or 'Will be shared by BR Concepts'}\nInstructions:"
      f" {interview.instructions or 'Please be available on time.'}"
  )
  results = publish_update(student, "Interview scheduled", message, "Interview")
  log_action(
      current_actor(),
      "Scheduled interview",
      f"{student.registration_id}: {round_name}",
  )
  flash(
      "Interview published to the student portal. Email/WhatsApp: "
      + str(results),
      "success",
  )
  return redirect(url_for("student_detail", student_id=student.id))


@app.route(
    "/student/<int:student_id>/interview/<int:interview_id>/cancel",
    methods=["POST"],
)
@staff_required
def cancel_interview(student_id, interview_id):
  student = db.get_or_404(Student, student_id)
  interview = db.get_or_404(Interview, interview_id)
  if interview.student_id != student.id:
    abort(404)
  if (
      session["role"] == "staff"
      and student.reference_staff_id != session["staff_id"]
  ):
    abort(403)
  interview.status = "Cancelled"
  db.session.commit()
  publish_update(
      student,
      "Interview cancelled",
      (
          f"Your {interview.round_name} scheduled for"
          f" {interview.scheduled_at.strftime('%d %b %Y, %I:%M %p')} has been"
          " cancelled. Please check the portal for further updates."
      ),
      "Interview",
  )
  log_action(
      current_actor(),
      "Cancelled interview",
      f"{student.registration_id}: {interview.round_name}",
  )
  return redirect(url_for("student_detail", student_id=student.id))


@app.route("/resume/<int:student_id>")
@staff_required
def resume(student_id):
  student = db.get_or_404(Student, student_id)
  if (
      session["role"] == "staff"
      and student.reference_staff_id != session["staff_id"]
  ):
    abort(403)
  return send_from_directory(
      app.config["UPLOAD_FOLDER"], student.resume_filename, as_attachment=True
  )


@app.route("/student/<int:student_id>/followup", methods=["POST"])
@staff_required
def add_followup(student_id):
  student = db.get_or_404(Student, student_id)
  if (
      session["role"] == "staff"
      and student.reference_staff_id != session["staff_id"]
  ):
    abort(403)
  dt = date.fromisoformat(request.form["followup_date"])
  db.session.add(
      FollowUp(
          student_id=student.id,
          staff_id=session.get("staff_id", student.reference_staff_id),
          followup_date=dt,
          note=request.form.get("note", ""),
      )
  )
  db.session.commit()
  log_action(current_actor(), "Added follow-up", student.registration_id)
  return redirect(url_for("student_detail", student_id=student.id))


@app.route("/api/summary")
@admin_required
def api_summary():
  return jsonify({
      "total": Student.query.count(),
      "new_today": Student.query.filter(
          db.func.date(Student.created_at) == date.today()
      ).count(),
      "staff": Staff.query.filter_by(active=True).count(),
  })


@app.route("/admin/activity")
@admin_required
def activity():
  logs = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(200).all()
  return render_template("activity.html", logs=logs)


@app.route("/health")
def health():
  return {"status": "ok"}


if __name__ == "__main__":
  with app.app_context():
    db.create_all()
  app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")