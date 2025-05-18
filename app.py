import sys
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import logging
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from threading import Timer, Thread
from werkzeug.utils import secure_filename
import json
from sqlalchemy.exc import SQLAlchemyError
import webbrowser
import io
from weasyprint import HTML
import webview  # إضافة مكتبة pywebview

# إعداد الـ logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# إعدادات قاعدة البيانات
basedir = os.path.dirname(os.path.abspath(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, "app.db")}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key-here'

# إعداد مجلد التحميل
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'uploads')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# تهيئة قاعدة البيانات
db = SQLAlchemy(app)
migrate = Migrate(app, db)

def init_db():
    try:
        # إنشاء جداول قاعدة البيانات
        with app.app_context():
            db.create_all()
            
            # التحقق من وجود مستخدمين
            if not User.query.first():
                logging.info("إنشاء قاعدة بيانات مع بيانات عينة...")
                create_sample()
            else:
                logging.info("قاعدة البيانات تحتوي على مستخدمين بالفعل، لن يتم إضافة بيانات عينة.")
                
    except Exception as e:
        logging.error(f"خطأ في تهيئة قاعدة البيانات: {e}")
        raise

# إعداد مجلد الملفات المرفوعة
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
ALLOWED_EXTENSIONS = {'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# إنشاء مجلد الملفات المرفوعة إذا لم يكن موجوداً
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_uploaded_file(file, folder=''):
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # إضافة timestamp لمنع تكرار أسماء الملفات
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{timestamp}_{filename}"
        
        # إنشاء مجلد فرعي إذا تم تحديده
        if folder:
            folder_path = os.path.join(app.config['UPLOAD_FOLDER'], folder)
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
            file_path = os.path.join(folder_path, filename)
        else:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            
        file.save(file_path)
        return filename
    return None

# دالة للتحقق من صحة الرقم القومي
def validate_national_id(nid):
    if not (len(nid) == 14 and nid.isdigit()):
        return False
    century = int(nid[0])
    year = int(nid[1:3])
    month = int(nid[3:5])
    day = int(nid[5:7])
    if century not in [2, 3] or month < 1 or month > 12 or day < 1 or day > 31:
        return False
    return True

# دالة للتحقق من صحة رقم الهاتف
def validate_phone_number(phone):
    if not (len(phone) == 11 and phone.isdigit()):
        return False
    if not phone.startswith(('010', '011', '012', '015')):
        return False
    return True

# نموذج المستخدم
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100), nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    roles = db.Column(db.String(100), nullable=False)
    governorate = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# نموذج قرار تعيين
class AppointmentDecision(db.Model):
    __tablename__ = 'appointment_decisions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    announcement_number = db.Column(db.String(50), nullable=False)
    candidate_code = db.Column(db.String(50), nullable=False)
    decision_number = db.Column(db.String(50), nullable=False)
    decision_date = db.Column(db.Date, nullable=False)
    article_one_text = db.Column(db.Text, nullable=False)
    article_two_text = db.Column(db.Text, nullable=False)
    article_three_text = db.Column(db.Text, nullable=False)
    competent_authority = db.Column(db.String(100), nullable=False)
    authority_approval = db.Column(db.String(100), nullable=False)
    governorate = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # حقول للملفات المرفقة (تخزين أسماء الملفات فقط)
    announcement_file = db.Column(db.String(255), nullable=True)
    candidate_file = db.Column(db.String(255), nullable=True)
    decision_file = db.Column(db.String(255), nullable=True)

# نموذج لجنة وظائف قيادية
class LeadershipCommittee(db.Model):
    __tablename__ = 'leadership_committees'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    decision_number = db.Column(db.String(50), nullable=False)
    decision_date = db.Column(db.Date, nullable=False)
    preamble = db.Column(db.Text, nullable=False)
    chairperson_name = db.Column(db.String(100), nullable=False)
    chairperson_national_id = db.Column(db.String(14), nullable=False)
    chairperson_phone = db.Column(db.String(11), nullable=False)
    admin_member_name = db.Column(db.String(100), nullable=False)
    admin_member_national_id = db.Column(db.String(14), nullable=False)
    admin_member_phone = db.Column(db.String(11), nullable=False)
    hr_member_name = db.Column(db.String(100), nullable=False)
    hr_member_national_id = db.Column(db.String(14), nullable=False)
    hr_member_phone = db.Column(db.String(11), nullable=False)
    it_member_name = db.Column(db.String(100), nullable=False)
    it_member_national_id = db.Column(db.String(14), nullable=False)
    it_member_phone = db.Column(db.String(11), nullable=False)
    legal_member_name = db.Column(db.String(100), nullable=False)
    legal_member_national_id = db.Column(db.String(14), nullable=False)
    legal_member_phone = db.Column(db.String(11), nullable=False)
    other_member_1_name = db.Column(db.String(100), nullable=False)
    other_member_1_national_id = db.Column(db.String(14), nullable=False)
    other_member_1_phone = db.Column(db.String(11), nullable=False)
    other_member_2_name = db.Column(db.String(100), nullable=False)
    other_member_2_national_id = db.Column(db.String(14), nullable=False)
    other_member_2_phone = db.Column(db.String(11), nullable=False)
    article_one_text = db.Column(db.Text, nullable=False)
    secretary_name = db.Column(db.String(100), nullable=False)
    secretary_national_id = db.Column(db.String(14), nullable=False)
    secretary_phone = db.Column(db.String(11), nullable=False)
    secretary_member_1_name = db.Column(db.String(100), nullable=False)
    secretary_member_1_national_id = db.Column(db.String(14), nullable=False)
    secretary_member_1_phone = db.Column(db.String(11), nullable=False)
    secretary_member_2_name = db.Column(db.String(100), nullable=False)
    secretary_member_2_national_id = db.Column(db.String(14), nullable=False)
    secretary_member_2_phone = db.Column(db.String(11), nullable=False)
    article_two_text = db.Column(db.Text, nullable=False)
    committee_tasks = db.Column(db.Text, nullable=False)
    article_four = db.Column(db.Text, nullable=False)
    competent_authority = db.Column(db.String(100), nullable=False)
    authority_approval = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # إضافة حقل governorate
    governorate = db.Column(db.String(100), nullable=False)  # نفس النوع المستخدم في AppointmentDecision

# نموذج الوظيفة
class Job(db.Model):
    __tablename__ = 'jobs'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    job_title = db.Column(db.String(100), nullable=False)
    job_code = db.Column(db.String(50), nullable=False, unique=True)
    job_description = db.Column(db.Text, nullable=False)
    deadline = db.Column(db.Date, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    governorate = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='pending')  # إضافة حقل الحالة (pending, in_progress, completed)

# نموذج حالة الوظيفة
class JobStatus(db.Model):
    __tablename__ = 'job_statuses'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    status = db.Column(db.String(50), nullable=False)  # pending, in_progress, completed, rejected
    notes = db.Column(db.Text, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    job = db.relationship('Job', backref=db.backref('statuses', lazy=True))
    user = db.relationship('User', backref=db.backref('job_statuses', lazy=True))

# دالة لإنشاء قاعدة بيانات مع بيانات عينة
def create_sample():
    """إنشاء بيانات عينة في قاعدة البيانات"""
    try:
        # التحقق من وجود مستخدمين
        if User.query.count() > 0:
            logging.info("قاعدة البيانات تحتوي على مستخدمين بالفعل، لن يتم إضافة بيانات عينة.")
            return

        # إنشاء مستخدم مدير عام
        admin = User(
            full_name="محمد علي",
            email="admin@example.com",
            roles='"general_admin"',
            governorate="القاهرة",
            active=True
        )
        admin.set_password("admin123")
        
        # إنشاء مستخدم محافظ
        governor = User(
            full_name="فاطمة حسن",
            email="governor@example.com",
            roles='"governor"',
            governorate="الإسكندرية",
            active=True
        )
        governor.set_password("governor123")
        
        # إنشاء مستخدمين عاديين
        users = [
            {
                "full_name": "خالد سعيد",
                "email": "khaled@example.com",
                "password": "user123",
                "roles": '"user"',
                "governorate": "القاهرة"
            },
            {
                "full_name": "علي يوسف",
                "email": "ali@example.com",
                "password": "user123",
                "roles": '"user"',
                "governorate": "الإسكندرية"
            },
            {
                "full_name": "احمد سمير",
                "email": "ahmed@example.com",
                "password": "user123",
                "roles": '"user"',
                "governorate": "الجيزة"
            }
        ]
        
        # إضافة المستخدمين لقاعدة البيانات
        db.session.add(admin)
        logging.info("تم إضافة المستخدم: محمد علي")
        
        db.session.add(governor)
        logging.info("تم إضافة المستخدم: فاطمة حسن")
        
        for user_data in users:
            user = User(
                full_name=user_data["full_name"],
                email=user_data["email"],
                roles=user_data["roles"],
                governorate=user_data["governorate"],
                active=True
            )
            user.set_password(user_data["password"])
            db.session.add(user)
            logging.info(f"تم إضافة المستخدم: {user_data['full_name']}")
        
        # حفظ التغييرات
        db.session.commit()
        logging.info("تم إنشاء قاعدة البيانات وبيانات العينة بنجاح!")
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ في إنشاء بيانات العينة: {e}")
        raise

# تهيئة قاعدة البيانات عند بدء التطبيق
with app.app_context():
    db.create_all()

# دالة لتوليد PDF
def generate_pdf(data=None, data_type='committee'):
    buffer = io.BytesIO()

    if not data:
        html_content = "<html><body><p style='text-align: right; font-family: DejaVu Sans, Arial, sans-serif;'>لا توجد بيانات متاحة</p></body></html>"
        HTML(string=html_content).write_pdf(buffer)
        buffer.seek(0)
        return buffer

    if data_type == 'committee':
        members = [
            {"title": "رئيس اللجنة", "name": data['chairperson_name'], "national_id": data['chairperson_national_id'], "phone": data['chairperson_phone']},
            {"title": "عضو الإدارة", "name": data['admin_member_name'], "national_id": data['admin_member_national_id'], "phone": data['admin_member_phone']},
            {"title": "عضو الموارد البشرية", "name": data['hr_member_name'], "national_id": data['hr_member_national_id'], "phone": data['hr_member_phone']},
            {"title": "عضو تكنولوجيا المعلومات", "name": data['it_member_name'], "national_id": data['it_member_national_id'], "phone": data['it_member_phone']},
            {"title": "عضو القانون", "name": data['legal_member_name'], "national_id": data['legal_member_national_id'], "phone": data['legal_member_phone']},
            {"title": "عضو آخر 1", "name": data['other_member_1_name'], "national_id": data['other_member_1_national_id'], "phone": data['other_member_1_phone']},
            {"title": "عضو آخر 2", "name": data['other_member_2_name'], "national_id": data['other_member_2_national_id'], "phone": data['other_member_2_phone']},
        ]

        secretaries = [
            {"title": "أمين اللجنة", "name": data['secretary_name'], "national_id": data['secretary_national_id'], "phone": data['secretary_phone']},
            {"title": "عضو أمانة 1", "name": data['secretary_member_1_name'], "national_id": data['secretary_member_1_national_id'], "phone": data['secretary_member_1_phone']},
            {"title": "عضو أمانة 2", "name": data['secretary_member_2_name'], "national_id": data['secretary_member_2_national_id'], "phone": data['secretary_member_2_phone']},
        ]

        data['members'] = members
        data['secretaries'] = secretaries
        data['current_date'] = datetime.now().strftime('%Y-%m-%d')
        data['governorate'] = session.get('governorate', 'غير محدد')

        html_content = render_template('pdf_template.html', committee_data=data)

    elif data_type == 'appointment':
        data['current_date'] = datetime.now().strftime('%Y-%m-%d')
        data['governorate'] = session.get('governorate', 'غير محدد')
        html_content = render_template('appointment_pdf_template.html', appointment_data=data)

    try:
        HTML(string=html_content).write_pdf(buffer)
    except Exception as e:
        logging.error(f"خطأ أثناء تحويل HTML إلى PDF: {e}")
        raise

    buffer.seek(0)
    return buffer

@app.before_request
def make_session_permanent():
    session.permanent = True

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signup', methods=['POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm-password']
        email = request.form['email']
        governorate = request.form['governorate']

        logging.info(f"محاولة تسجيل مستخدم جديد: username={username}, email={email}, governorate={governorate}")

        if password != confirm_password:
            flash('كلمة المرور وتأكيدها غير متطابقتين', 'error')
            logging.warning("كلمة المرور وتأكيدها غير متطابقتين.")
            return redirect(url_for('index'))

        if User.query.filter_by(email=email).first():
            flash('البريد الإلكتروني مستخدم بالفعل، استخدم بريدًا آخر.', 'error')
            logging.warning(f"البريد الإلكتروني {email} مستخدم بالفعل.")
            return redirect(url_for('index'))

        all_users = User.query.all()
        for user in all_users:
            if user.check_password(password):
                flash('كلمة المرور مستخدمة بالفعل، اختر كلمة مرور أخرى.', 'error')
                logging.warning(f"كلمة المرور مستخدمة بالفعل بواسطة مستخدم آخر.")
                return redirect(url_for('index'))

        try:
            new_user = User(
                full_name=username,
                email=email,
                roles='["user"]',
                governorate=governorate,
                active=True
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            logging.info(f"تم تسجيل المستخدم {username} بنجاح.")
            flash('تم التسجيل بنجاح، يمكنك الآن تسجيل الدخول', 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f"خطأ أثناء التسجيل: {e}")
            flash('حدث خطأ أثناء التسجيل، حاول مرة أخرى.', 'error')

        return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        full_name = request.form['full_name']
        password = request.form['password']

        logging.info(f"محاولة تسجيل دخول المستخدم: full_name={full_name}")

        user = User.query.filter_by(full_name=full_name).first()

        if not user or not user.check_password(password):
            flash('البيانات غير صحيحة', 'error')
            logging.warning("البيانات غير صحيحة.")
            return redirect(url_for('index'))

        if not user.active:
            flash('انتظر السماح لك بالدخول للمنصة', 'warning')
            logging.info(f"المستخدم {full_name} حاول تسجيل الدخول لكنه غير مفعل.")
            return redirect(url_for('index'))

        session['user_id'] = user.id
        session['roles'] = user.roles
        session['full_name'] = user.full_name
        session['governorate'] = user.governorate
        flash('تم تسجيل الدخول بنجاح!', 'success')
        logging.info(f"تم تسجيل دخول المستخدم {full_name} بنجاح.")
        return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    roles = session['roles']
    full_name = session.get('full_name', 'غير معروف')
    governorate = session.get('governorate', 'غير محدد')
    return render_template('dashboard.html', full_name=full_name, roles=roles, governorate=governorate)

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('profile.html', full_name=session['full_name'], roles=session['roles'])

@app.route('/activate_user/<int:user_id>', methods=['GET', 'POST'])
def activate_user(user_id):
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))

    allowed_roles = ['"governor"', '"general_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        flash('ليس لديك صلاحية لتفعيل المستخدمين.', 'error')
        return redirect(url_for('dashboard'))

    user = db.session.get(User, user_id)
    if not user:
        flash('المستخدم غير موجود.', 'error')
        return redirect(url_for('pending_users'))

    if request.method == 'POST':
        try:
            user.active = True
            db.session.commit()
            flash(f'تم تفعيل المستخدم {user.full_name} بنجاح!', 'success')
            logging.info(f"تم تفعيل المستخدم {user.full_name} بواسطة {session['full_name']}.")
        except Exception as e:
            db.session.rollback()
            logging.error(f"خطأ أثناء تفعيل المستخدم {user.full_name}: {e}")
            flash('حدث خطأ أثناء تفعيل المستخدم، حاول مرة أخرى.', 'error')

        return redirect(url_for('pending_users'))

    return render_template('activate_user.html', user=user)

@app.route('/pending_users')
def pending_users():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))

    allowed_roles = ['"governor"', '"general_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        flash('ليس لديك صلاحية لعرض المستخدمين المنتظرين.', 'error')
        return redirect(url_for('dashboard'))

    pending_users = User.query.filter_by(active=False).all()
    return render_template('pending_users.html', pending_users=pending_users)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('roles', None)
    session.pop('full_name', None)
    session.pop('governorate', None)
    flash('تم تسجيل الخروج بنجاح!', 'success')
    return redirect(url_for('index'))

@app.route('/view_pdf')
def view_pdf():
    try:
        decision_type = request.args.get('type', 'committee')  # جلب نوع القرار من المعلمة

        if decision_type == 'appointment':
            latest_appointment = AppointmentDecision.query.filter_by(status='created', user_id=session['user_id']).order_by(AppointmentDecision.created_at.desc()).first()
            if latest_appointment:
                appointment_data = {
                    'decision_number': latest_appointment.decision_number,
                    'decision_date': latest_appointment.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest_appointment.governorate,
                    'announcement_number': latest_appointment.announcement_number,
                    'candidate_code': latest_appointment.candidate_code,
                    'article_one_text': latest_appointment.article_one_text,
                    'article_two_text': latest_appointment.article_two_text,
                    'article_three_text': latest_appointment.article_three_text,
                    'competent_authority': latest_appointment.competent_authority,
                    'authority_approval': latest_appointment.authority_approval,
                    'files': {
                        'announcement_file': latest_appointment.announcement_file,
                        'candidate_file': latest_appointment.candidate_file,
                        'decision_file': latest_appointment.decision_file
                    },
                    'type': 'appointment'
                }
                pdf_buffer = generate_pdf(appointment_data, data_type='appointment')
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'inline; filename=appointment_{latest_appointment.decision_number}.pdf'
                return response
            else:
                pdf_buffer = generate_pdf()
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = 'inline; filename=no_data.pdf'
                return response

        elif decision_type == 'committee':
            latest_committee = LeadershipCommittee.query.filter_by(status='created', user_id=session['user_id']).order_by(LeadershipCommittee.created_at.desc()).first()
            if latest_committee:
                committee_data = {
                    'decision_number': latest_committee.decision_number,
                    'decision_date': latest_committee.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest_committee.governorate,
                    'preamble': latest_committee.preamble,
                    'article_one_text': latest_committee.article_one_text,
                    'chairperson_name': latest_committee.chairperson_name,
                    'chairperson_national_id': latest_committee.chairperson_national_id,
                    'chairperson_phone': latest_committee.chairperson_phone,
                    'admin_member_name': latest_committee.admin_member_name,
                    'admin_member_national_id': latest_committee.admin_member_national_id,
                    'admin_member_phone': latest_committee.admin_member_phone,
                    'hr_member_name': latest_committee.hr_member_name,
                    'hr_member_national_id': latest_committee.hr_member_national_id,
                    'hr_member_phone': latest_committee.hr_member_phone,
                    'it_member_name': latest_committee.it_member_name,
                    'it_member_national_id': latest_committee.it_member_national_id,
                    'it_member_phone': latest_committee.it_member_phone,
                    'legal_member_name': latest_committee.legal_member_name,
                    'legal_member_national_id': latest_committee.legal_member_national_id,
                    'legal_member_phone': latest_committee.legal_member_phone,
                    'other_member_1_name': latest_committee.other_member_1_name,
                    'other_member_1_national_id': latest_committee.other_member_1_national_id,
                    'other_member_1_phone': latest_committee.other_member_1_phone,
                    'other_member_2_name': latest_committee.other_member_2_name,
                    'other_member_2_national_id': latest_committee.other_member_2_national_id,
                    'other_member_2_phone': latest_committee.other_member_2_phone,
                    'article_two_text': latest_committee.article_two_text,
                    'secretary_name': latest_committee.secretary_name,
                    'secretary_national_id': latest_committee.secretary_national_id,
                    'secretary_phone': latest_committee.secretary_phone,
                    'secretary_member_1_name': latest_committee.secretary_member_1_name,
                    'secretary_member_1_national_id': latest_committee.secretary_member_1_national_id,
                    'secretary_member_1_phone': latest_committee.secretary_member_1_phone,
                    'secretary_member_2_name': latest_committee.secretary_member_2_name,
                    'secretary_member_2_national_id': latest_committee.secretary_member_2_national_id,
                    'secretary_member_2_phone': latest_committee.secretary_member_2_phone,
                    'committee_tasks': latest_committee.committee_tasks,
                    'article_four': latest_committee.article_four,
                    'competent_authority': latest_committee.competent_authority,
                    'authority_approval': latest_committee.authority_approval
                }
                pdf_buffer = generate_pdf(committee_data, data_type='committee')
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'inline; filename=decision_{latest_committee.decision_number}.pdf'
                return response
            else:
                pdf_buffer = generate_pdf()
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = 'inline; filename=no_data.pdf'
                return response

        else:
            pdf_buffer = generate_pdf()
            response = make_response(pdf_buffer.getvalue())
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = 'inline; filename=no_data.pdf'
            return response
    except Exception as e:
        logging.error(f"خطأ أثناء إنشاء ملف PDF للعرض: {e}")
        flash('حدث خطأ أثناء إنشاء ملف PDF، حاول مرة أخرى.', 'error')
        return redirect(url_for('form_leadership_committee'))

@app.route('/print_pdf')
def print_pdf():
    try:
        decision_type = request.args.get('type', 'committee')

        if decision_type == 'appointment':
            latest_appointment = AppointmentDecision.query.filter_by(status='created', user_id=session['user_id']).order_by(AppointmentDecision.created_at.desc()).first()
            if latest_appointment:
                appointment_data = {
                    'decision_number': latest_appointment.decision_number,
                    'decision_date': latest_appointment.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest_appointment.governorate,
                    'announcement_number': latest_appointment.announcement_number,
                    'candidate_code': latest_appointment.candidate_code,
                    'article_one_text': latest_appointment.article_one_text,
                    'article_two_text': latest_appointment.article_two_text,
                    'article_three_text': latest_appointment.article_three_text,
                    'competent_authority': latest_appointment.competent_authority,
                    'authority_approval': latest_appointment.authority_approval,
                    'files': {
                        'announcement_file': latest_appointment.announcement_file,
                        'candidate_file': latest_appointment.candidate_file,
                        'decision_file': latest_appointment.decision_file
                    },
                    'type': 'appointment'
                }
                pdf_buffer = generate_pdf(appointment_data, data_type='appointment')
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'inline; filename=appointment_{latest_appointment.decision_number}.pdf'
                return response

        elif decision_type == 'committee':
            latest_committee = LeadershipCommittee.query.filter_by(status='created', user_id=session['user_id']).order_by(LeadershipCommittee.created_at.desc()).first()
            if latest_committee:
                committee_data = {
                    'decision_number': latest_committee.decision_number,
                    'decision_date': latest_committee.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest_committee.governorate,
                    'preamble': latest_committee.preamble,
                    'article_one_text': latest_committee.article_one_text,
                    'chairperson_name': latest_committee.chairperson_name,
                    'chairperson_national_id': latest_committee.chairperson_national_id,
                    'chairperson_phone': latest_committee.chairperson_phone,
                    'admin_member_name': latest_committee.admin_member_name,
                    'admin_member_national_id': latest_committee.admin_member_national_id,
                    'admin_member_phone': latest_committee.admin_member_phone,
                    'hr_member_name': latest_committee.hr_member_name,
                    'hr_member_national_id': latest_committee.hr_member_national_id,
                    'hr_member_phone': latest_committee.hr_member_phone,
                    'it_member_name': latest_committee.it_member_name,
                    'it_member_national_id': latest_committee.it_member_national_id,
                    'it_member_phone': latest_committee.it_member_phone,
                    'legal_member_name': latest_committee.legal_member_name,
                    'legal_member_national_id': latest_committee.legal_member_national_id,
                    'legal_member_phone': latest_committee.legal_member_phone,
                    'other_member_1_name': latest_committee.other_member_1_name,
                    'other_member_1_national_id': latest_committee.other_member_1_national_id,
                    'other_member_1_phone': latest_committee.other_member_1_phone,
                    'other_member_2_name': latest_committee.other_member_2_name,
                    'other_member_2_national_id': latest_committee.other_member_2_national_id,
                    'other_member_2_phone': latest_committee.other_member_2_phone,
                    'article_two_text': latest_committee.article_two_text,
                    'secretary_name': latest_committee.secretary_name,
                    'secretary_national_id': latest_committee.secretary_national_id,
                    'secretary_phone': latest_committee.secretary_phone,
                    'secretary_member_1_name': latest_committee.secretary_member_1_name,
                    'secretary_member_1_national_id': latest_committee.secretary_member_1_national_id,
                    'secretary_member_1_phone': latest_committee.secretary_member_1_phone,
                    'secretary_member_2_name': latest_committee.secretary_member_2_name,
                    'secretary_member_2_national_id': latest_committee.secretary_member_2_national_id,
                    'secretary_member_2_phone': latest_committee.secretary_member_2_phone,
                    'committee_tasks': latest_committee.committee_tasks,
                    'article_four': latest_committee.article_four,
                    'competent_authority': latest_committee.competent_authority,
                    'authority_approval': latest_committee.authority_approval
                }
                pdf_buffer = generate_pdf(committee_data, data_type='committee')
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'inline; filename=decision_{latest_committee.decision_number}.pdf'
                return response

        pdf_buffer = generate_pdf()
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'inline; filename=no_data.pdf'
        return response
    except Exception as e:
        logging.error(f"خطأ أثناء إنشاء ملف PDF للطباعة: {e}")
        flash('حدث خطأ أثناء إنشاء ملف PDF للطباعة، حاول مرة أخرى.', 'error')
        return redirect(url_for('form_leadership_committee'))

@app.route('/download_pdf')
def download_pdf():
    try:
        decision_type = request.args.get('type', 'committee')

        if decision_type == 'appointment':
            latest_appointment = AppointmentDecision.query.filter_by(status='created', user_id=session['user_id']).order_by(AppointmentDecision.created_at.desc()).first()
            if latest_appointment:
                appointment_data = {
                    'decision_number': latest_appointment.decision_number,
                    'decision_date': latest_appointment.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest_appointment.governorate,
                    'announcement_number': latest_appointment.announcement_number,
                    'candidate_code': latest_appointment.candidate_code,
                    'article_one_text': latest_appointment.article_one_text,
                    'article_two_text': latest_appointment.article_two_text,
                    'article_three_text': latest_appointment.article_three_text,
                    'competent_authority': latest_appointment.competent_authority,
                    'authority_approval': latest_appointment.authority_approval,
                    'files': {
                        'announcement_file': latest_appointment.announcement_file,
                        'candidate_file': latest_appointment.candidate_file,
                        'decision_file': latest_appointment.decision_file
                    },
                    'type': 'appointment'
                }
                pdf_buffer = generate_pdf(appointment_data, data_type='appointment')
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'attachment; filename=appointment_{latest_appointment.decision_number}.pdf'
                return response

        elif decision_type == 'committee':
            latest_committee = LeadershipCommittee.query.filter_by(status='created', user_id=session['user_id']).order_by(LeadershipCommittee.created_at.desc()).first()
            if latest_committee:
                committee_data = {
                    'decision_number': latest_committee.decision_number,
                    'decision_date': latest_committee.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest_committee.governorate,
                    'preamble': latest_committee.preamble,
                    'article_one_text': latest_committee.article_one_text,
                    'chairperson_name': latest_committee.chairperson_name,
                    'chairperson_national_id': latest_committee.chairperson_national_id,
                    'chairperson_phone': latest_committee.chairperson_phone,
                    'admin_member_name': latest_committee.admin_member_name,
                    'admin_member_national_id': latest_committee.admin_member_national_id,
                    'admin_member_phone': latest_committee.admin_member_phone,
                    'hr_member_name': latest_committee.hr_member_name,
                    'hr_member_national_id': latest_committee.hr_member_national_id,
                    'hr_member_phone': latest_committee.hr_member_phone,
                    'it_member_name': latest_committee.it_member_name,
                    'it_member_national_id': latest_committee.it_member_national_id,
                    'it_member_phone': latest_committee.it_member_phone,
                    'legal_member_name': latest_committee.legal_member_name,
                    'legal_member_national_id': latest_committee.legal_member_national_id,
                    'legal_member_phone': latest_committee.legal_member_phone,
                    'other_member_1_name': latest_committee.other_member_1_name,
                    'other_member_1_national_id': latest_committee.other_member_1_national_id,
                    'other_member_1_phone': latest_committee.other_member_1_phone,
                    'other_member_2_name': latest_committee.other_member_2_name,
                    'other_member_2_national_id': latest_committee.other_member_2_national_id,
                    'other_member_2_phone': latest_committee.other_member_2_phone,
                    'article_two_text': latest_committee.article_two_text,
                    'secretary_name': latest_committee.secretary_name,
                    'secretary_national_id': latest_committee.secretary_national_id,
                    'secretary_phone': latest_committee.secretary_phone,
                    'secretary_member_1_name': latest_committee.secretary_member_1_name,
                    'secretary_member_1_national_id': latest_committee.secretary_member_1_national_id,
                    'secretary_member_1_phone': latest_committee.secretary_member_1_phone,
                    'secretary_member_2_name': latest_committee.secretary_member_2_name,
                    'secretary_member_2_national_id': latest_committee.secretary_member_2_national_id,
                    'secretary_member_2_phone': latest_committee.secretary_member_2_phone,
                    'committee_tasks': latest_committee.committee_tasks,
                    'article_four': latest_committee.article_four,
                    'competent_authority': latest_committee.competent_authority,
                    'authority_approval': latest_committee.authority_approval
                }
                pdf_buffer = generate_pdf(committee_data, data_type='committee')
                response = make_response(pdf_buffer.getvalue())
                response.headers['Content-Type'] = 'application/pdf'
                response.headers['Content-Disposition'] = f'attachment; filename=decision_{latest_committee.decision_number}.pdf'
                return response

        pdf_buffer = generate_pdf()
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = 'attachment; filename=no_data.pdf'
        return response
    except Exception as e:
        logging.error(f"خطأ أثناء إنشاء ملف PDF للتحميل: {e}")
        flash('حدث خطأ أثناء تحميل ملف PDF، حاول مرة أخرى.', 'error')
        return redirect(url_for('form_leadership_committee'))

@app.route('/previous_draft')
def previous_draft():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))

    # جلب governorate من الجلسة
    governorate = session.get('governorate', 'غير محدد')

    # جلب جميع المسودات من LeadershipCommittee
    committee_drafts = LeadershipCommittee.query.filter_by(status='draft', user_id=session['user_id']).order_by(LeadershipCommittee.created_at.desc()).all()
    
    # جلب جميع المسودات من AppointmentDecision
    appointment_drafts = AppointmentDecision.query.filter_by(status='draft', user_id=session['user_id']).order_by(AppointmentDecision.created_at.desc()).all()

    draft_list = []

    # معالجة مسودات LeadershipCommittee
    for draft in committee_drafts:
        draft_data = {
            'type': 'committee',
            'decision_number': draft.decision_number,
            'decision_date': draft.decision_date.strftime('%Y-%m-%d'),
            'governorate': governorate,
            'preamble': draft.preamble,
            'article_one_text': draft.article_one_text,
            'chairperson_name': draft.chairperson_name,
            'chairperson_national_id': draft.chairperson_national_id,
            'chairperson_phone': draft.chairperson_phone,
            'admin_member_name': draft.admin_member_name,
            'admin_member_national_id': draft.admin_member_national_id,
            'admin_member_phone': draft.admin_member_phone,
            'hr_member_name': draft.hr_member_name,
            'hr_member_national_id': draft.hr_member_national_id,
            'hr_member_phone': draft.hr_member_phone,
            'it_member_name': draft.it_member_name,
            'it_member_national_id': draft.it_member_national_id,
            'it_member_phone': draft.it_member_phone,
            'legal_member_name': draft.legal_member_name,
            'legal_member_national_id': draft.legal_member_national_id,
            'legal_member_phone': draft.legal_member_phone,
            'other_member_1_name': draft.other_member_1_name,
            'other_member_1_national_id': draft.other_member_1_national_id,
            'other_member_1_phone': draft.other_member_1_phone,
            'other_member_2_name': draft.other_member_2_name,
            'other_member_2_national_id': draft.other_member_2_national_id,
            'other_member_2_phone': draft.other_member_2_phone,
            'article_two_text': draft.article_two_text,
            'secretary_name': draft.secretary_name,
            'secretary_national_id': draft.secretary_national_id,
            'secretary_phone': draft.secretary_phone,
            'secretary_member_1_name': draft.secretary_member_1_name,
            'secretary_member_1_national_id': draft.secretary_member_1_national_id,
            'secretary_member_1_phone': draft.secretary_member_1_phone,
            'secretary_member_2_name': draft.secretary_member_2_name,
            'secretary_member_2_national_id': draft.secretary_member_2_national_id,
            'secretary_member_2_phone': draft.secretary_member_2_phone,
            'committee_tasks': draft.committee_tasks,
            'article_four': draft.article_four,
            'competent_authority': draft.competent_authority,
            'authority_approval': draft.authority_approval
        }
        draft_list.append(draft_data)

    # معالجة مسودات AppointmentDecision
    for draft in appointment_drafts:
        draft_data = {
            'type': 'appointment',
            'decision_number': draft.decision_number,
            'decision_date': draft.decision_date.strftime('%Y-%m-%d'),
            'governorate': governorate,
            'announcement_number': draft.announcement_number,
            'candidate_code': draft.candidate_code,
            'article_one_text': draft.article_one_text,
            'article_two_text': draft.article_two_text,
            'article_three_text': draft.article_three_text,
            'competent_authority': draft.competent_authority,
            'authority_approval': draft.authority_approval,
            'files': {
                'announcement_file': draft.announcement_file,
                'candidate_file': draft.candidate_file,
                'decision_file': draft.decision_file
            }
        }
        draft_list.append(draft_data)

    return render_template('previous_draft.html', drafts=draft_list)

@app.route('/delete_draft/<decision_number>/<draft_type>', methods=['POST'])
def delete_draft(decision_number, draft_type):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})

    try:
        if draft_type == 'committee':
            draft = LeadershipCommittee.query.filter_by(decision_number=decision_number, user_id=session['user_id'], status='draft').first()
        elif draft_type == 'appointment':
            draft = AppointmentDecision.query.filter_by(decision_number=decision_number, user_id=session['user_id'], status='draft').first()
        else:
            return jsonify({'success': False, 'message': 'نوع المسودة غير صالح'})

        if not draft:
            return jsonify({'success': False, 'message': 'المسودة غير موجودة أو ليس لديك صلاحية لحذفها'})

        db.session.delete(draft)
        db.session.commit()
        logging.info(f"تم حذف المسودة (رقم القرار: {decision_number}, نوع: {draft_type}) بواسطة المستخدم {session['full_name']}.")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء حذف المسودة (رقم القرار: {decision_number}, نوع: {draft_type}): {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء الحذف، حاول مرة أخرى'})

@app.route('/register_new_job', methods=['GET', 'POST'])
def register_new_job():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))

    governorate = session.get('governorate', 'غير محدد')

    if request.method == 'POST':
        try:
            job_title = request.form['job_title']
            job_code = request.form['job_code']
            job_description = request.form['job_description']
            deadline = datetime.strptime(request.form['deadline'], '%Y-%m-%d').date()

            # التحقق من أن كود الوظيفة غير مكرر
            if Job.query.filter_by(job_code=job_code).first():
                flash('كود الوظيفة مستخدم بالفعل، استخدم كودًا آخر.', 'error')
                logging.warning(f"كود الوظيفة {job_code} مستخدم بالفعل.")
                return redirect(url_for('register_new_job'))

            new_job = Job(
                user_id=session['user_id'],
                job_title=job_title,
                job_code=job_code,
                job_description=job_description,
                deadline=deadline,
                governorate=governorate,
                status='pending'  # تعيين الحالة الافتراضية للوظيفة الجديدة
            )

            db.session.add(new_job)
            db.session.commit()
            logging.info(f"تم تسجيل وظيفة جديدة (كود: {job_code}) بواسطة المستخدم {session['full_name']}.")
            flash('تم تسجيل الوظيفة بنجاح!', 'success')
            return redirect(url_for('jobs_in_progress'))  # توجيه المستخدم إلى صفحة الوظائف قيد التقدم

        except Exception as e:
            db.session.rollback()
            logging.error(f"خطأ أثناء تسجيل وظيفة جديدة: {e}")
            flash('حدث خطأ أثناء تسجيل الوظيفة، حاول مرة أخرى.', 'error')
            return redirect(url_for('register_new_job'))

    return render_template('register_new_job.html', governorate=governorate)

@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    try:
        # التحقق من وجود مجلد التحميل
        if 'UPLOAD_FOLDER' not in app.config:
            raise ConfigurationError('لم يتم تعريف مجلد التحميل')
        
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            try:
                os.makedirs(app.config['UPLOAD_FOLDER'])
            except Exception as e:
                logging.error(f"خطأ في إنشاء مجلد التحميل: {e}")
                raise ConfigurationError('لا يمكن إنشاء مجلد التحميل')
        
        # جلب المعاملات الواردة للمستخدم
        user_id = session['user_id']
        try:
            incoming_requests = Request.query.filter(
                Request.user_id == user_id
            ).order_by(Request.created_at.desc()).all()
        except SQLAlchemyError as e:
            logging.error(f"خطأ في قاعدة البيانات: {e}")
            raise DatabaseError('حدث خطأ أثناء جلب المعاملات')
        
        # جلب المرفقات لكل معاملة
        attachments_data = []
        for req in incoming_requests:
            if req.attachments:
                try:
                    attachments = json.loads(req.attachments)
                except json.JSONDecodeError as e:
                    logging.error(f"خطأ في تحليل JSON للمرفقات: {e}")
                    continue  # تخطي هذا الطلب والمتابعة مع التالي
                
                for attachment in attachments:
                    try:
                        file_path = os.path.join(app.config['UPLOAD_FOLDER'], attachment)
                        if not os.path.exists(file_path):
                            logging.warning(f"الملف غير موجود: {file_path}")
                            continue
                        
                        user = User.query.get(req.user_id)
                        if not user:
                            logging.warning(f"المستخدم غير موجود: {req.user_id}")
                            continue
                            
                        file_info = {
                            'name': attachment,
                            'type': attachment.split('.')[-1].lower(),
                            'date': req.created_at.strftime('%Y-%m-%d'),
                            'size': get_file_size(file_path),
                            'uploader': user.full_name,
                            'request_id': req.id
                        }
                        attachments_data.append(file_info)
                    except Exception as e:
                        logging.error(f"خطأ في معالجة المرفق {attachment}: {e}")
                        continue
        
        return render_template('inbox.html', 
                             attachments=attachments_data,
                             requests=incoming_requests)
                             
    except DatabaseError as e:
        logging.error(f"خطأ في قاعدة البيانات: {e}")
        flash('حدث خطأ في الاتصال بقاعدة البيانات', 'error')
        return redirect(url_for('dashboard'))
        
    except ConfigurationError as e:
        logging.error(f"خطأ في الإعدادات: {e}")
        flash('حدث خطأ في إعدادات النظام', 'error')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logging.error(f"خطأ في صفحة الوارد: {e}")
        flash('حدث خطأ أثناء تحميل صفحة الوارد', 'error')
        return redirect(url_for('dashboard'))

@app.route('/view_attachment/<request_id>/<path:filename>')
def view_attachment(request_id, filename):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        # التحقق من صلاحية الوصول للمرفق
        request = Request.query.get_or_404(request_id)
        if request.user_id != session['user_id']:
            allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
            if not any(role in session['roles'] for role in allowed_roles):
                return jsonify({'success': False, 'message': 'ليس لديك صلاحية لعرض هذا المرفق'})
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'الملف غير موجود'})
        
        # تحديد نوع الملف
        file_type = filename.split('.')[-1].lower()
        if file_type in ['pdf', 'jpg', 'jpeg', 'png', 'gif']:
            return send_file(file_path)
        else:
            return send_file(file_path, as_attachment=True)
            
    except Exception as e:
        logging.error(f"خطأ في عرض المرفق: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء عرض المرفق'})

@app.route('/download_attachment/<request_id>/<path:filename>')
def download_attachment(request_id, filename):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        # التحقق من صلاحية تحميل المرفق
        request = Request.query.get_or_404(request_id)
        if request.user_id != session['user_id']:
            allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
            if not any(role in session['roles'] for role in allowed_roles):
                return jsonify({'success': False, 'message': 'ليس لديك صلاحية لتحميل هذا المرفق'})
        
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': 'الملف غير موجود'})
        
        return send_file(file_path, as_attachment=True)
            
    except Exception as e:
        logging.error(f"خطأ في تحميل المرفق: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء تحميل المرفق'})

@app.route('/forward_request/<int:request_id>', methods=['POST'])
def forward_request(request_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        request_obj = Request.query.get_or_404(request_id)
        
        # التحقق من صلاحية تحويل الطلب
        if request_obj.user_id != session['user_id']:
            allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
            if not any(role in session['roles'] for role in allowed_roles):
                return jsonify({'success': False, 'message': 'ليس لديك صلاحية لتحويل هذا الطلب'})
        
        forward_to = request.form.get('forward_to')
        purpose = request.form.get('purpose')
        next_action = request.form.get('next_action')
        due_date = request.form.get('due_date')
        comments = request.form.get('comments')
        
        # إنشاء سجل تحويل جديد
        new_forward = RequestForward(
            request_id=request_id,
            from_user_id=session['user_id'],
            to_user_id=forward_to,
            purpose=purpose,
            next_action=next_action,
            due_date=datetime.strptime(due_date, '%Y-%m-%d'),
            comments=comments,
            status='pending'
        )
        
        db.session.add(new_forward)
        db.session.commit()
        
        # تحديث حالة الطلب
        request_obj.status = 'forwarded'
        db.session.commit()
        
        logging.info(f"تم تحويل الطلب {request_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تحويل الطلب بنجاح'
        })
            
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ في تحويل الطلب: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء تحويل الطلب'})

@app.route('/return_request/<int:request_id>', methods=['POST'])
def return_request(request_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        request_obj = Request.query.get_or_404(request_id)
        
        # التحقق من صلاحية رد الطلب
        if request_obj.user_id != session['user_id']:
            allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
            if not any(role in session['roles'] for role in allowed_roles):
                return jsonify({'success': False, 'message': 'ليس لديك صلاحية لرد هذا الطلب'})
        
        reason = request.form.get('reason')
        comments = request.form.get('comments')
        
        # إنشاء سجل رد الطلب
        new_return = RequestReturn(
            request_id=request_id,
            returned_by=session['user_id'],
            reason=reason,
            comments=comments
        )
        
        db.session.add(new_return)
        
        # تحديث حالة الطلب
        request_obj.status = 'returned'
        db.session.commit()
        
        logging.info(f"تم رد الطلب {request_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم رد الطلب بنجاح'
        })
            
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ في رد الطلب: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء رد الطلب'})

@app.route('/save_request/<int:request_id>', methods=['POST'])
def save_request(request_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        request_obj = Request.query.get_or_404(request_id)
        
        # التحقق من صلاحية حفظ الطلب
        if request_obj.user_id != session['user_id']:
            allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
            if not any(role in session['roles'] for role in allowed_roles):
                return jsonify({'success': False, 'message': 'ليس لديك صلاحية لحفظ هذا الطلب'})
        
        notes = request.form.get('notes')
        
        # تحديث ملاحظات الطلب
        request_obj.notes = notes
        db.session.commit()
        
        logging.info(f"تم حفظ الطلب {request_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم حفظ الطلب بنجاح'
        })
            
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ في حفظ الطلب: {e}")
        return jsonify({'success': False, 'message': 'حدث خطأ أثناء حفظ الطلب'})

def get_file_size(file_path):
    """حساب حجم الملف بتنسيق مناسب"""
    try:
        size = os.path.getsize(file_path)
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"
    except:
        return "غير معروف"

@app.route('/outbox')
def outbox():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    # جلب الوظائف التي أنشأها المستخدم الحالي
    user_jobs = Job.query.filter_by(user_id=session['user_id']).all()
    return render_template('outbox.html', jobs=user_jobs)

@app.route('/job_results')
def job_results():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    # جلب الوظائف المكتملة
    jobs = Job.query.filter_by(status='completed').all()
    return render_template('job_results.html', jobs=jobs)

@app.route('/reports')
def reports():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('reports.html')

@app.route('/search')
def search():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('search.html')

@app.route('/delegations')
def delegations():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('delegations.html')

@app.route('/withdraw')
def withdraw():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('withdraw.html')

@app.route('/jobs_in_progress')
def jobs_in_progress():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    # جلب الوظائف التي تحت الإجراء
    jobs = Job.query.filter_by(status='pending').all()
    return render_template('jobs_in_progress.html', jobs=jobs)

@app.route('/job_progress/<job_code>')
def job_progress(job_code):
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    job = Job.query.filter_by(job_code=job_code).first()
    if not job:
        return jsonify({'error': 'الوظيفة غير موجودة'}), 404
    
    # هنا يمكن إضافة المزيد من المعلومات حول تقدم الوظيفة في المستقبل
    progress_data = {
        'job_title': job.job_title,
        'job_code': job.job_code,
        'status': job.status,
        'created_at': job.created_at.strftime('%Y-%m-%d'),
        'deadline': job.deadline.strftime('%Y-%m-%d'),
        'progress_stage': 'تحت المراجعة',  # يمكن تغييرها لاحقاً بناءً على حالة الوظيفة الفعلية
        'details': 'تفاصيل إضافية حول تقدم الوظيفة ستظهر هنا.'
    }
    
    return jsonify(progress_data)

@app.route('/completed_jobs')
def completed_jobs():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('completed_jobs.html')

@app.route('/form_supervisory_committee')
def form_supervisory_committee():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('form_supervisory_committee.html')

@app.route('/issue_appointment_decision', methods=['GET', 'POST'])
def issue_appointment_decision():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))

    governorate = session.get('governorate', 'غير محدد')

    if request.method == 'POST':
        action = request.form.get('action')

        # جمع البيانات من النموذج
        try:
            decision_date = datetime.strptime(request.form['decision_date'], '%Y-%m-%d').date()
        except ValueError:
            flash('تاريخ القرار غير صالح، يرجى استخدام الصيغة الصحيحة (YYYY-MM-DD).', 'error')
            return redirect(url_for('issue_appointment_decision'))

        appointment_data = {
            'announcement_number': request.form.get('announcement_number'),
            'candidate_code': request.form.get('candidate_code'),
            'decision_number': request.form.get('decision_number'),
            'decision_date': decision_date,
            'article_one_text': request.form.get('article_one_text'),
            'article_two_text': request.form.get('article_two_text'),
            'article_three_text': request.form.get('article_three_text'),
            'competent_authority': request.form.get('competent_authority'),
            'authority_approval': request.form.get('authority_approval'),
            'governorate': governorate,
            'type': 'appointment'
        }

        # التعامل مع الملفات المرفوعة
        files = {}
        for file_field in ['announcement_file', 'candidate_file', 'decision_file']:
            if file_field in request.files and request.files[file_field].filename != '':
                files[file_field] = request.files[file_field].filename
            else:
                files[file_field] = None

        # إنشاء كائن قرار التعيين
        new_appointment = AppointmentDecision(
            user_id=session['user_id'],
            announcement_number=appointment_data['announcement_number'],
            candidate_code=appointment_data['candidate_code'],
            decision_number=appointment_data['decision_number'],
            decision_date=appointment_data['decision_date'],
            article_one_text=appointment_data['article_one_text'],
            article_two_text=appointment_data['article_two_text'],
            article_three_text=appointment_data['article_three_text'],
            competent_authority=appointment_data['competent_authority'],
            authority_approval=appointment_data['authority_approval'],
            governorate=appointment_data['governorate'],
            announcement_file=files.get('announcement_file'),
            candidate_file=files.get('candidate_file'),
            decision_file=files.get('decision_file')
        )

        if action == 'create_decision':
            new_appointment.status = 'created'
            try:
                db.session.add(new_appointment)
                db.session.commit()
                logging.info(f"تم إنشاء قرار تعيين (رقم القرار: {new_appointment.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم إنشاء قرار التعيين بنجاح!', 'success')
            except Exception as e:
                db.session.rollback()
                logging.error(f"خطأ أثناء إنشاء قرار تعيين: {e}")
                flash('حدث خطأ أثناء إنشاء القرار، حاول مرة أخرى.', 'error')
            return redirect(url_for('issue_appointment_decision'))

        elif action == 'save_draft':
            new_appointment.status = 'draft'
            try:
                db.session.add(new_appointment)
                db.session.commit()
                logging.info(f"تم حفظ قرار تعيين كمسودة (رقم القرار: {new_appointment.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم حفظ المسودة بنجاح!', 'success')
            except Exception as e:
                db.session.rollback()
                logging.error(f"خطأ أثناء حفظ المسودة: {e}")
                flash('حدث خطأ أثناء حفظ المسودة، حاول مرة أخرى.', 'error')
            return redirect(url_for('issue_appointment_decision'))

        elif action == 'refer_to':
            new_appointment.status = 'referred'
            try:
                db.session.add(new_appointment)
                db.session.commit()
                logging.info(f"تم إحالة قرار تعيين (رقم القرار: {new_appointment.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تمت الإحالة بنجاح!', 'success')
            except Exception as e:
                db.session.rollback()
                logging.error(f"خطأ أثناء الإحالة: {e}")
                flash('حدث خطأ أثناء الإحالة، حاول مرة أخرى.', 'error')
            return redirect(url_for('issue_appointment_decision'))

        elif action == 'next':
            new_appointment.status = 'next'
            try:
                db.session.add(new_appointment)
                db.session.commit()
                logging.info(f"تم الانتقال للخطوة التالية لقرار تعيين (رقم القرار: {new_appointment.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم الانتقال إلى الخطوة التالية!', 'success')
            except Exception as e:
                db.session.rollback()
                logging.error(f"خطأ أثناء الانتقال للخطوة التالية: {e}")
                flash('حدث خطأ أثناء الانتقال للخطوة التالية، حاول مرة أخرى.', 'error')
            return redirect(url_for('issue_appointment_decision'))

    # جلب آخر قرار تم إنشاؤه فقط (status='created')
    latest_appointment = AppointmentDecision.query.filter_by(status='created', user_id=session['user_id']).order_by(AppointmentDecision.created_at.desc()).first()
    if latest_appointment:
        session['latest_appointment'] = {
            'decision_number': latest_appointment.decision_number,
            'decision_date': latest_appointment.decision_date.strftime('%Y-%m-%d'),
            'governorate': latest_appointment.governorate,
            'announcement_number': latest_appointment.announcement_number,
            'candidate_code': latest_appointment.candidate_code,
            'article_one_text': latest_appointment.article_one_text,
            'article_two_text': latest_appointment.article_two_text,
            'article_three_text': latest_appointment.article_three_text,
            'competent_authority': latest_appointment.competent_authority,
            'authority_approval': latest_appointment.authority_approval,
            'files': {
                'announcement_file': latest_appointment.announcement_file,
                'candidate_file': latest_appointment.candidate_file,
                'decision_file': latest_appointment.decision_file
            },
            'type': 'appointment'
        }
    else:
        session.pop('latest_appointment', None)

    return render_template('issue_appointment_decision.html', governorate=governorate)

@app.route('/form_leadership_committee', methods=['GET', 'POST'])
def form_leadership_committee():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))

    governorate = session.get('governorate', 'غير محدد')

    if request.method == 'POST':
        try:
            decision_date = datetime.strptime(request.form['decision_date'], '%Y-%m-%d').date()

            national_ids = [
                request.form['chairperson_national_id'],
                request.form['admin_member_national_id'],
                request.form['hr_member_national_id'],
                request.form['it_member_national_id'],
                request.form['legal_member_national_id'],
                request.form['other_member_1_national_id'],
                request.form['other_member_2_national_id'],
                request.form['secretary_national_id'],
                request.form['secretary_member_1_national_id'],
                request.form['secretary_member_2_national_id']
            ]

            if len(national_ids) != len(set(national_ids)):
                flash('يجب أن تكون جميع الأرقام القومية مختلفة.', 'error')
                logging.warning("تم اكتشاف تكرار في الأرقام القومية.")
                return redirect(url_for('form_leadership_committee'))

            for nid in national_ids:
                if not validate_national_id(nid):
                    flash('كل رقم قومي يجب أن يكون 14 رقمًا ويتبع الصيغة الصحيحة.', 'error')
                    logging.warning(f"رقم قومي غير صالح: {nid}")
                    return redirect(url_for('form_leadership_committee'))

            phone_numbers = [
                request.form['chairperson_phone'],
                request.form['admin_member_phone'],
                request.form['hr_member_phone'],
                request.form['it_member_phone'],
                request.form['legal_member_phone'],
                request.form['other_member_1_phone'],
                request.form['other_member_2_phone'],
                request.form['secretary_phone'],
                request.form['secretary_member_1_phone'],
                request.form['secretary_member_2_phone']
            ]

            for phone in phone_numbers:
                if not validate_phone_number(phone):
                    flash('كل رقم هاتف يجب أن يكون 11 رقمًا ويبدأ بـ 010 أو 011 أو 012 أو 015.', 'error')
                    logging.warning(f"رقم هاتف غير صالح: {phone}")
                    return redirect(url_for('form_leadership_committee'))

            new_committee = LeadershipCommittee(
                user_id=session['user_id'],
                decision_number=request.form['decision_number'],
                decision_date=decision_date,
                preamble=request.form['preamble'],
                chairperson_name=request.form['chairperson_name'],
                chairperson_national_id=request.form['chairperson_national_id'],
                chairperson_phone=request.form['chairperson_phone'],
                admin_member_name=request.form['admin_member_name'],
                admin_member_national_id=request.form['admin_member_national_id'],
                admin_member_phone=request.form['admin_member_phone'],
                hr_member_name=request.form['hr_member_name'],
                hr_member_national_id=request.form['hr_member_national_id'],
                hr_member_phone=request.form['hr_member_phone'],
                it_member_name=request.form['it_member_name'],
                it_member_national_id=request.form['it_member_national_id'],
                it_member_phone=request.form['it_member_phone'],
                legal_member_name=request.form['legal_member_name'],
                legal_member_national_id=request.form['legal_member_national_id'],
                legal_member_phone=request.form['legal_member_phone'],
                other_member_1_name=request.form['other_member_1_name'],
                other_member_1_national_id=request.form['other_member_1_national_id'],
                other_member_1_phone=request.form['other_member_1_phone'],
                other_member_2_name=request.form['other_member_2_name'],
                other_member_2_national_id=request.form['other_member_2_national_id'],
                other_member_2_phone=request.form['other_member_2_phone'],
                article_one_text=request.form['article_one_text'],
                secretary_name=request.form['secretary_name'],
                secretary_national_id=request.form['secretary_national_id'],
                secretary_phone=request.form['secretary_phone'],
                secretary_member_1_name=request.form['secretary_member_1_name'],
                secretary_member_1_national_id=request.form['secretary_member_1_national_id'],
                secretary_member_1_phone=request.form['secretary_member_1_phone'],
                secretary_member_2_name=request.form['secretary_member_2_name'],
                secretary_member_2_national_id=request.form['secretary_member_2_national_id'],
                secretary_member_2_phone=request.form['secretary_member_2_phone'],
                article_two_text=request.form['article_two_text'],
                committee_tasks=request.form['committee_tasks'],
                article_four=request.form['article_four'],
                competent_authority=request.form['competent_authority'],
                authority_approval=request.form['authority_approval'],
                governorate=governorate  # إضافة governorate مباشرة
            )

            action = request.form.get('action')

            if action == 'create_decision':
                new_committee.status = 'created'
                db.session.add(new_committee)
                db.session.commit()
                logging.info(f"تم إنشاء قرار لجنة (رقم القرار: {new_committee.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم إنشاء قرار بتشكيل لجنة وظائف قيادية', 'success')
                return redirect(url_for('form_leadership_committee'))

            elif action == 'save_draft':
                new_committee.status = 'draft'
                db.session.add(new_committee)
                db.session.commit()
                logging.info(f"تم حفظ لجنة كمسودة (رقم القرار: {new_committee.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم حفظ اللجنة كمسودة بنجاح!', 'success')
                return redirect(url_for('form_leadership_committee'))

            elif action == 'refer_to':
                new_committee.status = 'referred'
                db.session.add(new_committee)
                db.session.commit()
                logging.info(f"تم إحالة لجنة (رقم القرار: {new_committee.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم إحالة اللجنة بنجاح!', 'success')
                return redirect(url_for('form_leadership_committee'))

            elif action == 'next':
                new_committee.status = 'next'
                db.session.add(new_committee)
                db.session.commit()
                logging.info(f"تم الانتقال للخطوة التالية للجنة (رقم القرار: {new_committee.decision_number}) بواسطة المستخدم {session['full_name']}.")
                flash('تم الانتقال للخطوة التالية بنجاح!', 'success')
                return redirect(url_for('form_leadership_committee'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"خطأ أثناء إنشاء لجنة وظائف قيادية: {e}")
            flash('حدث خطأ أثناء تشكيل اللجنة، حاول مرة أخرى.', 'error')
            return redirect(url_for('form_leadership_committee'))

    # جلب آخر قرار تم إنشاؤه فقط (status='created')
    latest_committee = LeadershipCommittee.query.filter_by(status='created', user_id=session['user_id']).order_by(LeadershipCommittee.created_at.desc()).first()
    if latest_committee:
        session['latest_committee'] = {
            'decision_number': latest_committee.decision_number,
            'decision_date': latest_committee.decision_date.strftime('%Y-%m-%d'),
            'governorate': latest_committee.governorate,
            'preamble': latest_committee.preamble,
            'article_one_text': latest_committee.article_one_text,
            'chairperson_name': latest_committee.chairperson_name,
            'chairperson_national_id': latest_committee.chairperson_national_id,
            'chairperson_phone': latest_committee.chairperson_phone,
            'admin_member_name': latest_committee.admin_member_name,
            'admin_member_national_id': latest_committee.admin_member_national_id,
            'admin_member_phone': latest_committee.admin_member_phone,
            'hr_member_name': latest_committee.hr_member_name,
            'hr_member_national_id': latest_committee.hr_member_national_id,
            'hr_member_phone': latest_committee.hr_member_phone,
            'it_member_name': latest_committee.it_member_name,
            'it_member_national_id': latest_committee.it_member_national_id,
            'it_member_phone': latest_committee.it_member_phone,
            'legal_member_name': latest_committee.legal_member_name,
            'legal_member_national_id': latest_committee.legal_member_national_id,
            'legal_member_phone': latest_committee.legal_member_phone,
            'other_member_1_name': latest_committee.other_member_1_name,
            'other_member_1_national_id': latest_committee.other_member_1_national_id,
            'other_member_1_phone': latest_committee.other_member_1_phone,
            'other_member_2_name': latest_committee.other_member_2_name,
            'other_member_2_national_id': latest_committee.other_member_2_national_id,
            'other_member_2_phone': latest_committee.other_member_2_phone,
            'article_two_text': latest_committee.article_two_text,
            'secretary_name': latest_committee.secretary_name,
            'secretary_national_id': latest_committee.secretary_national_id,
            'secretary_phone': latest_committee.secretary_phone,
            'secretary_member_1_name': latest_committee.secretary_member_1_name,
            'secretary_member_1_national_id': latest_committee.secretary_member_1_national_id,
            'secretary_member_1_phone': latest_committee.secretary_member_1_phone,
            'secretary_member_2_name': latest_committee.secretary_member_2_name,
            'secretary_member_2_national_id': latest_committee.secretary_member_2_national_id,
            'secretary_member_2_phone': latest_committee.secretary_member_2_phone,
            'committee_tasks': latest_committee.committee_tasks,
            'article_four': latest_committee.article_four,
            'competent_authority': latest_committee.competent_authority,
            'authority_approval': latest_committee.authority_approval
        }
    else:
        session.pop('latest_committee', None)

    return render_template('form_leadership_committee.html', governorate=governorate)

@app.route('/decisions')
def decisions():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('decisions.html')

@app.route('/general_statistics_1')
def general_statistics_1():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('general_statistics_1.html')

@app.route('/training_results')
def training_results():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('training_results.html')

@app.route('/update_job_description')
def update_job_description():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('update_job_description.html')

@app.route('/approved_job_descriptions')
def approved_job_descriptions():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('approved_job_descriptions.html')

@app.route('/new_request')
def new_request():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('new_request.html')

@app.route('/delete_request')
def delete_request():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('delete_request.html')

@app.route('/edit_self_evaluation')
def edit_self_evaluation():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('edit_self_evaluation.html')

@app.route('/follow_request')
def follow_request():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('follow_request.html')

@app.route('/interview_schedule')
def interview_schedule():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('interview_schedule.html')

@app.route('/training_schedule')
def training_schedule():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('training_schedule.html')

@app.route('/self_evaluation_grades_1')
def self_evaluation_grades_1():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('self_evaluation_grades_1.html')

@app.route('/appointment_decision')
def appointment_decision():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('appointment_decision.html')

@app.route('/general_statistics_2')
def general_statistics_2():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('general_statistics_2.html')

@app.route('/edit_evaluation')
def edit_evaluation():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('edit_evaluation.html')

@app.route('/evaluation')
def evaluation():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('evaluation.html')

@app.route('/schedule_remote_interview')
def schedule_remote_interview():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('schedule_remote_interview.html')

@app.route('/self_evaluation_grades_2')
def self_evaluation_grades_2():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('self_evaluation_grades_2.html')

@app.route('/send_training_results')
def send_training_results():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('send_training_results.html')

@app.route('/add_training_programs')
def add_training_programs():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('add_training_programs.html')

@app.route('/upload_file', methods=['POST'])
def upload_file():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})
    
    file = request.files['file']
    folder = request.form.get('folder', '')
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'لم يتم اختيار ملف'})
    
    try:
        filename = save_uploaded_file(file, folder)
        if filename:
            return jsonify({
                'success': True,
                'filename': filename,
                'message': 'تم رفع الملف بنجاح'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'نوع الملف غير مسموح به'
            })
    except Exception as e:
        logging.error(f"خطأ أثناء رفع الملف: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء رفع الملف'
        })

@app.route('/download_file/<path:filename>')
def download_file(filename):
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    try:
        return send_file(
            os.path.join(app.config['UPLOAD_FOLDER'], filename),
            as_attachment=True
        )
    except Exception as e:
        logging.error(f"خطأ أثناء تحميل الملف: {e}")
        flash('حدث خطأ أثناء تحميل الملف', 'error')
        return redirect(url_for('dashboard'))

def open_browser():
    # لن نستخدم هذه الدالة بعد الآن لأننا سنستخدم pywebview
    pass

def start_flask():
    """تشغيل خادم Flask في خلفية التطبيق"""
    app.run(debug=False, port=5000)

@app.route('/update_job_status/<int:job_id>', methods=['POST'])
def update_job_status(job_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    job = Job.query.get_or_404(job_id)
    new_status = request.form.get('status')
    notes = request.form.get('notes', '')
    
    if not new_status:
        return jsonify({'success': False, 'message': 'يجب تحديد الحالة الجديدة'})
    
    try:
        # إنشاء سجل حالة جديد
        status_record = JobStatus(
            job_id=job_id,
            status=new_status,
            notes=notes,
            created_by=session['user_id']
        )
        
        # تحديث حالة الوظيفة
        job.status = new_status
        
        db.session.add(status_record)
        db.session.commit()
        
        logging.info(f"تم تحديث حالة الوظيفة {job.job_code} إلى {new_status} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تحديث حالة الوظيفة بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تحديث حالة الوظيفة: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تحديث حالة الوظيفة'
        })

@app.route('/job_status_history/<int:job_id>')
def job_status_history(job_id):
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    job = Job.query.get_or_404(job_id)
    status_history = JobStatus.query.filter_by(job_id=job_id).order_by(JobStatus.created_at.desc()).all()
    
    return render_template('job_status_history.html', job=job, status_history=status_history)

# نموذج برنامج تدريبي
class TrainingProgram(db.Model):
    __tablename__ = 'training_programs'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    location = db.Column(db.String(200), nullable=False)
    capacity = db.Column(db.Integer, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='active')  # active, completed, cancelled

    creator = db.relationship('User', backref=db.backref('created_programs', lazy=True))

# نموذج تسجيل في برنامج تدريبي
class TrainingRegistration(db.Model):
    __tablename__ = 'training_registrations'
    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey('training_programs.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    registration_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected, completed
    attendance_status = db.Column(db.String(50), nullable=True)  # present, absent, late
    evaluation_score = db.Column(db.Float, nullable=True)
    evaluation_notes = db.Column(db.Text, nullable=True)

    program = db.relationship('TrainingProgram', backref=db.backref('registrations', lazy=True))
    user = db.relationship('User', backref=db.backref('training_registrations', lazy=True))

@app.route('/add_training_program', methods=['GET', 'POST'])
def add_training_program():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            
            if end_date < start_date:
                flash('تاريخ الانتهاء يجب أن يكون بعد تاريخ البداية', 'error')
                return redirect(url_for('add_training_program'))
            
            new_program = TrainingProgram(
                title=request.form['title'],
                description=request.form['description'],
                start_date=start_date,
                end_date=end_date,
                location=request.form['location'],
                capacity=int(request.form['capacity']),
                created_by=session['user_id']
            )
            
            db.session.add(new_program)
            db.session.commit()
            
            logging.info(f"تم إضافة برنامج تدريبي جديد: {new_program.title} بواسطة {session['full_name']}")
            flash('تم إضافة البرنامج التدريبي بنجاح', 'success')
            return redirect(url_for('training_schedule'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"خطأ أثناء إضافة برنامج تدريبي: {e}")
            flash('حدث خطأ أثناء إضافة البرنامج التدريبي', 'error')
            return redirect(url_for('add_training_program'))
    
    return render_template('add_training_programs.html')

@app.route('/register_for_training/<int:program_id>', methods=['POST'])
def register_for_training(program_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    program = TrainingProgram.query.get_or_404(program_id)
    
    # التحقق من توفر المقاعد
    current_registrations = TrainingRegistration.query.filter_by(program_id=program_id, status='approved').count()
    if current_registrations >= program.capacity:
        return jsonify({'success': False, 'message': 'عذراً، البرنامج التدريبي مكتمل العدد'})
    
    # التحقق من عدم وجود تسجيل سابق
    existing_registration = TrainingRegistration.query.filter_by(
        program_id=program_id,
        user_id=session['user_id']
    ).first()
    
    if existing_registration:
        return jsonify({'success': False, 'message': 'لقد قمت بالتسجيل في هذا البرنامج مسبقاً'})
    
    try:
        new_registration = TrainingRegistration(
            program_id=program_id,
            user_id=session['user_id']
        )
        
        db.session.add(new_registration)
        db.session.commit()
        
        logging.info(f"تم تسجيل المستخدم {session['full_name']} في البرنامج التدريبي {program.title}")
        return jsonify({
            'success': True,
            'message': 'تم تسجيلك في البرنامج التدريبي بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء التسجيل في البرنامج التدريبي: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء التسجيل في البرنامج التدريبي'
        })

@app.route('/update_training_registration/<int:registration_id>', methods=['POST'])
def update_training_registration(registration_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    registration = TrainingRegistration.query.get_or_404(registration_id)
    new_status = request.form.get('status')
    attendance_status = request.form.get('attendance_status')
    evaluation_score = request.form.get('evaluation_score')
    evaluation_notes = request.form.get('evaluation_notes')
    
    try:
        if new_status:
            registration.status = new_status
        if attendance_status:
            registration.attendance_status = attendance_status
        if evaluation_score:
            registration.evaluation_score = float(evaluation_score)
        if evaluation_notes:
            registration.evaluation_notes = evaluation_notes
        
        db.session.commit()
        
        logging.info(f"تم تحديث تسجيل البرنامج التدريبي {registration_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تحديث التسجيل بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تحديث تسجيل البرنامج التدريبي: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تحديث التسجيل'
        })

# نموذج التقييم
class Evaluation(db.Model):
    __tablename__ = 'evaluations'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    evaluator_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    evaluation_date = db.Column(db.DateTime, default=datetime.utcnow)
    performance_score = db.Column(db.Float, nullable=False)
    skills_score = db.Column(db.Float, nullable=False)
    behavior_score = db.Column(db.Float, nullable=False)
    attendance_score = db.Column(db.Float, nullable=False)
    overall_score = db.Column(db.Float, nullable=False)
    strengths = db.Column(db.Text, nullable=True)
    weaknesses = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(50), default='draft')  # draft, submitted, approved, rejected

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('received_evaluations', lazy=True))
    evaluator = db.relationship('User', foreign_keys=[evaluator_id], backref=db.backref('given_evaluations', lazy=True))

@app.route('/submit_evaluation', methods=['POST'])
def submit_evaluation():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        # حساب الدرجة الإجمالية
        performance_score = float(request.form['performance_score'])
        skills_score = float(request.form['skills_score'])
        behavior_score = float(request.form['behavior_score'])
        attendance_score = float(request.form['attendance_score'])
        
        overall_score = (performance_score + skills_score + behavior_score + attendance_score) / 4
        
        new_evaluation = Evaluation(
            user_id=request.form['user_id'],
            evaluator_id=session['user_id'],
            performance_score=performance_score,
            skills_score=skills_score,
            behavior_score=behavior_score,
            attendance_score=attendance_score,
            overall_score=overall_score,
            strengths=request.form.get('strengths'),
            weaknesses=request.form.get('weaknesses'),
            recommendations=request.form.get('recommendations'),
            status='submitted'
        )
        
        db.session.add(new_evaluation)
        db.session.commit()
        
        logging.info(f"تم تقديم تقييم جديد للمستخدم {new_evaluation.user.full_name} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تقديم التقييم بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تقديم التقييم: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تقديم التقييم'
        })

@app.route('/update_evaluation/<int:evaluation_id>', methods=['POST'])
def update_evaluation(evaluation_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    # التحقق من أن المستخدم هو من قام بالتقييم
    if evaluation.evaluator_id != session['user_id']:
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية لتعديل هذا التقييم'})
    
    try:
        # تحديث البيانات
        evaluation.performance_score = float(request.form['performance_score'])
        evaluation.skills_score = float(request.form['skills_score'])
        evaluation.behavior_score = float(request.form['behavior_score'])
        evaluation.attendance_score = float(request.form['attendance_score'])
        evaluation.overall_score = (evaluation.performance_score + evaluation.skills_score + 
                                  evaluation.behavior_score + evaluation.attendance_score) / 4
        evaluation.strengths = request.form.get('strengths')
        evaluation.weaknesses = request.form.get('weaknesses')
        evaluation.recommendations = request.form.get('recommendations')
        
        db.session.commit()
        
        logging.info(f"تم تحديث التقييم {evaluation_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تحديث التقييم بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تحديث التقييم: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تحديث التقييم'
        })

@app.route('/approve_evaluation/<int:evaluation_id>', methods=['POST'])
def approve_evaluation(evaluation_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية لاعتماد التقييمات'})
    
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    try:
        evaluation.status = 'approved'
        db.session.commit()
        
        logging.info(f"تم اعتماد التقييم {evaluation_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم اعتماد التقييم بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء اعتماد التقييم: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء اعتماد التقييم'
        })

@app.route('/reject_evaluation/<int:evaluation_id>', methods=['POST'])
def reject_evaluation(evaluation_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية لرفض التقييمات'})
    
    evaluation = Evaluation.query.get_or_404(evaluation_id)
    
    try:
        evaluation.status = 'rejected'
        db.session.commit()
        
        logging.info(f"تم رفض التقييم {evaluation_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم رفض التقييم بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء رفض التقييم: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء رفض التقييم'
        })

@app.route('/statistics')
def get_statistics():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية لعرض الإحصائيات'})
    
    try:
        # إحصائيات المستخدمين
        total_users = User.query.count()
        active_users = User.query.filter_by(is_active=True).count()
        users_by_role = db.session.query(User.roles, db.func.count(User.id)).group_by(User.roles).all()
        
        # إحصائيات الوظائف
        total_jobs = Job.query.count()
        jobs_by_status = db.session.query(Job.status, db.func.count(Job.id)).group_by(Job.status).all()
        
        # إحصائيات التقييمات
        total_evaluations = Evaluation.query.count()
        evaluations_by_status = db.session.query(Evaluation.status, db.func.count(Evaluation.id)).group_by(Evaluation.status).all()
        avg_overall_score = db.session.query(db.func.avg(Evaluation.overall_score)).scalar() or 0
        
        # إحصائيات البرامج التدريبية
        total_programs = TrainingProgram.query.count()
        active_programs = TrainingProgram.query.filter_by(status='active').count()
        total_registrations = TrainingRegistration.query.count()
        
        return jsonify({
            'success': True,
            'data': {
                'users': {
                    'total': total_users,
                    'active': active_users,
                    'by_role': dict(users_by_role)
                },
                'jobs': {
                    'total': total_jobs,
                    'by_status': dict(jobs_by_status)
                },
                'evaluations': {
                    'total': total_evaluations,
                    'by_status': dict(evaluations_by_status),
                    'average_score': round(avg_overall_score, 2)
                },
                'training': {
                    'total_programs': total_programs,
                    'active_programs': active_programs,
                    'total_registrations': total_registrations
                }
            }
        })
    except Exception as e:
        logging.error(f"خطأ أثناء جلب الإحصائيات: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء جلب الإحصائيات'
        })

@app.route('/generate_report', methods=['POST'])
def generate_report():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({'success': False, 'message': 'ليس لديك صلاحية لإنشاء التقارير'})
    
    try:
        report_type = request.form.get('report_type')
        start_date = datetime.strptime(request.form.get('start_date'), '%Y-%m-%d')
        end_date = datetime.strptime(request.form.get('end_date'), '%Y-%m-%d')
        
        if report_type == 'users':
            # تقرير المستخدمين
            users = User.query.filter(
                User.created_at >= start_date,
                User.created_at <= end_date
            ).all()
            
            report_data = [{
                'id': user.id,
                'full_name': user.full_name,
                'email': user.email,
                'roles': user.roles,
                'is_active': user.is_active,
                'created_at': user.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for user in users]
            
        elif report_type == 'jobs':
            # تقرير الوظائف
            jobs = Job.query.filter(
                Job.created_at >= start_date,
                Job.created_at <= end_date
            ).all()
            
            report_data = [{
                'id': job.id,
                'title': job.title,
                'department': job.department,
                'status': job.status,
                'created_by': job.created_by,
                'created_at': job.created_at.strftime('%Y-%m-%d %H:%M:%S')
            } for job in jobs]
            
        elif report_type == 'evaluations':
            # تقرير التقييمات
            evaluations = Evaluation.query.filter(
                Evaluation.evaluation_date >= start_date,
                Evaluation.evaluation_date <= end_date
            ).all()
            
            report_data = [{
                'id': eval.id,
                'user': eval.user.full_name,
                'evaluator': eval.evaluator.full_name,
                'overall_score': eval.overall_score,
                'status': eval.status,
                'evaluation_date': eval.evaluation_date.strftime('%Y-%m-%d %H:%M:%S')
            } for eval in evaluations]
            
        elif report_type == 'training':
            # تقرير البرامج التدريبية
            programs = TrainingProgram.query.filter(
                TrainingProgram.created_at >= start_date,
                TrainingProgram.created_at <= end_date
            ).all()
            
            report_data = [{
                'id': program.id,
                'title': program.title,
                'start_date': program.start_date.strftime('%Y-%m-%d'),
                'end_date': program.end_date.strftime('%Y-%m-%d'),
                'status': program.status,
                'registrations_count': len(program.registrations)
            } for program in programs]
            
        else:
            return jsonify({
                'success': False,
                'message': 'نوع التقرير غير صالح'
            })
        
        # إنشاء ملف PDF للتقرير
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f'report_{report_type}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf')
        
        # هنا يمكنك استخدام مكتبة مثل reportlab أو weasyprint لإنشاء ملف PDF
        # هذا مثال بسيط باستخدام reportlab
        from reportlab.pdfgen import canvas
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        
        # تسجيل الخط العربي
        pdfmetrics.registerFont(TTFont('Arabic', 'path/to/arabic/font.ttf'))
        
        c = canvas.Canvas(pdf_path, pagesize=letter)
        c.setFont('Arabic', 12)
        
        # إضافة محتوى التقرير
        y = 750
        for item in report_data:
            for key, value in item.items():
                c.drawString(50, y, f"{key}: {value}")
                y -= 20
            y -= 20
        
        c.save()
        
        return jsonify({
            'success': True,
            'message': 'تم إنشاء التقرير بنجاح',
            'report_path': pdf_path
        })
        
    except Exception as e:
        logging.error(f"خطأ أثناء إنشاء التقرير: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء إنشاء التقرير'
        })

# نموذج الطلبات
class Request(db.Model):
    __tablename__ = 'requests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    request_type = db.Column(db.String(50), nullable=False)  # leave, transfer, promotion, etc.
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='pending')  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    attachments = db.Column(db.Text, nullable=True)  # JSON string of file paths
    notes = db.Column(db.Text, nullable=True)
    
    user = db.relationship('User', backref=db.backref('requests', lazy=True))

class RequestForward(db.Model):
    __tablename__ = 'request_forwards'
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, completed, rejected
    
    request = db.relationship('Request', backref=db.backref('forwards', lazy=True))
    from_user = db.relationship('User', foreign_keys=[from_user_id], backref=db.backref('forwarded_requests', lazy=True))
    to_user = db.relationship('User', foreign_keys=[to_user_id], backref=db.backref('received_forwards', lazy=True))

class RequestReturn(db.Model):
    __tablename__ = 'request_returns'
    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey('requests.id'), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reason = db.Column(db.Text, nullable=False)  # سبب الإرجاع
    notes = db.Column(db.Text, nullable=True)  # ملاحظات إضافية
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='pending')  # pending, acknowledged
    
    request = db.relationship('Request', backref=db.backref('returns', lazy=True))
    from_user = db.relationship('User', foreign_keys=[from_user_id], backref=db.backref('returned_requests', lazy=True))
    to_user = db.relationship('User', foreign_keys=[to_user_id], backref=db.backref('received_returns', lazy=True))

@app.route('/submit_request', methods=['POST'])
def submit_request():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        # التحقق من الملفات المرفقة
        attachments = []
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            for file in files:
                if file and allowed_file(file.filename):
                    filename = save_uploaded_file(file)
                    attachments.append(filename)
        
        new_request = Request(
            user_id=session['user_id'],
            request_type=request.form['request_type'],
            title=request.form['title'],
            description=request.form['description'],
            attachments=json.dumps(attachments) if attachments else None
        )
        
        db.session.add(new_request)
        db.session.commit()
        
        logging.info(f"تم تقديم طلب جديد من المستخدم {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تقديم الطلب بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تقديم الطلب: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تقديم الطلب'
        })

@app.route('/update_request/<int:request_id>', methods=['POST'])
def update_request(request_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    request_obj = Request.query.get_or_404(request_id)
    
    # التحقق من أن المستخدم هو صاحب الطلب
    if request_obj.user_id != session['user_id']:
        return jsonify({
            'success': False,
            'message': 'ليس لديك صلاحية لتعديل هذا الطلب'
        })
    
    try:
        # تحديث البيانات
        request_obj.title = request.form.get('title', request_obj.title)
        request_obj.description = request.form.get('description', request_obj.description)
        
        # تحديث المرفقات
        if 'attachments' in request.files:
            files = request.files.getlist('attachments')
            attachments = []
            for file in files:
                if file and allowed_file(file.filename):
                    filename = save_uploaded_file(file)
                    attachments.append(filename)
            if attachments:
                request_obj.attachments = json.dumps(attachments)
        
        db.session.commit()
        
        logging.info(f"تم تحديث الطلب {request_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تحديث الطلب بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تحديث الطلب: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تحديث الطلب'
        })

@app.route('/process_request/<int:request_id>', methods=['POST'])
def process_request(request_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({
            'success': False,
            'message': 'ليس لديك صلاحية لمعالجة الطلبات'
        })
    
    request_obj = Request.query.get_or_404(request_id)
    
    try:
        new_status = request.form.get('status')
        notes = request.form.get('notes')
        
        if new_status not in ['approved', 'rejected']:
            return jsonify({
                'success': False,
                'message': 'حالة غير صالحة'
            })
        
        request_obj.status = new_status
        request_obj.notes = notes
        
        db.session.commit()
        
        logging.info(f"تم {new_status} الطلب {request_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': f'تم {new_status} الطلب بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء معالجة الطلب: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء معالجة الطلب'
        })

@app.route('/get_requests')
def get_requests():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        # التحقق من صلاحيات المستخدم
        allowed_roles = ['"governor"', '"general_admin"', '"central_admin"']
        user_roles = session['roles']
        
        if any(role in user_roles for role in allowed_roles):
            # للمدراء: عرض جميع الطلبات
            requests = Request.query.order_by(Request.created_at.desc()).all()
        else:
            # للمستخدمين العاديين: عرض طلباتهم فقط
            requests = Request.query.filter_by(user_id=session['user_id']).order_by(Request.created_at.desc()).all()
        
        requests_data = [{
            'id': req.id,
            'user': req.user.full_name,
            'request_type': req.request_type,
            'title': req.title,
            'description': req.description,
            'status': req.status,
            'created_at': req.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': req.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'attachments': json.loads(req.attachments) if req.attachments else [],
            'notes': req.notes
        } for req in requests]
        
        return jsonify({
            'success': True,
            'data': requests_data
        })
    except Exception as e:
        logging.error(f"خطأ أثناء جلب الطلبات: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء جلب الطلبات'
        })

# نموذج المقابلات
class Interview(db.Model):
    __tablename__ = 'interviews'
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), nullable=False)
    candidate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    interviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    scheduled_date = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # in minutes
    location = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default='scheduled')  # scheduled, completed, cancelled
    notes = db.Column(db.Text, nullable=True)
    feedback = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    job = db.relationship('Job', backref=db.backref('interviews', lazy=True))
    candidate = db.relationship('User', foreign_keys=[candidate_id], backref=db.backref('candidate_interviews', lazy=True))
    interviewer = db.relationship('User', foreign_keys=[interviewer_id], backref=db.backref('interviewer_interviews', lazy=True))

@app.route('/schedule_interview', methods=['POST'])
def schedule_interview():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"', '"hr_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({
            'success': False,
            'message': 'ليس لديك صلاحية لجدولة المقابلات'
        })
    
    try:
        # التحقق من تداخل المواعيد
        scheduled_date = datetime.strptime(request.form['scheduled_date'], '%Y-%m-%d %H:%M')
        duration = int(request.form['duration'])
        interviewer_id = int(request.form['interviewer_id'])
        
        # التحقق من تداخل مواعيد المقابلات للمقابل
        existing_interview = Interview.query.filter(
            Interview.interviewer_id == interviewer_id,
            Interview.scheduled_date <= scheduled_date + timedelta(minutes=duration),
            Interview.scheduled_date + timedelta(minutes=Interview.duration) >= scheduled_date
        ).first()
        
        if existing_interview:
            return jsonify({
                'success': False,
                'message': 'هناك مقابلة أخرى مجدولة في نفس الوقت'
            })
        
        new_interview = Interview(
            job_id=request.form['job_id'],
            candidate_id=request.form['candidate_id'],
            interviewer_id=interviewer_id,
            scheduled_date=scheduled_date,
            duration=duration,
            location=request.form['location'],
            notes=request.form.get('notes')
        )
        
        db.session.add(new_interview)
        db.session.commit()
        
        logging.info(f"تم جدولة مقابلة جديدة بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم جدولة المقابلة بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء جدولة المقابلة: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء جدولة المقابلة'
        })

@app.route('/update_interview/<int:interview_id>', methods=['POST'])
def update_interview(interview_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    # التحقق من صلاحيات المستخدم
    allowed_roles = ['"governor"', '"general_admin"', '"central_admin"', '"hr_admin"']
    user_roles = session['roles']
    if not any(role in user_roles for role in allowed_roles):
        return jsonify({
            'success': False,
            'message': 'ليس لديك صلاحية لتعديل المقابلات'
        })
    
    interview = Interview.query.get_or_404(interview_id)
    
    try:
        # التحقق من تداخل المواعيد إذا تم تغيير الموعد
        if 'scheduled_date' in request.form:
            new_date = datetime.strptime(request.form['scheduled_date'], '%Y-%m-%d %H:%M')
            duration = int(request.form.get('duration', interview.duration))
            
            existing_interview = Interview.query.filter(
                Interview.interviewer_id == interview.interviewer_id,
                Interview.id != interview_id,
                Interview.scheduled_date <= new_date + timedelta(minutes=duration),
                Interview.scheduled_date + timedelta(minutes=Interview.duration) >= new_date
            ).first()
            
            if existing_interview:
                return jsonify({
                    'success': False,
                    'message': 'هناك مقابلة أخرى مجدولة في نفس الوقت'
                })
            
            interview.scheduled_date = new_date
            interview.duration = duration
        
        # تحديث البيانات الأخرى
        interview.location = request.form.get('location', interview.location)
        interview.notes = request.form.get('notes', interview.notes)
        
        db.session.commit()
        
        logging.info(f"تم تحديث المقابلة {interview_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تحديث المقابلة بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تحديث المقابلة: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تحديث المقابلة'
        })

@app.route('/submit_interview_feedback/<int:interview_id>', methods=['POST'])
def submit_interview_feedback(interview_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    interview = Interview.query.get_or_404(interview_id)
    
    # التحقق من أن المستخدم هو المقابل
    if interview.interviewer_id != session['user_id']:
        return jsonify({
            'success': False,
            'message': 'ليس لديك صلاحية لتقديم التغذية الراجعة'
        })
    
    try:
        interview.feedback = request.form['feedback']
        interview.status = 'completed'
        
        db.session.commit()
        
        logging.info(f"تم تقديم تغذية راجعة للمقابلة {interview_id} بواسطة {session['full_name']}")
        return jsonify({
            'success': True,
            'message': 'تم تقديم التغذية الراجعة بنجاح'
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"خطأ أثناء تقديم التغذية الراجعة: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء تقديم التغذية الراجعة'
        })

@app.route('/get_interviews')
def get_interviews():
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'يرجى تسجيل الدخول أولاً'})
    
    try:
        # التحقق من صلاحيات المستخدم
        allowed_roles = ['"governor"', '"general_admin"', '"central_admin"', '"hr_admin"']
        user_roles = session['roles']
        
        if any(role in user_roles for role in allowed_roles):
            # للمدراء: عرض جميع المقابلات
            interviews = Interview.query.order_by(Interview.scheduled_date.desc()).all()
        else:
            # للمستخدمين العاديين: عرض مقابلاتهم فقط
            interviews = Interview.query.filter(
                (Interview.candidate_id == session['user_id']) |
                (Interview.interviewer_id == session['user_id'])
            ).order_by(Interview.scheduled_date.desc()).all()
        
        interviews_data = [{
            'id': interview.id,
            'job': interview.job.title,
            'candidate': interview.candidate.full_name,
            'interviewer': interview.interviewer.full_name,
            'scheduled_date': interview.scheduled_date.strftime('%Y-%m-%d %H:%M'),
            'duration': interview.duration,
            'location': interview.location,
            'status': interview.status,
            'notes': interview.notes,
            'feedback': interview.feedback,
            'created_at': interview.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': interview.updated_at.strftime('%Y-%m-%d %H:%M:%S')
        } for interview in interviews]
        
        return jsonify({
            'success': True,
            'data': interviews_data
        })
    except Exception as e:
        logging.error(f"خطأ أثناء جلب المقابلات: {e}")
        return jsonify({
            'success': False,
            'message': 'حدث خطأ أثناء جلب المقابلات'
        })

# معالجة الأخطاء
@app.errorhandler(400)
def bad_request(error):
    logging.error(f"خطأ 400: {error}")
    return render_template('errors/400.html'), 400

@app.errorhandler(401)
def unauthorized(error):
    logging.error(f"خطأ 401: {error}")
    return render_template('errors/401.html'), 401

@app.errorhandler(403)
def forbidden(error):
    logging.error(f"خطأ 403: {error}")
    return render_template('errors/403.html'), 403

@app.errorhandler(404)
def page_not_found(error):
    logging.error(f"خطأ 404: {error}")
    return render_template('errors/404.html'), 404

@app.errorhandler(405)
def method_not_allowed(error):
    logging.error(f"طريقة غير مسموح بها: {error}")
    return jsonify({
        'success': False,
        'message': 'طريقة غير مسموح بها',
        'error': str(error)
    }), 405

@app.errorhandler(500)
def internal_server_error(error):
    logging.error(f"خطأ 500: {error}")
    return render_template('errors/500.html'), 500

# معالجة أخطاء قاعدة البيانات
@app.errorhandler(db.exc.SQLAlchemyError)
def handle_db_error(error):
    db.session.rollback()
    logging.error(f"خطأ في قاعدة البيانات: {error}")
    return jsonify({
        'success': False,
        'message': 'حدث خطأ في قاعدة البيانات',
        'error': str(error)
    }), 500

# معالجة أخطاء التحقق من الصحة
@app.errorhandler(ValueError)
def handle_validation_error(error):
    logging.error(f"خطأ في التحقق من الصحة: {error}")
    return jsonify({
        'success': False,
        'message': 'خطأ في البيانات المدخلة',
        'error': str(error)
    }), 400

# معالجة أخطاء الملفات
@app.errorhandler(IOError)
def handle_file_error(error):
    logging.error(f"خطأ في الملفات: {error}")
    return jsonify({
        'success': False,
        'message': 'حدث خطأ في معالجة الملفات',
        'error': str(error)
    }), 500

# معالجة أخطاء JSON
@app.errorhandler(json.JSONDecodeError)
def handle_json_error(error):
    logging.error(f"خطأ في تنسيق JSON: {error}")
    return jsonify({
        'success': False,
        'message': 'خطأ في تنسيق البيانات',
        'error': str(error)
    }), 400

# معالجة أخطاء التواريخ
@app.errorhandler(ValueError)
def handle_date_error(error):
    if 'time data' in str(error):
        logging.error(f"خطأ في تنسيق التاريخ: {error}")
        return jsonify({
            'success': False,
            'message': 'خطأ في تنسيق التاريخ',
            'error': str(error)
        }), 400
    raise error

# معالجة أخطاء الصلاحيات
class PermissionError(Exception):
    pass

@app.errorhandler(PermissionError)
def handle_permission_error(error):
    logging.error(f"خطأ في الصلاحيات: {error}")
    return jsonify({
        'success': False,
        'message': str(error),
        'error': 'خطأ في الصلاحيات'
    }), 403

# معالجة أخطاء التحقق من الملفات
class FileValidationError(Exception):
    pass

@app.errorhandler(FileValidationError)
def handle_file_validation_error(error):
    logging.error(f"خطأ في التحقق من الملف: {error}")
    return jsonify({
        'success': False,
        'message': str(error),
        'error': 'خطأ في التحقق من الملف'
    }), 400

# معالجة أخطاء تداخل المواعيد
class ScheduleConflictError(Exception):
    pass

@app.errorhandler(ScheduleConflictError)
def handle_schedule_conflict_error(error):
    logging.error(f"خطأ في تداخل المواعيد: {error}")
    return jsonify({
        'success': False,
        'message': str(error),
        'error': 'خطأ في تداخل المواعيد'
    }), 400

# معالجة أخطاء التحقق من الحالة
class StatusValidationError(Exception):
    pass

@app.errorhandler(StatusValidationError)
def handle_status_validation_error(error):
    logging.error(f"خطأ في التحقق من الحالة: {error}")
    return jsonify({
        'success': False,
        'message': str(error),
        'error': 'خطأ في التحقق من الحالة'
    }), 400

# إضافة تعريفات الأخطاء المخصصة
class ConfigurationError(Exception):
    pass

class DatabaseError(Exception):
    pass

# تهيئة قاعدة البيانات بعد تعريف جميع النماذج
init_db()

if __name__ == "__main__":
    try:
        # تهيئة قاعدة البيانات
        init_db()
        
        # تشغيل الخادم في خلفية منفصلة
        def start_server():
            app.run(host='127.0.0.1', port=5000, debug=False)
        
        # بدء تشغيل الخادم في خلفية
        server_thread = Thread(target=start_server)
        server_thread.daemon = True  # هذا يضمن إغلاق الخيط عند إغلاق البرنامج الرئيسي
        server_thread.start()
        
        # انتظار قليلاً للتأكد من بدء الخادم
        import time
        time.sleep(1)
        
        # فتح نافذة التطبيق باستخدام pywebview
        webview.create_window(
            title="النظام الإلكتروني للوظائف القيادية والإشرافية",
            url="http://127.0.0.1:5000",
            width=1200,
            height=800,
            resizable=True,
            min_size=(800, 600),
            background_color='#FFFFFF',
            text_select=True
        )
        
        # بدء تشغيل النافذة - سيتوقف البرنامج عند إغلاق النافذة
        webview.start()
        
        # عند إغلاق النافذة، سيتم الوصول إلى هنا وإنهاء البرنامج
        print("تم إغلاق التطبيق")
        sys.exit(0)
    except Exception as e:
        logging.error(f"خطأ أثناء تشغيل التطبيق: {e}")
        sys.exit(1)