"""
banking_app/app.py
==================
Flask web application for the BankingDB PostgreSQL database.

Roles:
  customer  — logs in, sees their own accounts and transactions
  admin     — logs in, sees all customers, accounts, and summary stats

Setup:
  pip install -r requirements.txt
  python app.py

The app auto-creates an app_users table and seeds demo credentials
on first run if they don't already exist.
"""

import os
import hashlib
import secrets
from functools import wraps
from datetime import date, datetime
from pathlib import Path

import psycopg2
import psycopg2.extras
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g)

# ── App config ────────────────────────────────────────────────────
# Resolve template and static paths relative to this file so the app
# works regardless of which directory it is launched from.
BASE_DIR = Path(__file__).resolve().parent

app = Flask(__name__,
            template_folder=str(BASE_DIR / 'templates'),
            static_folder=str(BASE_DIR / 'static'))
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ── Database config ───────────────────────────────────────────────
DB_CONFIG = {
    'host':     os.environ.get('DB_HOST',     'localhost'),
    'port':     int(os.environ.get('DB_PORT', 5433)),
    'dbname':   os.environ.get('DB_NAME',     'bankingdb'),
    'user':     os.environ.get('DB_USER',     'bankadmin'),
    'password': os.environ.get('DB_PASSWORD', 'BankDBSecure123'),
}


# ══════════════════════════════════════════════════════════════════
# DATABASE HELPERS
# ══════════════════════════════════════════════════════════════════

def get_db():
    """Return a per-request psycopg2 connection (stored on flask.g)."""
    if 'db' not in g:
        g.db = psycopg2.connect(**DB_CONFIG,
                                cursor_factory=psycopg2.extras.RealDictCursor)
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def query(sql, params=None, one=False):
    cur = get_db().cursor()
    cur.execute(sql, params or ())
    result = cur.fetchone() if one else cur.fetchall()
    return result


def execute(sql, params=None):
    conn = get_db()
    cur  = conn.cursor()
    cur.execute(sql, params or ())
    conn.commit()


# ── Password hashing ──────────────────────────────────────────────
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════════
# FIRST-RUN: create app_users table and seed demo accounts
# ══════════════════════════════════════════════════════════════════

SETUP_SQL = """
CREATE TABLE IF NOT EXISTS app_users (
    id           SERIAL      PRIMARY KEY,
    username     VARCHAR(60) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    role         VARCHAR(10) NOT NULL CHECK(role IN ('customer','admin')),
    customer_ssn CHAR(11)    REFERENCES Customer(ssn) ON DELETE CASCADE
);
"""

DEMO_USERS = [
    # (username,         password,            role,       customer_ssn)
    # ── Admin ─────────────────────────────────────────────────────────
    ('admin',            'admin123',          'admin',    None),
    # ── Customers — username = first name, password = FirstLast (no space)
    ('nancy.green',      'NancyGreen',        'customer', '101-01-0001'),
    ('oscar.brown',      'OscarBrown',        'customer', '202-02-0002'),
    ('paula.white',      'PaulaWhite',        'customer', '303-03-0003'),
    ('quinn.black',      'QuinnBlack',        'customer', '404-04-0004'),
    ('rachel.silver',    'RachelSilver',      'customer', '505-05-0005'),
    ('sam.gold',         'SamGold',           'customer', '606-06-0006'),
    ('tina.rose',        'TinaRose',          'customer', '707-07-0007'),
    ('umar.shah',        'UmarShah',          'customer', '808-08-0008'),
]


def init_app_users():
    """Create app_users table and populate demo credentials if empty."""
    try:
        conn = psycopg2.connect(**DB_CONFIG,
                                cursor_factory=psycopg2.extras.RealDictCursor)
        cur  = conn.cursor()
        cur.execute(SETUP_SQL)
        cur.execute("SELECT COUNT(*) AS n FROM app_users")
        if cur.fetchone()['n'] == 0:
            for username, password, role, ssn in DEMO_USERS:
                cur.execute(
                    "INSERT INTO app_users (username, password_hash, role, customer_ssn) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (username, hash_password(password), role, ssn)
                )
        conn.commit()
        conn.close()
        print("[OK] app_users table ready.")
    except Exception as e:
        print(f"[WARN] Could not initialise app_users: {e}")


# ══════════════════════════════════════════════════════════════════
# AUTH DECORATORS
# ══════════════════════════════════════════════════════════════════

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get('role') != 'admin':
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


# ══════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


# ── Login / Logout ────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = query(
            "SELECT * FROM app_users WHERE username = %s AND password_hash = %s",
            (username, hash_password(password)),
            one=True
        )

        if user:
            session.clear()
            session['user_id']      = user['id']
            session['username']     = user['username']
            session['role']         = user['role']
            session['customer_ssn'] = user['customer_ssn']
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ── Dashboard (role-router) ───────────────────────────────────────

@app.route('/dashboard')
@login_required
def dashboard():
    if session['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('customer_dashboard'))


# ── Register (Open Account) ───────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    # Always fetch branches for the form
    branches = query("SELECT branch_id, branch_name, city, address_state FROM Branch ORDER BY branch_name")

    if request.method == 'POST':
        # ── Collect form data ────────────────────────────────────
        first_name   = request.form.get('first_name',  '').strip()
        last_name    = request.form.get('last_name',   '').strip()
        ssn          = request.form.get('ssn',         '').strip()
        phone        = request.form.get('phone',       '').strip()
        apt_no       = request.form.get('apt_no',      '').strip() or None
        street_no    = request.form.get('street_no',   '').strip()
        street_name  = request.form.get('street_name', '').strip()
        city         = request.form.get('city',        '').strip()
        state        = request.form.get('state',       '').strip().upper()
        zip_code     = request.form.get('zip_code',    '').strip()
        branch_id    = request.form.get('branch_id',   type=int)
        account_type = request.form.get('account_type','').strip()
        username     = request.form.get('username',    '').strip()
        password     = request.form.get('password',   '')
        confirm_pw   = request.form.get('confirm_password', '')

        errors = []

        # ── Validate ─────────────────────────────────────────────
        import re
        if not first_name:
            errors.append('First name is required.')
        if not last_name:
            errors.append('Last name is required.')
        if not re.match(r'^\d{3}-\d{2}-\d{4}$', ssn):
            errors.append('SSN must be in the format XXX-XX-XXXX.')
        if not phone:
            errors.append('Phone number is required.')
        if not street_no:
            errors.append('Street number is required.')
        if not street_name:
            errors.append('Street name is required.')
        if not city:
            errors.append('City is required.')
        if not state or len(state) != 2:
            errors.append('State must be a 2-letter abbreviation (e.g. NY).')
        if not zip_code:
            errors.append('Zip code is required.')
        if not branch_id:
            errors.append('Please select a branch.')
        if account_type not in ('SAVINGS', 'CHECKING', 'MONEY_MARKET'):
            errors.append('Please select a valid account type.')
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not password or len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm_pw:
            errors.append('Passwords do not match.')

        # Check uniqueness
        if not errors:
            existing_ssn = query(
                "SELECT 1 FROM Customer WHERE ssn = %s", (ssn,), one=True
            )
            if existing_ssn:
                errors.append('A customer with that SSN already exists.')

            existing_username = query(
                "SELECT 1 FROM app_users WHERE username = %s", (username,), one=True
            )
            if existing_username:
                errors.append('That username is already taken. Please choose another.')

            existing_phone = query(
                "SELECT 1 FROM Customer WHERE phone_number = %s", (phone,), one=True
            )
            if existing_phone:
                errors.append('That phone number is already registered to another account.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('register.html',
                                   branches=branches,
                                   form=request.form)

        # ── Create customer, account, and login in one transaction ─
        conn = get_db()
        try:
            with conn.cursor() as cur:
                # 1. Insert Customer
                cur.execute(
                    """INSERT INTO Customer
                           (ssn, first_name, last_name, apt_no, street_no,
                            street_name, city, state, zip_code, phone_number,
                            branch_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (ssn, first_name, last_name, apt_no, street_no,
                     street_name, city, state, zip_code, phone, branch_id)
                )

                # 2. Create Account (supertype)
                cur.execute(
                    """INSERT INTO Account (account_type, balance, open_date)
                       VALUES (%s::account_type_enum, 0.00, CURRENT_DATE)
                       RETURNING account_no""",
                    (account_type,)
                )
                account_no = cur.fetchone()['account_no']

                # 3. Create subtype row
                if account_type == 'SAVINGS':
                    cur.execute(
                        "INSERT INTO Savings_Account VALUES (%s, 0.0150)",
                        (account_no,)
                    )
                elif account_type == 'CHECKING':
                    cur.execute(
                        "INSERT INTO Checking_Account VALUES (%s, 0.00)",
                        (account_no,)
                    )
                elif account_type == 'MONEY_MARKET':
                    cur.execute(
                        "INSERT INTO MoneyMarket_Account (account_no, current_interest_rate, last_rate_update) VALUES (%s, 0.0400, NOW())",
                        (account_no,)
                    )

                # 4. Link customer to account
                cur.execute(
                    """INSERT INTO Customer_Account (customer_ssn, account_no, last_access_date)
                       VALUES (%s, %s, CURRENT_DATE)""",
                    (ssn, account_no)
                )

                # 5. Create web login
                cur.execute(
                    """INSERT INTO app_users (username, password_hash, role, customer_ssn)
                       VALUES (%s, %s, 'customer', %s)
                       RETURNING id""",
                    (username, hash_password(password), ssn)
                )
                user_id = cur.fetchone()['id']

            conn.commit()

            # Auto-login after registration
            session.clear()
            session['user_id']      = user_id
            session['username']     = username
            session['role']         = 'customer'
            session['customer_ssn'] = ssn

            flash(
                f'Welcome, {first_name}! Your {account_type.replace("_"," ").title()} '
                f'account has been opened successfully.',
                'success'
            )
            return redirect(url_for('customer_dashboard'))

        except Exception as e:
            conn.rollback()
            flash(f'Registration failed: {str(e)}', 'danger')
            return render_template('register.html',
                                   branches=branches,
                                   form=request.form)

    return render_template('register.html', branches=branches, form={})


# ── Customer Dashboard ────────────────────────────────────────────

@app.route('/customer')
@login_required
def customer_dashboard():
    ssn = session['customer_ssn']

    # Customer profile
    customer = query(
        """SELECT c.*, b.branch_name,
                  e.first_name || ' ' || e.last_name AS banker_name
           FROM   Customer c
           LEFT JOIN Branch   b ON c.branch_id           = b.branch_id
           LEFT JOIN Employee e ON c.personal_banker_ssn = e.ssn
           WHERE  c.ssn = %s""",
        (ssn,), one=True
    )

    # All accounts for this customer
    accounts = query(
        """SELECT a.account_no, a.account_type::TEXT AS account_type,
                  a.balance, a.open_date, ca.last_access_date,
                  sa.interest_rate       AS savings_rate,
                  ck.overdraft_amount,
                  mm.current_interest_rate AS mm_rate,
                  la.amount              AS loan_amount,
                  la.monthly_repayment,
                  la.interest_rate       AS loan_rate
           FROM   Customer_Account ca
           JOIN   Account          a  ON ca.account_no = a.account_no
           LEFT JOIN Savings_Account     sa ON sa.account_no = a.account_no
           LEFT JOIN Checking_Account    ck ON ck.account_no = a.account_no
           LEFT JOIN MoneyMarket_Account mm ON mm.account_no = a.account_no
           LEFT JOIN Loan_Account        la ON la.account_no = a.account_no
           WHERE  ca.customer_ssn = %s
           ORDER BY a.account_type, a.account_no""",
        (ssn,)
    )

    # Recent transactions (last 10 across all accounts)
    transactions = query(
        """SELECT tl.transaction_id, tl.transaction_code,
                  tl.transaction_name, tl.tran_date, tl.tran_time,
                  tl.amount, tl.is_chargeable, tl.charge_amount,
                  a.account_type::TEXT AS account_type, tl.account_no
           FROM   Transaction_Log tl
           JOIN   Account          a  ON tl.account_no  = a.account_no
           JOIN   Customer_Account ca ON ca.account_no  = tl.account_no
           WHERE  ca.customer_ssn = %s
           ORDER BY tl.tran_date DESC, tl.tran_time DESC
           LIMIT 10""",
        (ssn,)
    )

    # Summary totals
    totals = query(
        """SELECT
               SUM(a.balance) FILTER (WHERE a.account_type = 'SAVINGS')      AS total_savings,
               SUM(a.balance) FILTER (WHERE a.account_type = 'CHECKING')     AS total_checking,
               SUM(a.balance) FILTER (WHERE a.account_type = 'MONEY_MARKET') AS total_mm,
               SUM(a.balance) FILTER (WHERE a.account_type = 'LOAN')         AS total_loans,
               SUM(a.balance)                                                 AS grand_total
           FROM Customer_Account ca
           JOIN Account a ON ca.account_no = a.account_no
           WHERE ca.customer_ssn = %s""",
        (ssn,), one=True
    )

    return render_template('customer_dashboard.html',
                           customer=customer,
                           accounts=accounts,
                           transactions=transactions,
                           totals=totals)


# ── Account Detail ────────────────────────────────────────────────

@app.route('/account/<int:account_no>')
@login_required
def account_detail(account_no):
    ssn = session['customer_ssn']

    # Verify ownership (or admin)
    if session['role'] != 'admin':
        owns = query(
            "SELECT 1 FROM Customer_Account WHERE customer_ssn=%s AND account_no=%s",
            (ssn, account_no), one=True
        )
        if not owns:
            flash('Account not found.', 'danger')
            return redirect(url_for('customer_dashboard'))

    account = query(
        """SELECT a.*,  a.account_type::TEXT AS account_type,
                  sa.interest_rate, ck.overdraft_amount,
                  mm.current_interest_rate, mm.last_rate_update,
                  la.amount, la.interest_rate AS loan_rate,
                  la.monthly_repayment, b.branch_name AS loan_branch
           FROM   Account a
           LEFT JOIN Savings_Account     sa ON sa.account_no = a.account_no
           LEFT JOIN Checking_Account    ck ON ck.account_no = a.account_no
           LEFT JOIN MoneyMarket_Account mm ON mm.account_no = a.account_no
           LEFT JOIN Loan_Account        la ON la.account_no = a.account_no
           LEFT JOIN Branch              b  ON la.branch_id  = b.branch_id
           WHERE  a.account_no = %s""",
        (account_no,), one=True
    )

    txns = query(
        """SELECT * FROM Transaction_Log
           WHERE account_no = %s
           ORDER BY tran_date DESC, tran_time DESC""",
        (account_no,)
    )

    holders = query(
        """SELECT c.first_name || ' ' || c.last_name AS name,
                  ca.last_access_date
           FROM Customer_Account ca
           JOIN Customer c ON ca.customer_ssn = c.ssn
           WHERE ca.account_no = %s""",
        (account_no,)
    )

    return render_template('account_detail.html',
                           account=account,
                           txns=txns,
                           holders=holders)


# ── Transfer ──────────────────────────────────────────────────────

@app.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    if session['role'] != 'customer':
        flash('Transfers are only available to customers.', 'danger')
        return redirect(url_for('dashboard'))

    ssn = session['customer_ssn']

    # Fetch all eligible accounts (exclude LOAN accounts — not transferable)
    eligible_accounts = query(
        """SELECT a.account_no, a.account_type::TEXT AS account_type, a.balance
           FROM   Customer_Account ca
           JOIN   Account a ON ca.account_no = a.account_no
           WHERE  ca.customer_ssn = %s
             AND  a.account_type != 'LOAN'
           ORDER BY a.account_type, a.account_no""",
        (ssn,)
    )

    if len(eligible_accounts) < 2:
        flash('You need at least two non-loan accounts to make a transfer.', 'warning')
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        from_no    = request.form.get('from_account', type=int)
        to_no      = request.form.get('to_account',   type=int)
        amount_str = request.form.get('amount', '').strip()

        # ── Validate inputs ──────────────────────────────────────
        errors = []

        if not from_no or not to_no:
            errors.append('Please select both a source and destination account.')
        elif from_no == to_no:
            errors.append('Source and destination accounts must be different.')

        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append('Transfer amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Please enter a valid transfer amount.')
            amount = 0

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('transfer.html', accounts=eligible_accounts)

        # ── Verify both accounts belong to this customer ──────────
        account_nos = [a['account_no'] for a in eligible_accounts]
        if from_no not in account_nos or to_no not in account_nos:
            flash('Invalid account selection.', 'danger')
            return render_template('transfer.html', accounts=eligible_accounts)

        # ── Check sufficient balance ──────────────────────────────
        from_account = query(
            "SELECT balance, account_type::TEXT AS account_type FROM Account WHERE account_no = %s",
            (from_no,), one=True
        )
        to_account = query(
            "SELECT account_type::TEXT AS account_type FROM Account WHERE account_no = %s",
            (to_no,), one=True
        )

        if float(from_account['balance']) < amount:
            flash(
                f'Insufficient funds. Available balance: ${float(from_account["balance"]):,.2f}',
                'danger'
            )
            return render_template('transfer.html', accounts=eligible_accounts)

        # ── Execute transfer in a single transaction ──────────────
        conn = get_db()
        try:
            with conn.cursor() as cur:

                today    = date.today().isoformat()
                now_time = datetime.now().strftime('%H:%M:%S')

                # Debit source account
                cur.execute(
                    "UPDATE Account SET balance = balance - %s WHERE account_no = %s",
                    (amount, from_no)
                )

                # Credit destination account
                cur.execute(
                    "UPDATE Account SET balance = balance + %s WHERE account_no = %s",
                    (amount, to_no)
                )

                # Log transfer-out transaction
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('TRO', 'Transfer Out', %s, %s, %s, %s, FALSE)
                       RETURNING transaction_id""",
                    (today, now_time, amount, from_no)
                )
                out_row = cur.fetchone()
                out_id  = out_row['transaction_id']   # RealDictCursor — use key

                # Log transfer-in transaction
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('TRI', 'Transfer In', %s, %s, %s, %s, FALSE)
                       RETURNING transaction_id""",
                    (today, now_time, amount, to_no)
                )

                # Update last_access_date for both accounts
                cur.execute(
                    """UPDATE Customer_Account SET last_access_date = %s
                       WHERE customer_ssn = %s AND account_no IN (%s, %s)""",
                    (today, ssn, from_no, to_no)
                )

            conn.commit()
            flash(
                f'Transfer of ${amount:,.2f} from Account #{from_no} to '
                f'Account #{to_no} was successful.',
                'success'
            )
            return redirect(url_for('customer_dashboard'))

        except Exception as e:
            conn.rollback()
            flash(f'Transfer failed: {str(e)}', 'danger')
            return render_template('transfer.html', accounts=eligible_accounts)

    return render_template('transfer.html', accounts=eligible_accounts)


# ── Deposit ───────────────────────────────────────────────────────

@app.route('/deposit', methods=['GET', 'POST'])
@login_required
def deposit():
    if session['role'] != 'customer':
        flash('Deposits are only available to customers.', 'danger')
        return redirect(url_for('dashboard'))

    ssn = session['customer_ssn']

    # All non-loan accounts for this customer
    accounts = query(
        """SELECT a.account_no, a.account_type::TEXT AS account_type, a.balance
           FROM   Customer_Account ca
           JOIN   Account a ON ca.account_no = a.account_no
           WHERE  ca.customer_ssn = %s
             AND  a.account_type != 'LOAN'
           ORDER BY a.account_type, a.account_no""",
        (ssn,)
    )

    if not accounts:
        flash('You have no accounts available for deposit.', 'warning')
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        account_no  = request.form.get('account_no', type=int)
        amount_str  = request.form.get('amount', '').strip()
        description = request.form.get('description', 'Customer Deposit').strip() or 'Customer Deposit'

        errors = []
        if not account_no:
            errors.append('Please select an account.')

        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append('Deposit amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Please enter a valid deposit amount.')
            amount = 0

        # Verify account belongs to this customer
        valid_nos = [a['account_no'] for a in accounts]
        if account_no and account_no not in valid_nos:
            errors.append('Invalid account selection.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            preselect = request.form.get('account_no', type=int)
            return render_template('deposit.html', accounts=accounts, preselect=preselect)

        conn = get_db()
        try:
            with conn.cursor() as cur:
                today    = date.today().isoformat()
                now_time = datetime.now().strftime('%H:%M:%S')

                # Credit the account
                cur.execute(
                    "UPDATE Account SET balance = balance + %s WHERE account_no = %s",
                    (amount, account_no)
                )

                # Log deposit transaction
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('CD', %s, %s, %s, %s, %s, FALSE)""",
                    (description, today, now_time, amount, account_no)
                )

                # Update last access date
                cur.execute(
                    """UPDATE Customer_Account SET last_access_date = %s
                       WHERE customer_ssn = %s AND account_no = %s""",
                    (today, ssn, account_no)
                )

            conn.commit()
            flash(f'Successfully deposited ${amount:,.2f} into Account #{account_no}.', 'success')
            return redirect(url_for('account_detail', account_no=account_no))

        except Exception as e:
            conn.rollback()
            flash(f'Deposit failed: {str(e)}', 'danger')
            preselect = account_no
            return render_template('deposit.html', accounts=accounts, preselect=preselect)

    # Pre-select account if passed via query param (e.g. from account detail page)
    preselect = request.args.get('account_no', type=int)
    return render_template('deposit.html', accounts=accounts, preselect=preselect)


# ── Phone-based Send (Zelle-style) ────────────────────────────────

@app.route('/send/lookup', methods=['POST'])
@login_required
def send_lookup():
    """AJAX endpoint — look up a customer by phone number."""
    if session['role'] != 'customer':
        return {'error': 'Unauthorised'}, 403

    phone = request.json.get('phone', '').strip()
    if not phone:
        return {'error': 'Phone number required.'}, 400

    # Normalise: strip spaces, dashes, parentheses
    import re
    clean = re.sub(r'[\s\-().+]', '', phone)

    recipient = query(
        """SELECT ssn, first_name, last_name, phone_number
           FROM   Customer
           WHERE  REGEXP_REPLACE(phone_number, '[\\s\\-().+]', '', 'g') = %s
             AND  ssn != %s""",
        (clean, session['customer_ssn']), one=True
    )

    if not recipient:
        return {'error': 'No customer found with that phone number.'}, 404

    return {
        'ssn':        recipient['ssn'],
        'name':       f"{recipient['first_name']} {recipient['last_name']}",
        'initials':   recipient['first_name'][0] + recipient['last_name'][0],
        'phone':      recipient['phone_number'],
    }


@app.route('/send', methods=['GET', 'POST'])
@login_required
def send():
    if session['role'] != 'customer':
        flash('This feature is only available to customers.', 'danger')
        return redirect(url_for('dashboard'))

    ssn = session['customer_ssn']

    # Sender's non-loan accounts with a positive balance
    sender_accounts = query(
        """SELECT a.account_no, a.account_type::TEXT AS account_type, a.balance
           FROM   Customer_Account ca
           JOIN   Account a ON ca.account_no = a.account_no
           WHERE  ca.customer_ssn = %s
             AND  a.account_type  != 'LOAN'
             AND  a.balance        > 0
           ORDER BY a.balance DESC""",
        (ssn,)
    )

    if not sender_accounts:
        flash('You have no accounts with funds available to send.', 'warning')
        return redirect(url_for('customer_dashboard'))

    if request.method == 'POST':
        recipient_ssn = request.form.get('recipient_ssn', '').strip()
        from_no       = request.form.get('from_account', type=int)
        amount_str    = request.form.get('amount', '').strip()
        note          = request.form.get('note', '').strip() or 'Send Payment'

        errors = []

        # Validate recipient
        recipient = query(
            "SELECT ssn, first_name, last_name, phone_number FROM Customer WHERE ssn = %s AND ssn != %s",
            (recipient_ssn, ssn), one=True
        )
        if not recipient:
            errors.append('Recipient not found. Please search again.')

        # Validate from account
        valid_nos = [a['account_no'] for a in sender_accounts]
        if not from_no or from_no not in valid_nos:
            errors.append('Please select a valid source account.')

        # Validate amount
        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append('Amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Please enter a valid amount.')
            amount = 0

        # Check balance
        if from_no and amount > 0:
            src_balance = query(
                "SELECT balance FROM Account WHERE account_no = %s",
                (from_no,), one=True
            )
            if src_balance and float(src_balance['balance']) < amount:
                errors.append(
                    f'Insufficient funds. Available: ${float(src_balance["balance"]):,.2f}'
                )

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('send.html',
                                   sender_accounts=sender_accounts,
                                   prefill_recipient=recipient_ssn)

        # Find recipient's primary non-loan account (highest balance, or first savings)
        recipient_account = query(
            """SELECT a.account_no
               FROM   Customer_Account ca
               JOIN   Account a ON ca.account_no = a.account_no
               WHERE  ca.customer_ssn = %s
                 AND  a.account_type != 'LOAN'
               ORDER BY
                   CASE a.account_type WHEN 'SAVINGS' THEN 1
                                       WHEN 'CHECKING' THEN 2
                                       ELSE 3 END,
                   a.balance DESC
               LIMIT 1""",
            (recipient_ssn,), one=True
        )

        if not recipient_account:
            flash('Recipient has no eligible account to receive funds.', 'danger')
            return render_template('send.html',
                                   sender_accounts=sender_accounts,
                                   prefill_recipient=recipient_ssn)

        to_no = recipient_account['account_no']

        # Execute in one atomic transaction
        conn = get_db()
        try:
            with conn.cursor() as cur:
                today    = date.today().isoformat()
                now_time = datetime.now().strftime('%H:%M:%S')

                # Debit sender
                cur.execute(
                    "UPDATE Account SET balance = balance - %s WHERE account_no = %s",
                    (amount, from_no)
                )

                # Credit recipient
                cur.execute(
                    "UPDATE Account SET balance = balance + %s WHERE account_no = %s",
                    (amount, to_no)
                )

                # Log sender's outgoing transaction
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('SND', %s, %s, %s, %s, %s, FALSE)""",
                    (f"Sent to {recipient['first_name']} {recipient['last_name']} — {note}",
                     today, now_time, amount, from_no)
                )

                # Log recipient's incoming transaction
                sender = query(
                    "SELECT first_name, last_name FROM Customer WHERE ssn = %s",
                    (ssn,), one=True
                )
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('RCV', %s, %s, %s, %s, %s, FALSE)""",
                    (f"Received from {sender['first_name']} {sender['last_name']} — {note}",
                     today, now_time, amount, to_no)
                )

                # Update last_access_date for sender's account
                cur.execute(
                    """UPDATE Customer_Account SET last_access_date = %s
                       WHERE customer_ssn = %s AND account_no = %s""",
                    (today, ssn, from_no)
                )

                # Update last_access_date for recipient's account
                cur.execute(
                    """UPDATE Customer_Account SET last_access_date = %s
                       WHERE customer_ssn = %s AND account_no = %s""",
                    (today, recipient_ssn, to_no)
                )

            conn.commit()
            flash(
                f'${amount:,.2f} sent successfully to '
                f'{recipient["first_name"]} {recipient["last_name"]}.',
                'success'
            )
            return redirect(url_for('customer_dashboard'))

        except Exception as e:
            conn.rollback()
            flash(f'Payment failed: {str(e)}', 'danger')
            return render_template('send.html',
                                   sender_accounts=sender_accounts,
                                   prefill_recipient=recipient_ssn)

    return render_template('send.html',
                           sender_accounts=sender_accounts,
                           prefill_recipient=None)


# ── Admin Dashboard ───────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():

    # Bank-wide summary stats
    stats = query(
        """SELECT
               (SELECT COUNT(*) FROM Branch)   AS num_branches,
               (SELECT COUNT(*) FROM Employee) AS num_employees,
               (SELECT COUNT(*) FROM Customer) AS num_customers,
               (SELECT COUNT(*) FROM Account)  AS num_accounts,
               (SELECT SUM(balance) FROM Account) AS total_balance,
               (SELECT COUNT(*) FROM Transaction_Log) AS num_transactions,
               (SELECT SUM(assets) FROM Branch) AS total_assets""",
        one=True
    )

    # Account type breakdown
    breakdown = query(
        """SELECT account_type::TEXT AS account_type,
                  COUNT(*)           AS count,
                  SUM(balance)       AS total_balance
           FROM Account
           GROUP BY account_type
           ORDER BY account_type"""
    )

    # All customers with account count and total balance
    customers = query(
        """SELECT c.ssn, c.first_name || ' ' || c.last_name AS name,
                  c.city, c.state,
                  b.branch_name,
                  e.first_name || ' ' || e.last_name AS banker,
                  COUNT(ca.account_no)  AS num_accounts,
                  COALESCE(SUM(a.balance), 0) AS total_balance
           FROM   Customer c
           LEFT JOIN Branch          b  ON c.branch_id           = b.branch_id
           LEFT JOIN Employee        e  ON c.personal_banker_ssn = e.ssn
           LEFT JOIN Customer_Account ca ON c.ssn = ca.customer_ssn
           LEFT JOIN Account          a  ON ca.account_no = a.account_no
           GROUP BY c.ssn, c.first_name, c.last_name, c.city, c.state,
                    b.branch_name, e.first_name, e.last_name
           ORDER BY total_balance DESC"""
    )

    # Branch summary
    branches = query(
        """SELECT b.branch_name, b.city, b.assets,
                  COUNT(DISTINCT e.ssn)         AS num_employees,
                  COUNT(DISTINCT la.account_no) AS num_loans,
                  SUM(la.amount)                AS total_loans
           FROM   Branch b
           LEFT JOIN Employee    e  ON e.branch_id  = b.branch_id
           LEFT JOIN Loan_Account la ON la.branch_id = b.branch_id
           GROUP BY b.branch_id, b.branch_name, b.city, b.assets
           ORDER BY b.assets DESC"""
    )

    # Recent transactions (last 15)
    recent_txns = query(
        """SELECT tl.transaction_id, tl.transaction_code,
                  tl.transaction_name, tl.tran_date, tl.tran_time,
                  tl.amount, tl.is_chargeable,
                  a.account_type::TEXT AS account_type,
                  c.first_name || ' ' || c.last_name AS customer_name
           FROM   Transaction_Log tl
           JOIN   Account          a  ON tl.account_no  = a.account_no
           JOIN   Customer_Account ca ON ca.account_no  = tl.account_no
           JOIN   Customer          c  ON ca.customer_ssn = c.ssn
           ORDER BY tl.tran_date DESC, tl.tran_time DESC
           LIMIT 15"""
    )

    return render_template('admin_dashboard.html',
                           stats=stats,
                           breakdown=breakdown,
                           customers=customers,
                           branches=branches,
                           recent_txns=recent_txns)


# ── Admin: All Accounts ───────────────────────────────────────────

@app.route('/admin/accounts')
@login_required
@admin_required
def admin_accounts():
    acct_type = request.args.get('type', '')
    search    = request.args.get('search', '').strip()

    sql = """
        SELECT a.account_no, a.account_type::TEXT AS account_type,
               a.balance, a.open_date,
               STRING_AGG(c.first_name || ' ' || c.last_name, ', ') AS holders
        FROM   Account a
        LEFT JOIN Customer_Account ca ON ca.account_no   = a.account_no
        LEFT JOIN Customer          c  ON ca.customer_ssn = c.ssn
        WHERE  1=1
    """
    params = []
    if acct_type:
        sql += " AND a.account_type::TEXT = %s"
        params.append(acct_type)
    if search:
        sql += " AND (c.first_name ILIKE %s OR c.last_name ILIKE %s)"
        params += [f'%{search}%', f'%{search}%']

    sql += " GROUP BY a.account_no, a.account_type, a.balance, a.open_date ORDER BY a.account_no"
    accounts = query(sql, params)

    return render_template('admin_accounts.html',
                           accounts=accounts,
                           acct_type=acct_type,
                           search=search)


# ── Admin: Customer detail ────────────────────────────────────────

@app.route('/admin/customer/<ssn>')
@login_required
@admin_required
def admin_customer_detail(ssn):
    customer = query(
        """SELECT c.*, b.branch_name,
                  e.first_name || ' ' || e.last_name AS banker_name
           FROM   Customer c
           LEFT JOIN Branch   b ON c.branch_id           = b.branch_id
           LEFT JOIN Employee e ON c.personal_banker_ssn = e.ssn
           WHERE  c.ssn = %s""",
        (ssn,), one=True
    )
    if not customer:
        flash('Customer not found.', 'danger')
        return redirect(url_for('admin_dashboard'))

    accounts = query(
        """SELECT a.account_no, a.account_type::TEXT AS account_type,
                  a.balance, a.open_date, ca.last_access_date
           FROM   Customer_Account ca
           JOIN   Account a ON ca.account_no = a.account_no
           WHERE  ca.customer_ssn = %s
           ORDER BY a.account_type""",
        (ssn,)
    )

    return render_template('admin_customer_detail.html',
                           customer=customer,
                           accounts=accounts)


# ── Admin: Transfer on behalf of customer ─────────────────────────

@app.route('/admin/transfer', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_transfer():

    # All customers who have 2+ non-loan accounts
    all_customers = query(
        """SELECT c.ssn,
                  c.first_name || ' ' || c.last_name AS name,
                  COUNT(a.account_no) AS eligible_accounts
           FROM   Customer c
           JOIN   Customer_Account ca ON ca.customer_ssn = c.ssn
           JOIN   Account          a  ON ca.account_no   = a.account_no
           WHERE  a.account_type != 'LOAN'
           GROUP BY c.ssn, c.first_name, c.last_name
           HAVING COUNT(a.account_no) >= 2
           ORDER BY c.first_name, c.last_name"""
    )

    # Selected customer (from query param or POST)
    selected_ssn = request.args.get('ssn') or request.form.get('customer_ssn', '')

    customer       = None
    customer_accounts = []

    if selected_ssn:
        customer = query(
            "SELECT ssn, first_name || ' ' || last_name AS name FROM Customer WHERE ssn = %s",
            (selected_ssn,), one=True
        )
        if customer:
            customer_accounts = query(
                """SELECT a.account_no, a.account_type::TEXT AS account_type, a.balance
                   FROM   Customer_Account ca
                   JOIN   Account a ON ca.account_no = a.account_no
                   WHERE  ca.customer_ssn = %s
                     AND  a.account_type != 'LOAN'
                   ORDER BY a.account_type, a.account_no""",
                (selected_ssn,)
            )

    if request.method == 'POST':
        from_no    = request.form.get('from_account', type=int)
        to_no      = request.form.get('to_account',   type=int)
        amount_str = request.form.get('amount', '').strip()
        ssn        = request.form.get('customer_ssn', '').strip()

        errors = []
        if not ssn:
            errors.append('No customer selected.')
        if not from_no or not to_no:
            errors.append('Please select both a source and destination account.')
        elif from_no == to_no:
            errors.append('Source and destination accounts must be different.')

        try:
            amount = float(amount_str)
            if amount <= 0:
                errors.append('Transfer amount must be greater than zero.')
        except (ValueError, TypeError):
            errors.append('Please enter a valid transfer amount.')
            amount = 0

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('admin_transfer.html',
                                   all_customers=all_customers,
                                   customer=customer,
                                   customer_accounts=customer_accounts,
                                   selected_ssn=ssn)

        # Verify accounts belong to the selected customer
        valid_nos = [a['account_no'] for a in customer_accounts]
        if from_no not in valid_nos or to_no not in valid_nos:
            flash('Invalid account selection for this customer.', 'danger')
            return render_template('admin_transfer.html',
                                   all_customers=all_customers,
                                   customer=customer,
                                   customer_accounts=customer_accounts,
                                   selected_ssn=ssn)

        # Check balance
        from_acct = query(
            "SELECT balance FROM Account WHERE account_no = %s",
            (from_no,), one=True
        )
        if float(from_acct['balance']) < amount:
            flash(
                f'Insufficient funds. Available: ${float(from_acct["balance"]):,.2f}',
                'danger'
            )
            return render_template('admin_transfer.html',
                                   all_customers=all_customers,
                                   customer=customer,
                                   customer_accounts=customer_accounts,
                                   selected_ssn=ssn)

        # Execute transfer
        conn = get_db()
        try:
            with conn.cursor() as cur:
                today    = date.today().isoformat()
                now_time = datetime.now().strftime('%H:%M:%S')

                cur.execute(
                    "UPDATE Account SET balance = balance - %s WHERE account_no = %s",
                    (amount, from_no)
                )
                cur.execute(
                    "UPDATE Account SET balance = balance + %s WHERE account_no = %s",
                    (amount, to_no)
                )
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('TRO', 'Transfer Out (Admin)', %s, %s, %s, %s, FALSE)""",
                    (today, now_time, amount, from_no)
                )
                cur.execute(
                    """INSERT INTO Transaction_Log
                           (transaction_code, transaction_name, tran_date, tran_time,
                            amount, account_no, is_chargeable)
                       VALUES ('TRI', 'Transfer In (Admin)', %s, %s, %s, %s, FALSE)""",
                    (today, now_time, amount, to_no)
                )
                cur.execute(
                    """UPDATE Customer_Account SET last_access_date = %s
                       WHERE customer_ssn = %s AND account_no IN (%s, %s)""",
                    (today, ssn, from_no, to_no)
                )

            conn.commit()
            cust_name = customer['name'] if customer else ssn
            flash(
                f'Transfer of ${amount:,.2f} from Account #{from_no} to '
                f'Account #{to_no} completed on behalf of {cust_name}.',
                'success'
            )
            return redirect(url_for('admin_customer_detail', ssn=ssn))

        except Exception as e:
            conn.rollback()
            flash(f'Transfer failed: {str(e)}', 'danger')
            return render_template('admin_transfer.html',
                                   all_customers=all_customers,
                                   customer=customer,
                                   customer_accounts=customer_accounts,
                                   selected_ssn=ssn)

    return render_template('admin_transfer.html',
                           all_customers=all_customers,
                           customer=customer,
                           customer_accounts=customer_accounts,
                           selected_ssn=selected_ssn)


# ══════════════════════════════════════════════════════════════════
# TEMPLATE FILTERS
# ══════════════════════════════════════════════════════════════════

@app.template_filter('currency')
def currency_filter(value):
    if value is None:
        return '$0.00'
    return f'${float(value):,.2f}'

@app.template_filter('pct')
def pct_filter(value):
    if value is None:
        return '—'
    return f'{float(value)*100:.2f}%'

@app.template_filter('account_icon')
def account_icon_filter(acct_type):
    icons = {
        'SAVINGS':      '🏦',
        'CHECKING':     '💳',
        'MONEY_MARKET': '📈',
        'LOAN':         '🏠',
    }
    return icons.get(str(acct_type).upper(), '💰')


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    init_app_users()
    app.run(debug=True, host='0.0.0.0', port=5055)