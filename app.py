from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///profitbliss.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Gmail SMTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = "yourgmail@gmail.com"      # replace
app.config['MAIL_PASSWORD'] = "your-app-password"        # replace with Gmail App Password

db = SQLAlchemy(app)
login_manager = LoginManager(app)
mail = Mail(app)

# ---------------- Models ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    country = db.Column(db.String(100))
    balance = db.Column(db.Float, default=0.0)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)

class Deposit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    coin = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default="pending")

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float, nullable=False)
    wallet_address = db.Column(db.String(255))
    status = db.Column(db.String(50), default="pending")

class Plan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    stake = db.Column(db.Float)
    daily_roi = db.Column(db.Float)  # percentage (e.g. 20 for 20%)
    duration = db.Column(db.Integer)  # in days

class ActivePlan(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    plan_id = db.Column(db.Integer, db.ForeignKey('plan.id'))
    start_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    end_date = db.Column(db.DateTime)
    last_roi_date = db.Column(db.DateTime)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---------------- Utility ----------------
def create_plans():
    """Create investment plans if not exist."""
    if not Plan.query.first():
        plans = [
            Plan(name="Basic", stake=50, daily_roi=20, duration=30),
            Plan(name="Gold", stake=100, daily_roi=35, duration=30),
            Plan(name="Master", stake=200, daily_roi=50, duration=30),
            Plan(name="Premium", stake=300, daily_roi=75, duration=30),
        ]
        db.session.add_all(plans)
        db.session.commit()

def credit_daily_roi():
    """Credit ROI daily to active users."""
    now = datetime.datetime.utcnow()
    active_plans = ActivePlan.query.all()
    for ap in active_plans:
        plan = Plan.query.get(ap.plan_id)
        user = User.query.get(ap.user_id)
        if user and now.date() > (ap.last_roi_date.date() if ap.last_roi_date else ap.start_date.date()):
            if now <= ap.end_date:
                roi_amount = (plan.stake * plan.daily_roi) / 100
                user.balance += roi_amount
                ap.last_roi_date = now
    db.session.commit()

# ---------------- Routes ----------------
@app.route('/')
def index():
    return render_template("index.html")

@app.route('/signup', methods=['GET','POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        country = request.form['country']
        referral = request.form.get('referral', '')

        if referral and referral != "tmdf28dns":
            flash("Invalid referral code!", "danger")
            return redirect(url_for('signup'))

        user = User(email=email, password=password, country=country)
        db.session.add(user)
        db.session.commit()

        token = str(user.id)
        msg = Message("Verify your Profit Bliss account",
                      sender="yourgmail@gmail.com",
                      recipients=[email])
        msg.body = f"Click to verify your account: http://127.0.0.1:5000/verify/{token}"
        mail.send(msg)

        flash("Check your email to verify your account.", "info")
        return redirect(url_for('login'))
    return render_template("signup.html")

@app.route('/verify/<token>')
def verify(token):
    user = User.query.get(int(token))
    if user:
        user.is_verified = True
        db.session.commit()
        flash("Account verified! You can now login.", "success")
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            if not user.is_verified:
                flash("Please verify your email first.", "warning")
                return redirect(url_for('login'))

            login_user(user)
            return redirect(url_for('dashboard'))
        else:
            flash("Invalid credentials.", "danger")
    return render_template("login.html")

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    credit_daily_roi()  # auto credit on each dashboard visit
    plans = Plan.query.all()
    active_plans = ActivePlan.query.filter_by(user_id=current_user.id).all()
    return render_template("dashboard.html", balance=current_user.balance,
                           plans=plans, active_plans=active_plans)

@app.route('/subscribe/<int:plan_id>')
@login_required
def subscribe(plan_id):
    plan = Plan.query.get(plan_id)
    if current_user.balance < plan.stake:
        flash("Insufficient balance! Deposit now.", "danger")
        return redirect(url_for('deposit'))

    current_user.balance -= plan.stake
    ap = ActivePlan(user_id=current_user.id, plan_id=plan.id,
                    end_date=datetime.datetime.utcnow() + datetime.timedelta(days=plan.duration),
                    last_roi_date=datetime.datetime.utcnow())
    db.session.add(ap)
    db.session.commit()
    flash(f"Subscribed to {plan.name} plan.", "success")
    return redirect(url_for('dashboard'))

@app.route('/deposit', methods=['GET','POST'])
@login_required
def deposit():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        coin = request.form['coin']
        if amount < 50:
            flash("Minimum deposit is $50.", "danger")
            return redirect(url_for('deposit'))

        dep = Deposit(user_id=current_user.id, amount=amount, coin=coin)
        db.session.add(dep)
        db.session.commit()
        flash("Deposit submitted. Awaiting admin approval.", "info")
        return redirect(url_for('dashboard'))
    return render_template("deposit.html")

@app.route('/withdraw', methods=['GET','POST'])
@login_required
def withdraw():
    if request.method == 'POST':
        amount = float(request.form['amount'])
        wallet = request.form['wallet']
        if amount < 70:
            flash("Minimum withdrawal is $70.", "danger")
            return redirect(url_for('withdraw'))
        if amount > current_user.balance:
            flash("Insufficient balance.", "danger")
            return redirect(url_for('withdraw'))

        wd = Withdrawal(user_id=current_user.id, amount=amount, wallet_address=wallet)
        db.session.add(wd)
        db.session.commit()
        flash("Withdrawal submitted. Awaiting admin approval.", "info")
        return redirect(url_for('dashboard'))
    return render_template("withdraw.html")

# ---------------- Admin ----------------
@app.route('/admin')
@login_required
def admin():
    if not current_user.is_admin:
        flash("Unauthorized!", "danger")
        return redirect(url_for('dashboard'))
    deposits = Deposit.query.filter_by(status="pending").all()
    withdrawals = Withdrawal.query.filter_by(status="pending").all()
    return render_template("admin.html", deposits=deposits, withdrawals=withdrawals)

@app.route('/admin/approve/deposit/<int:dep_id>')
@login_required
def approve_deposit(dep_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    dep = Deposit.query.get(dep_id)
    if dep and dep.status == "pending":
        dep.status = "approved"
        user = User.query.get(dep.user_id)
        user.balance += dep.amount
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/reject/deposit/<int:dep_id>')
@login_required
def reject_deposit(dep_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    dep = Deposit.query.get(dep_id)
    if dep:
        dep.status = "rejected"
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/approve/withdraw/<int:wd_id>')
@login_required
def approve_withdraw(wd_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    wd = Withdrawal.query.get(wd_id)
    if wd and wd.status == "pending":
        wd.status = "approved"
        user = User.query.get(wd.user_id)
        user.balance -= wd.amount
        db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/reject/withdraw/<int:wd_id>')
@login_required
def reject_withdraw(wd_id):
    if not current_user.is_admin: return redirect(url_for('dashboard'))
    wd = Withdrawal.query.get(wd_id)
    if wd:
        wd.status = "rejected"
        db.session.commit()
    return redirect(url_for('admin'))

# ---------------- Run ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        create_plans()
        if not User.query.filter_by(email="admin@profitbliss.com").first():
            admin_user = User(
                email="admin@profitbliss.com",
                password=generate_password_hash("admin123"),
                is_verified=True,
                is_admin=True
            )
            db.session.add(admin_user)
            db.session.commit()
    app.run(debug=True)
