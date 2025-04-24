# Import optimizations - remove duplicate imports and organize them
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
import logging
import os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from weasyprint import HTML
import io
import warnings
from functools import wraps


# Suppress warnings more efficiently
warnings.filterwarnings('ignore', category=Warning)
warnings.filterwarnings('ignore', message='.*UWP app.*')
warnings.filterwarnings('ignore', message='.*GLib-GIO.*')
warnings.filterwarnings('ignore', message='.*extensions but has no verbs.*')

# Improved logging configuration with file handler
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'app.log')

# Configure file handler and console handler
file_handler = logging.FileHandler(log_file, encoding='utf-8')
console_handler = logging.StreamHandler()

# Set formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure logger
logger = logging.getLogger('app_logger')
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Flask app configuration with better security
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(24))  # Better to use environment variable
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit upload size to 16MB

# Initialize database
db = SQLAlchemy(app)


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

# ... existing code ...

# Refactored PDF generation function with error handling and caching
def generate_pdf(data=None, data_type=None):
    try:
        if data is None:
            html_content = render_template('no_data_pdf.html')
        elif data_type == 'committee':
            html_content = render_template('committee_pdf.html', committee=data)
        elif data_type == 'appointment':
            html_content = render_template('appointment_pdf.html', appointment=data)
        else:
            html_content = render_template('no_data_pdf.html')
        
        pdf_buffer = io.BytesIO()
        HTML(string=html_content).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        return pdf_buffer
    except Exception as e:
        logger.error(f"Error generating PDF: {e}")
        # Return a simple error PDF
        error_html = f"<html><body><h1>Error generating PDF</h1><p>{str(e)}</p></body></html>"
        pdf_buffer = io.BytesIO()
        HTML(string=error_html).write_pdf(pdf_buffer)
        pdf_buffer.seek(0)
        return pdf_buffer

# Improved authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('يرجى تسجيل الدخول أولاً', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function


# Role-based access control decorator
def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'user_id' not in session:
                flash('يرجى تسجيل الدخول أولاً', 'error')
                return redirect(url_for('index'))
            
            user_roles = session.get('roles', '[]')
            if not any(role in user_roles for role in allowed_roles):
                flash('ليس لديك صلاحية للوصول إلى هذه الصفحة', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# ... existing code ...

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

# دالة لإنشاء قاعدة بيانات مع بيانات عينة
def create_sample():
    logging.info("إنشاء قاعدة بيانات مع بيانات عينة...")
    db.create_all()

    if User.query.count() > 0:
        logging.info("قاعدة البيانات تحتوي على مستخدمين بالفعل، لن يتم إضافة بيانات عينة.")
        return

    users = [
        User(full_name='احمد محمود', email='ahmed.mahmoud@system.com', roles='["general_department_member"]', governorate='الإسكندرية', active=True),
        User(full_name='محمد علي', email='mohamed.ali@system.com', roles='["general_admin"]', governorate='الجيزة', active=True),
        User(full_name='فاطمة حسن', email='fatma.hassan@system.com', roles='["central_admin"]', governorate='الدقهلية', active=True),
        User(full_name='خالد سعيد', email='khaled.saeed@system.com', roles='["directorate_admin"]', governorate='أسيوط', active=True),
        User(full_name='علي يوسف', email='ali.youssef@system.com', roles='["governor"]', governorate='القاهرة', active=True),
        User(full_name='سارة احمد', email='sara.ahmed@system.com', roles='["central_authority_head"]', governorate='الشرقية', active=True),
        User(full_name='يوسف خالد', email='youssef.khaled@system.com', roles='["regular_user"]', governorate='المنوفية', active=True),
        User(full_name='منى حسن', email='mona.hassan@system.com', roles='["evaluation_committee_member"]', governorate='الغربية', active=True),
        User(full_name='احمد سمير', email='ahmed.samir@system.com', roles='["training_center_member"]', governorate='سوهاج', active=True),
    ]

    passwords = ['GDM001', 'GEN001', 'CEN001', 'DIR001', 'GOV001', 'CAH001', 'REG001', 'EVAL001', 'TCM001']
    for user, password in zip(users, passwords):
        user.set_password(password)
        db.session.add(user)
        logging.info(f"تم إضافة المستخدم: {user.full_name}")

    db.session.commit()
    logging.info("تم إنشاء قاعدة البيانات وبيانات العينة بنجاح!")

with app.app_context():
    create_sample()

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
                roles='["regular_user"]',
                governorate=governorate,
                active=False
            )
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            logging.info(f"تم تسجيل المستخدم {username} بنجاح.")
            flash('تم التسجيل بنجاح، وانتظر السماح لك بالدخول للمنصة', 'success')
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

# ... existing code ...

@app.route('/profile')
@login_required
def profile():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('المستخدم غير موجود', 'error')
        return redirect(url_for('logout'))
    
    return render_template('profile.html', 
                          full_name=user.full_name,
                          email=user.email,
                          roles=user.roles,
                          governorate=user.governorate,
                          created_at=user.created_at)

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    user = db.session.get(User, session['user_id'])
    if not user:
        flash('المستخدم غير موجود', 'error')
        return redirect(url_for('logout'))
    
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    if not check_password_hash(user.password, current_password):
        flash('كلمة المرور الحالية غير صحيحة', 'error')
        return redirect(url_for('profile'))

    if len(new_password) < 6:
        flash('كلمة المرور الجديدة يجب أن تكون 6 أحرف على الأقل', 'error')
        return redirect(url_for('profile'))

    if new_password != confirm_password:
        flash('كلمة المرور الجديدة وتأكيدها غير متطابقين', 'error')
        return redirect(url_for('profile'))

    try:
        user.set_password(new_password)
        db.session.commit()
        flash('تم تغيير كلمة المرور بنجاح', 'success')
        logger.info(f"تم تغيير كلمة المرور للمستخدم {user.full_name}")
    except Exception as e:
        db.session.rollback()
        flash('حدث خطأ أثناء تغيير كلمة المرور', 'error')
        logger.error(f"خطأ في تغيير كلمة المرور: {e}")

    return redirect(url_for('profile'))

# ... existing code ... 
    
# ... existing code ...

@app.route('/pdf/<action>')
@login_required
def handle_pdf(action):
    if action not in ['view', 'print', 'download']:
        flash('إجراء غير صالح', 'error')
        return redirect(url_for('dashboard'))
    
    decision_type = request.args.get('type', 'committee')
    
    try:
        # Get the appropriate data based on decision type
        if decision_type == 'appointment':
            latest = AppointmentDecision.query.filter_by(
                status='created', 
                user_id=session['user_id']
            ).order_by(AppointmentDecision.created_at.desc()).first()
            
            if latest:
                data = {
                    'decision_number': latest.decision_number,
                    'decision_date': latest.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest.governorate,
                    'announcement_number': latest.announcement_number,
                    'candidate_code': latest.candidate_code,
                    'article_one_text': latest.article_one_text,
                    'article_two_text': latest.article_two_text,
                    'article_three_text': latest.article_three_text,
                    'competent_authority': latest.competent_authority,
                    'authority_approval': latest.authority_approval,
                    'files': {
                        'announcement_file': latest.announcement_file,
                        'candidate_file': latest.candidate_file,
                        'decision_file': latest.decision_file
                    },
                    'type': 'appointment'
                }
                filename = f"appointment_{latest.decision_number}.pdf"
            else:
                data = None
                filename = "no_data.pdf"
                
        elif decision_type == 'committee':
            latest = LeadershipCommittee.query.filter_by(
                status='created', 
                user_id=session['user_id']
            ).order_by(LeadershipCommittee.created_at.desc()).first()
            
            if latest:
                data = {
                    'decision_number': latest.decision_number,
                    'decision_date': latest.decision_date.strftime('%Y-%m-%d'),
                    'governorate': latest.governorate,
                    'preamble': latest.preamble,
                    'article_one_text': latest.article_one_text,
                    # ... rest of committee data ...
                    'competent_authority': latest.competent_authority,
                    'authority_approval': latest.authority_approval
                }
                filename = f"decision_{latest.decision_number}.pdf"
            else:
                data = None
                filename = "no_data.pdf"
        else:
            data = None
            filename = "no_data.pdf"
        
        # Generate PDF
        pdf_buffer = generate_pdf(data, data_type=decision_type)
        
        # Create response
        response = make_response(pdf_buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        
        # Set disposition based on action
        if action == 'download':
            response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        else:  # view or print
            response.headers['Content-Disposition'] = f'inline; filename={filename}'
            
        return response
        
    except Exception as e:
        logger.error(f"خطأ أثناء إنشاء ملف PDF: {e}")
        flash(f'حدث خطأ أثناء إنشاء ملف PDF: {e}', 'error')
        return redirect(url_for('dashboard'))

# ... existing code ...

    
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

@app.route('/inbox')
def inbox():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('inbox.html')

@app.route('/outbox')
def outbox():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('outbox.html')

@app.route('/job_results')
def job_results():
    if 'user_id' not in session:
        flash('يرجى تسجيل الدخول أولاً', 'error')
        return redirect(url_for('index'))
    return render_template('job_results.html')

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
    return render_template('jobs_in_progress.html')

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

if __name__ == '__main__':
    app.run(debug=True)