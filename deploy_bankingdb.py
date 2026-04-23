#!/usr/bin/env python3
"""
deploy_bankingdb.py
====================
Manages the BankingDB PostgreSQL container via docker-compose,
then creates the full banking schema and seeds all tables.

Requirements:
    pip install psycopg2-binary

    Docker + Docker Compose plugin must be installed and running.
    docker-compose.yml must be in the same directory as this script.

Usage:
    python deploy_bankingdb.py              # bring up + create schema + seed
    python deploy_bankingdb.py --reset      # down -v, bring up fresh, create schema + seed
    python deploy_bankingdb.py --schema-only # skip compose; just (re)run schema + seed
    python deploy_bankingdb.py --stop       # docker compose down
    python deploy_bankingdb.py --stop --volumes  # docker compose down -v (wipes data)
"""

import argparse
import socket
import subprocess
import sys
import time
import textwrap
from pathlib import Path
from datetime import datetime

# ── psycopg2 ───────────────────────────────────────────────────────
try:
    import psycopg2
except ImportError:
    print("[ERROR] 'psycopg2-binary' not found.\n"
          "        Install it with:  pip install psycopg2-binary")
    sys.exit(1)


# ══════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════

CONFIG = {
    "compose_file":  Path(__file__).parent / "docker-compose.yml",
    "db_host":       "localhost",
    "db_port":       5433,
    "db_name":       "bankingdb",
    "db_user":       "bankadmin",
    "db_password":   "BankDBSecure123",
    "max_wait_secs": 120,         # increased from 90 — first-run image init can be slow
}


# ══════════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════════

def ts():
    return datetime.now().strftime("%H:%M:%S")

def log(msg, level="INFO"):
    icons = {"INFO": "ℹ", "OK": "✓", "WARN": "⚠", "ERROR": "✗", "STEP": "▶"}
    print(f"  [{ts()}] {icons.get(level,'•')}  {msg}")

def section(title):
    bar = "─" * 62
    print(f"\n{bar}\n  {title}\n{bar}")


# ══════════════════════════════════════════════════════════════════
# DOCKER COMPOSE HELPERS
# ══════════════════════════════════════════════════════════════════

def compose_cmd(*args, capture=False):
    """
    Run `docker compose <args>` inside the directory containing docker-compose.yml.
    Tries `docker compose` (plugin) then `docker-compose` (standalone) as fallback.
    """
    compose_dir = str(CONFIG["compose_file"].parent)

    for binary in (["docker", "compose"], ["docker-compose"]):
        cmd = binary + list(args)
        if capture:
            result = subprocess.run(
                cmd, cwd=compose_dir,
                capture_output=True, text=True
            )
            return result
        else:
            result = subprocess.run(cmd, cwd=compose_dir)
            if result.returncode != 0 and binary == ["docker", "compose"]:
                continue        # try standalone fallback
            return result

    log("Neither 'docker compose' nor 'docker-compose' found.", "ERROR")
    log("Install Docker Desktop or the Compose plugin.", "WARN")
    sys.exit(1)


def check_compose_file():
    """Abort if docker-compose.yml is missing. Also ensure pgpass exists."""
    cf = CONFIG["compose_file"]
    if not cf.exists():
        log(f"docker-compose.yml not found at: {cf}", "ERROR")
        log("Run this script from the project directory.", "WARN")
        sys.exit(1)
    log(f"docker-compose.yml found: {cf}", "OK")

    # Ensure pgpass exists alongside docker-compose.yml
    pgpass = cf.parent / "pgpass"
    if not pgpass.exists():
        pgpass.write_text(
            "# pgpass: hostname:port:database:username:password\n"
            "bankingdb:5432:*:bankadmin:BankDBSecure123\n"
        )
        log(f"Created pgpass file: {pgpass}", "OK")
    else:
        log(f"pgpass file found: {pgpass}", "OK")


def compose_up():
    """Start services defined in docker-compose.yml (detached)."""
    log("Running: docker compose up -d --pull missing …", "STEP")
    result = compose_cmd("up", "-d", "--pull", "missing")
    if result.returncode != 0:
        log("docker compose up failed.", "ERROR")
        sys.exit(1)
    log("Compose services started.", "OK")


def compose_down(volumes=False):
    """Stop and remove compose services, optionally wiping volumes."""
    args = ["down"]
    if volumes:
        args.append("-v")
        log("Running: docker compose down -v (data volume will be deleted)…", "STEP")
    else:
        log("Running: docker compose down …", "STEP")
    compose_cmd(*args)
    log("Compose services stopped and removed.", "OK")


def compose_ps():
    """Print current status of compose services."""
    compose_cmd("ps")


def get_container_state():
    """
    Return the state of the BankingDB container as a string:
    'running', 'exited', 'paused', 'not_found', or 'unknown'.
    Uses 'docker inspect' which works regardless of compose version.
    """
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.State.Status}}", "BankingDB"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        # Non-zero exit means the container doesn't exist
        return "not_found"
    return result.stdout.strip().lower() or "unknown"


def is_running():
    """Return True if the BankingDB container is already running."""
    return get_container_state() == "running"


def compose_up():
    """
    Start services via docker compose up -d.
    If the container is already running, log a notice and skip
    rather than propagating the Docker HTTP 304 error.
    """
    state = get_container_state()

    if state == "running":
        log("Container 'BankingDB' is already running — skipping compose up.", "WARN")
        log("Use --reset to tear down and redeploy, or --schema-only to re-run schema.", "INFO")
        return

    if state == "exited":
        log("Container 'BankingDB' exists but is stopped — restarting…", "WARN")

    log("Running: docker compose up -d --pull missing …", "STEP")
    result = compose_cmd("up", "-d", "--pull", "missing", capture=True)

    # HTTP 304 / "already started" is not a real failure — treat it as OK
    already_started = (
        "304" in result.stderr or
        "already started" in result.stderr.lower() or
        "already started" in result.stdout.lower()
    )

    if result.returncode != 0 and not already_started:
        log("docker compose up failed.", "ERROR")
        log(result.stderr.strip() or result.stdout.strip(), "ERROR")
        sys.exit(1)

    if already_started:
        log("Container was already started (HTTP 304) — continuing.", "WARN")
    else:
        log("Compose services started.", "OK")


# ══════════════════════════════════════════════════════════════════
# POSTGRES CONNECTION
# ══════════════════════════════════════════════════════════════════

def _container_logs(tail=20):
    """Return the last N lines of the BankingDB container log."""
    result = subprocess.run(
        ["docker", "logs", "--tail", str(tail), "BankingDB"],
        capture_output=True, text=True
    )
    return (result.stdout + result.stderr).strip()


def _port_open(host, port, timeout=2):
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _diagnose():
    """
    Print a structured diagnosis when PostgreSQL cannot be reached.
    Checks container state, port binding, and recent logs.
    """
    print()
    print("  ── Diagnosis ────────────────────────────────────────────")

    # 1. Container state
    state = get_container_state()
    log(f"Container state : {state}", "INFO")

    if state == "not_found":
        log("Container 'BankingDB' does not exist.", "ERROR")
        log("Run the script without flags to create it.", "WARN")
        return

    # 2. Port reachability
    cfg = CONFIG
    port_ok = _port_open(cfg["db_host"], cfg["db_port"])
    if port_ok:
        log(f"Port {cfg['db_port']} is open — PostgreSQL process is listening.", "OK")
        log("The port is reachable but authentication failed or DB not ready.", "WARN")
        log(f"Check credentials: user={cfg['db_user']}  db={cfg['db_name']}", "WARN")
    else:
        log(f"Port {cfg['db_port']} is NOT reachable on {cfg['db_host']}.", "ERROR")
        log("Possible causes:", "WARN")
        log("  • Container is still initialising (try again in ~15 seconds)", "WARN")
        log(f"  • Port {cfg['db_port']} is already used by another process on your machine", "WARN")
        log("  • docker-compose.yml port mapping is incorrect", "WARN")

    # 3. Recent container logs
    print()
    log("Last 25 lines of container log:", "INFO")
    print("  " + "─" * 56)
    logs = _container_logs(tail=25)
    for line in logs.splitlines():
        print(f"  {line}")
    print("  " + "─" * 56)

    # 4. Port conflict check
    if not port_ok:
        result = subprocess.run(
            ["lsof", "-i", f":{cfg['db_port']}"],
            capture_output=True, text=True
        )
        if result.stdout.strip():
            print()
            log(f"Process(es) already using port {cfg['db_port']}:", "WARN")
            for line in result.stdout.strip().splitlines():
                print(f"  {line}")
            log(f"Change 'host_port' in CONFIG to a free port and update docker-compose.yml.", "WARN")

    print()


def _is_auth_failure(err_str):
    """Return True if the error is definitely a password/auth problem."""
    markers = [
        "password authentication failed",
        "pg_hba.conf",
        "authentication failed",
        "role \"bankadmin\" does not exist",
    ]
    return any(m in err_str.lower() for m in markers)


def _prompt_reset():
    """
    Ask the user if they want to wipe the volume and redeploy.
    Returns True if they agree.
    """
    print()
    print("  ┌─────────────────────────────────────────────────────────┐")
    print("  │  The PostgreSQL data volume was initialised with a      │")
    print("  │  different password on a previous run.                  │")
    print("  │                                                         │")
    print("  │  Fix: wipe the volume and redeploy (all data lost).     │")
    print("  │                                                         │")
    print("  │  Run:  python deploy_bankingdb.py --reset               │")
    print("  └─────────────────────────────────────────────────────────┘")
    print()
    try:
        answer = input("  Auto-reset now? This deletes all existing data. [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"
    return answer == "y"


def wait_for_postgres():
    """
    Poll until PostgreSQL accepts connections.
    Shows live container state, captures the actual error message on failure,
    and runs full diagnostics before exiting.
    """
    cfg      = CONFIG
    start    = time.time()
    attempt  = 0
    last_err = ""
    last_state_log = 0

    log(f"Waiting up to {cfg['max_wait_secs']}s for PostgreSQL on "
        f"{cfg['db_host']}:{cfg['db_port']} …", "STEP")

    while time.time() - start < cfg["max_wait_secs"]:
        attempt += 1
        elapsed = int(time.time() - start)

        # Log container state every 15 s so the user can see it's progressing
        if elapsed - last_state_log >= 15:
            state = get_container_state()
            print(f"\r    [{elapsed:3d}s]  Container: {state:<12}  attempt {attempt} …",
                  end="", flush=True)
            last_state_log = elapsed

            # If container crashed, bail early — no point waiting
            if state in ("exited", "dead", "not_found"):
                print()
                log(f"Container stopped unexpectedly (state: {state}).", "ERROR")
                _diagnose()
                sys.exit(1)

        try:
            conn = psycopg2.connect(
                host            = cfg["db_host"],
                port            = cfg["db_port"],
                dbname          = cfg["db_name"],
                user            = cfg["db_user"],
                password        = cfg["db_password"],
                connect_timeout = 3,
            )
            conn.close()
            print()   # clear the progress line
            elapsed = round(time.time() - start, 1)
            log(f"PostgreSQL ready after {elapsed}s ({attempt} attempt(s)).", "OK")
            return

        except psycopg2.OperationalError as e:
            last_err = str(e).strip().splitlines()[0]

            # ── Detect stale-volume password mismatch immediately ──────
            # No point waiting 120 s — the error will never go away on its own.
            if _is_auth_failure(last_err):
                print()
                log("Authentication failed — stale volume detected.", "ERROR")
                log(f"Error: {last_err}", "ERROR")
                log("The data volume was initialised with a different password.", "WARN")

                if _prompt_reset():
                    print()
                    section("Auto-Reset: Wiping Volume and Redeploying")
                    compose_down(volumes=True)
                    compose_up()
                    # Restart the wait from scratch
                    start          = time.time()
                    attempt        = 0
                    last_err       = ""
                    last_state_log = 0
                    log(f"Waiting up to {cfg['max_wait_secs']}s for fresh PostgreSQL …", "STEP")
                    continue
                else:
                    print()
                    log("Manual fix: run  python deploy_bankingdb.py --reset", "WARN")
                    sys.exit(1)
            # ──────────────────────────────────────────────────────────

            print(f"\r    [{elapsed:3d}s]  Not ready ({last_err[:60]}) …",
                  end="", flush=True)
            time.sleep(3)

    # ── Timeout ──────────────────────────────────────────────────
    print()
    log(f"Timed out after {cfg['max_wait_secs']}s waiting for PostgreSQL.", "ERROR")
    if last_err:
        log(f"Last error: {last_err}", "ERROR")
    _diagnose()
    sys.exit(1)


def get_connection():
    cfg = CONFIG
    try:
        return psycopg2.connect(
            host     = cfg["db_host"],
            port     = cfg["db_port"],
            dbname   = cfg["db_name"],
            user     = cfg["db_user"],
            password = cfg["db_password"],
        )
    except psycopg2.OperationalError as e:
        log(f"Cannot connect to database: {e}", "ERROR")
        _diagnose()
        sys.exit(1)



# ══════════════════════════════════════════════════════════════════
# SCHEMA DDL
# ══════════════════════════════════════════════════════════════════

DDL_STATEMENTS = [

    # ── Clean slate ─────────────────────────────────────────────
    ("Drop existing objects",
     """
     DO $$ BEGIN
         DROP TABLE IF EXISTS Transaction_Log      CASCADE;
         DROP TABLE IF EXISTS Loan_Account         CASCADE;
         DROP TABLE IF EXISTS MoneyMarket_Account  CASCADE;
         DROP TABLE IF EXISTS Checking_Account     CASCADE;
         DROP TABLE IF EXISTS Savings_Account      CASCADE;
         DROP TABLE IF EXISTS Customer_Account     CASCADE;
         DROP TABLE IF EXISTS Account              CASCADE;
         DROP TABLE IF EXISTS Customer             CASCADE;
         DROP TABLE IF EXISTS Employee_Dependent   CASCADE;
         DROP TABLE IF EXISTS Employee_Phone       CASCADE;
         DROP TABLE IF EXISTS Employee             CASCADE;
         DROP TABLE IF EXISTS Branch               CASCADE;
         DROP TYPE  IF EXISTS account_type_enum;
     END $$
     """),

    # ── ENUM ────────────────────────────────────────────────────
    ("Create ENUM type: account_type_enum",
     """
     CREATE TYPE account_type_enum AS ENUM (
         'SAVINGS', 'CHECKING', 'MONEY_MARKET', 'LOAN'
     )
     """),

    # ── Branch ──────────────────────────────────────────────────
    ("Create table: Branch",
     """
     CREATE TABLE Branch (
         branch_id        SERIAL        PRIMARY KEY,
         branch_name      VARCHAR(100)  NOT NULL UNIQUE,
         city             VARCHAR(60)   NOT NULL,
         address_street   VARCHAR(120)  NOT NULL,
         address_state    CHAR(2)       NOT NULL,
         address_zip      CHAR(10)      NOT NULL,
         assets           NUMERIC(18,2) NOT NULL DEFAULT 0.00,
         manager_ssn      CHAR(11),
         asst_manager_ssn CHAR(11),
         CONSTRAINT chk_assets_positive CHECK (assets >= 0)
     )
     """),

    # ── Employee ────────────────────────────────────────────────
    ("Create table: Employee",
     """
     CREATE TABLE Employee (
         ssn          CHAR(11)     PRIMARY KEY,
         first_name   VARCHAR(60)  NOT NULL,
         last_name    VARCHAR(60)  NOT NULL,
         start_date   DATE         NOT NULL,
         branch_id    INTEGER      NOT NULL
                          REFERENCES Branch(branch_id) ON UPDATE CASCADE,
         manager_ssn  CHAR(11)
                          REFERENCES Employee(ssn) ON DELETE SET NULL,
         CONSTRAINT chk_ssn_format CHECK (ssn ~ '^\\d{3}-\\d{2}-\\d{4}$')
     )
     """),

    # ── Deferred FKs on Branch (circular dependency) ─────────────
    ("Add deferred FK constraints on Branch (manager / asst. manager)",
     """
     ALTER TABLE Branch
         ADD CONSTRAINT fk_branch_manager
             FOREIGN KEY (manager_ssn) REFERENCES Employee(ssn)
             DEFERRABLE INITIALLY DEFERRED,
         ADD CONSTRAINT fk_branch_asst_manager
             FOREIGN KEY (asst_manager_ssn) REFERENCES Employee(ssn)
             DEFERRABLE INITIALLY DEFERRED
     """),

    # ── Employee_Phone ───────────────────────────────────────────
    ("Create table: Employee_Phone",
     """
     CREATE TABLE Employee_Phone (
         ssn          CHAR(11)    NOT NULL
                          REFERENCES Employee(ssn) ON DELETE CASCADE,
         phone_number VARCHAR(20) NOT NULL,
         PRIMARY KEY (ssn, phone_number)
     )
     """),

    # ── Employee_Dependent ───────────────────────────────────────
    ("Create table: Employee_Dependent",
     """
     CREATE TABLE Employee_Dependent (
         ssn            CHAR(11)    NOT NULL
                            REFERENCES Employee(ssn) ON DELETE CASCADE,
         dependent_name VARCHAR(80) NOT NULL,
         PRIMARY KEY (ssn, dependent_name)
     )
     """),

    # ── Customer ─────────────────────────────────────────────────
    ("Create table: Customer",
     """
     CREATE TABLE Customer (
         ssn                 CHAR(11)     PRIMARY KEY,
         first_name          VARCHAR(60)  NOT NULL,
         last_name           VARCHAR(60)  NOT NULL,
         apt_no              VARCHAR(10),
         street_no           VARCHAR(10)  NOT NULL,
         street_name         VARCHAR(100) NOT NULL,
         city                VARCHAR(60)  NOT NULL,
         state               CHAR(2)      NOT NULL,
         zip_code            CHAR(10)     NOT NULL,
         phone_number        VARCHAR(20),
         branch_id           INTEGER
                                 REFERENCES Branch(branch_id) ON UPDATE CASCADE,
         personal_banker_ssn CHAR(11)
                                 REFERENCES Employee(ssn) ON DELETE SET NULL,
         CONSTRAINT chk_cust_ssn CHECK (ssn ~ '^\\d{3}-\\d{2}-\\d{4}$')
     )
     """),

    # ── Account ──────────────────────────────────────────────────
    ("Create table: Account (supertype)",
     """
     CREATE TABLE Account (
         account_no   SERIAL            PRIMARY KEY,
         account_type account_type_enum NOT NULL,
         balance      NUMERIC(18,2)     NOT NULL DEFAULT 0.00,
         open_date    DATE              NOT NULL DEFAULT CURRENT_DATE,
         CONSTRAINT chk_balance CHECK (balance >= 0)
     )
     """),

    # ── Customer_Account ─────────────────────────────────────────
    ("Create table: Customer_Account (M:N junction)",
     """
     CREATE TABLE Customer_Account (
         customer_ssn     CHAR(11) NOT NULL
                              REFERENCES Customer(ssn) ON DELETE CASCADE,
         account_no       INTEGER  NOT NULL
                              REFERENCES Account(account_no) ON DELETE CASCADE,
         last_access_date DATE     NOT NULL,
         PRIMARY KEY (customer_ssn, account_no)
     )
     """),

    # ── Savings_Account ──────────────────────────────────────────
    ("Create table: Savings_Account (IS-A subtype)",
     """
     CREATE TABLE Savings_Account (
         account_no    INTEGER       PRIMARY KEY
                           REFERENCES Account(account_no) ON DELETE CASCADE,
         interest_rate NUMERIC(5,4)  NOT NULL,
         CONSTRAINT chk_savings_rate CHECK (interest_rate > 0)
     )
     """),

    # ── Checking_Account ─────────────────────────────────────────
    ("Create table: Checking_Account (IS-A subtype)",
     """
     CREATE TABLE Checking_Account (
         account_no       INTEGER       PRIMARY KEY
                              REFERENCES Account(account_no) ON DELETE CASCADE,
         overdraft_amount NUMERIC(18,2) NOT NULL DEFAULT 0.00,
         CONSTRAINT chk_overdraft CHECK (overdraft_amount >= 0)
     )
     """),

    # ── MoneyMarket_Account ──────────────────────────────────────
    ("Create table: MoneyMarket_Account (IS-A subtype)",
     """
     CREATE TABLE MoneyMarket_Account (
         account_no            INTEGER       PRIMARY KEY
                                   REFERENCES Account(account_no) ON DELETE CASCADE,
         current_interest_rate NUMERIC(5,4)  NOT NULL,
         last_rate_update      TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
         CONSTRAINT chk_mm_rate CHECK (current_interest_rate > 0)
     )
     """),

    # ── Loan_Account ─────────────────────────────────────────────
    ("Create table: Loan_Account (IS-A subtype)",
     """
     CREATE TABLE Loan_Account (
         account_no        INTEGER       PRIMARY KEY
                               REFERENCES Account(account_no) ON DELETE CASCADE,
         amount            NUMERIC(18,2) NOT NULL,
         interest_rate     NUMERIC(5,4)  NOT NULL,
         monthly_repayment NUMERIC(18,2) NOT NULL,
         branch_id         INTEGER       NOT NULL
                               REFERENCES Branch(branch_id),
         CONSTRAINT chk_loan_amount    CHECK (amount > 0),
         CONSTRAINT chk_loan_rate      CHECK (interest_rate > 0),
         CONSTRAINT chk_loan_repayment CHECK (monthly_repayment > 0)
     )
     """),

    # ── Transaction_Log ──────────────────────────────────────────
    ("Create table: Transaction_Log",
     """
     CREATE TABLE Transaction_Log (
         transaction_id        SERIAL        PRIMARY KEY,
         transaction_code      CHAR(3)       NOT NULL,
         transaction_name      VARCHAR(80)   NOT NULL,
         tran_date             DATE          NOT NULL,
         tran_time             TIME          NOT NULL,
         amount                NUMERIC(18,2) NOT NULL,
         account_no            INTEGER       NOT NULL
                                   REFERENCES Account(account_no),
         is_chargeable         BOOLEAN       NOT NULL DEFAULT FALSE,
         charge_amount         NUMERIC(10,2),
         parent_transaction_id INTEGER
                                   REFERENCES Transaction_Log(transaction_id),
         CONSTRAINT chk_txn_amount CHECK (amount > 0)
     )
     """),

    # ── Indexes ──────────────────────────────────────────────────
    ("Create index: idx_employee_branch",
     "CREATE INDEX idx_employee_branch  ON Employee(branch_id)"),
    ("Create index: idx_customer_branch",
     "CREATE INDEX idx_customer_branch  ON Customer(branch_id)"),
    ("Create index: idx_customer_banker",
     "CREATE INDEX idx_customer_banker  ON Customer(personal_banker_ssn)"),
    ("Create index: idx_account_type",
     "CREATE INDEX idx_account_type     ON Account(account_type)"),
    ("Create index: idx_txn_account_date",
     "CREATE INDEX idx_txn_account_date ON Transaction_Log(account_no, tran_date)"),
    ("Create index: idx_txn_code",
     "CREATE INDEX idx_txn_code         ON Transaction_Log(transaction_code)"),
    ("Create index: idx_loan_branch",
     "CREATE INDEX idx_loan_branch      ON Loan_Account(branch_id)"),
]


# ══════════════════════════════════════════════════════════════════
# SEED DATA
# ══════════════════════════════════════════════════════════════════

SEED_DATA = {
    "Branch": {
        "sql": """
            INSERT INTO Branch
                (branch_name, city, address_street, address_state, address_zip, assets)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
        "rows": [
            ("Downtown Main",   "New York",    "100 Wall Street",    "NY", "10005", 12450000.00),
            ("Midtown West",    "New York",    "450 7th Avenue",     "NY", "10123",  8300000.00),
            ("Chicago Central", "Chicago",     "200 S Michigan Ave", "IL", "60604",  9875000.00),
            ("LA Pacific",      "Los Angeles", "1 Ocean Boulevard",  "CA", "90210",  6120000.00),
            ("Boston Harbor",   "Boston",      "75 State Street",    "MA", "02109",  7450000.00),
        ],
    },
    "Employee": {
        "sql": """
            INSERT INTO Employee
                (ssn, first_name, last_name, start_date, branch_id, manager_ssn)
            VALUES (%s, %s, %s, %s, %s, %s)
        """,
        "rows": [
            ("111-22-3333", "Alice",  "Morgan",   "2010-03-15", 1, None),
            ("222-33-4444", "Brian",  "Chen",     "2012-07-01", 1, "111-22-3333"),
            ("333-44-5555", "Clara",  "Ortiz",    "2009-11-20", 2, None),
            ("444-55-6666", "David",  "Patel",    "2015-02-28", 2, "333-44-5555"),
            ("555-66-7777", "Eva",    "Johnson",  "2008-06-10", 3, None),
            ("666-77-8888", "Frank",  "Williams", "2013-09-05", 3, "555-66-7777"),
            ("777-88-9999", "Grace",  "Kim",      "2011-01-14", 4, None),
            ("888-99-0000", "Henry",  "Davis",    "2016-04-22", 4, "777-88-9999"),
            ("999-00-1111", "Isabel", "Torres",   "2018-08-30", 1, "111-22-3333"),
            ("000-11-2222", "James",  "Wilson",   "2020-05-17", 5, None),
            ("100-20-3040", "Karen",  "Lee",      "2017-03-01", 5, "000-11-2222"),
            ("200-30-4050", "Leo",    "Martin",   "2019-09-12", 2, "333-44-5555"),
        ],
    },
    "_branch_managers": {
        "sql": """
            UPDATE Branch SET manager_ssn = %s, asst_manager_ssn = %s
            WHERE branch_id = %s
        """,
        "rows": [
            ("111-22-3333", "222-33-4444", 1),
            ("333-44-5555", "444-55-6666", 2),
            ("555-66-7777", "666-77-8888", 3),
            ("777-88-9999", "888-99-0000", 4),
            ("000-11-2222", "100-20-3040", 5),
        ],
    },
    "Employee_Phone": {
        "sql": "INSERT INTO Employee_Phone (ssn, phone_number) VALUES (%s, %s)",
        "rows": [
            ("111-22-3333", "212-555-0101"),
            ("111-22-3333", "917-555-0199"),
            ("333-44-5555", "212-555-0202"),
            ("555-66-7777", "312-555-0303"),
            ("777-88-9999", "310-555-0404"),
            ("000-11-2222", "617-555-0505"),
            ("999-00-1111", "212-555-0606"),
        ],
    },
    "Employee_Dependent": {
        "sql": "INSERT INTO Employee_Dependent (ssn, dependent_name) VALUES (%s, %s)",
        "rows": [
            ("111-22-3333", "Tom Morgan"),
            ("111-22-3333", "Sara Morgan"),
            ("555-66-7777", "Lily Johnson"),
            ("777-88-9999", "Max Kim"),
            ("000-11-2222", "Noah Wilson"),
            ("333-44-5555", "Mia Ortiz"),
        ],
    },
    "Customer": {
        "sql": """
            INSERT INTO Customer
                (ssn, first_name, last_name, apt_no, street_no, street_name,
                 city, state, zip_code, phone_number, branch_id, personal_banker_ssn)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        "rows": [
            ("101-01-0001", "Nancy",  "Green",  "4A",  "88",  "Park Avenue",      "New York",    "NY", "10016", "212-555-1001", 1, "999-00-1111"),
            ("202-02-0002", "Oscar",  "Brown",  None,  "240", "Lakeshore Drive",  "Chicago",     "IL", "60614", "312-555-2002", 3, "666-77-8888"),
            ("303-03-0003", "Paula",  "White",  "12B", "55",  "Sunset Boulevard", "Los Angeles", "CA", "90028", "310-555-3003", 4, "888-99-0000"),
            ("404-04-0004", "Quinn",  "Black",  None,  "10",  "Broad Street",     "New York",    "NY", "10004", "212-555-4004", 1, "222-33-4444"),
            ("505-05-0005", "Rachel", "Silver", "7C",  "320", "Michigan Avenue",  "Chicago",     "IL", "60601", "312-555-5005", 3, "555-66-7777"),
            ("606-06-0006", "Sam",    "Gold",   None,  "900", "Wilshire Blvd",    "Los Angeles", "CA", "90024", "310-555-6006", 4, "777-88-9999"),
            ("707-07-0007", "Tina",   "Rose",   "2F",  "45",  "Beacon Street",    "Boston",      "MA", "02108", "617-555-7007", 5, "100-20-3040"),
            ("808-08-0008", "Umar",   "Shah",   None,  "12",  "Tremont Street",   "Boston",      "MA", "02111", "617-555-8008", 5, "000-11-2222"),
        ],
    },
    "Account": {
        "sql": "INSERT INTO Account (account_type, balance, open_date) VALUES (%s, %s, %s)",
        "rows": [
            ("SAVINGS",      5200.00,   "2019-01-10"),
            ("CHECKING",     1850.50,   "2019-01-10"),
            ("MONEY_MARKET", 22000.00,  "2020-06-15"),
            ("SAVINGS",      9500.00,   "2018-03-22"),
            ("CHECKING",     3100.00,   "2021-11-01"),
            ("MONEY_MARKET", 41000.00,  "2017-07-30"),
            ("LOAN",         25000.00,  "2023-04-01"),
            ("LOAN",         10000.00,  "2024-01-15"),
            ("LOAN",         150000.00, "2022-09-01"),
            ("LOAN",         8000.00,   "2025-06-10"),
            ("SAVINGS",      3750.00,   "2022-04-05"),
            ("CHECKING",     640.25,    "2023-08-19"),
        ],
    },
    "Savings_Account": {
        "sql": "INSERT INTO Savings_Account (account_no, interest_rate) VALUES (%s, %s)",
        "rows": [(1, 0.0150), (4, 0.0200), (11, 0.0175)],
    },
    "Checking_Account": {
        "sql": "INSERT INTO Checking_Account (account_no, overdraft_amount) VALUES (%s, %s)",
        "rows": [(2, 0.00), (5, 50.00), (12, 0.00)],
    },
    "MoneyMarket_Account": {
        "sql": """
            INSERT INTO MoneyMarket_Account
                (account_no, current_interest_rate, last_rate_update)
            VALUES (%s, %s, %s)
        """,
        "rows": [
            (3, 0.0425, "2026-03-01 00:00:00+00"),
            (6, 0.0410, "2026-03-01 00:00:00+00"),
        ],
    },
    "Loan_Account": {
        "sql": """
            INSERT INTO Loan_Account
                (account_no, amount, interest_rate, monthly_repayment, branch_id)
            VALUES (%s, %s, %s, %s, %s)
        """,
        "rows": [
            (7,  25000.00,  0.0575, 482.35,  1),
            (8,  10000.00,  0.0620, 215.80,  3),
            (9,  150000.00, 0.0499, 801.40,  4),
            (10,  8000.00,  0.0650, 180.50,  2),
        ],
    },
    "Customer_Account": {
        "sql": """
            INSERT INTO Customer_Account (customer_ssn, account_no, last_access_date)
            VALUES (%s, %s, %s)
        """,
        "rows": [
            ("101-01-0001",  1, "2026-03-10"),
            ("101-01-0001",  2, "2026-03-12"),
            ("101-01-0001",  7, "2026-03-01"),
            ("202-02-0002",  3, "2026-03-08"),
            ("202-02-0002",  8, "2026-02-20"),
            ("303-03-0003",  4, "2026-02-28"),
            ("303-03-0003",  9, "2026-03-15"),
            ("404-04-0004",  2, "2026-03-11"),
            ("404-04-0004",  5, "2026-03-05"),
            ("404-04-0004",  7, "2026-03-01"),
            ("505-05-0005",  6, "2026-03-14"),
            ("505-05-0005", 10, "2026-03-10"),
            ("606-06-0006",  6, "2026-03-14"),
            ("606-06-0006",  9, "2026-03-15"),
            ("707-07-0007", 11, "2026-03-20"),
            ("707-07-0007", 12, "2026-03-22"),
            ("808-08-0008", 12, "2026-03-18"),
        ],
    },
    "Transaction_Log": {
        "sql": """
            INSERT INTO Transaction_Log
                (transaction_code, transaction_name, tran_date, tran_time,
                 amount, account_no, is_chargeable, charge_amount,
                 parent_transaction_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        "rows": [
            ("CD",  "Customer Deposit", "2026-03-10", "09:15:00",  500.00,  1, False, None, None),
            ("WD",  "Withdrawal",       "2026-03-10", "10:30:00",  200.00,  2, True,   2.50, None),
            ("FEE", "Service Charge",   "2026-03-10", "10:30:01",    2.50,  2, False, None,  2),
            ("CD",  "Customer Deposit", "2026-03-11", "14:00:00", 1000.00,  3, False, None, None),
            ("LP",  "Loan Payment",     "2026-03-12", "09:00:00",  482.35,  7, False, None, None),
            ("WD",  "Withdrawal",       "2026-03-12", "08:45:00",  150.00,  2, True,   2.50, None),
            ("FEE", "Service Charge",   "2026-03-12", "08:45:01",    2.50,  2, False, None,  6),
            ("TR",  "Transfer Out",     "2026-03-14", "11:20:00", 5000.00,  6, False, None, None),
            ("CD",  "Customer Deposit", "2026-03-15", "16:00:00",  750.00,  4, False, None, None),
            ("WD",  "Withdrawal",       "2026-03-18", "10:00:00",  300.00,  5, True,   2.50, None),
            ("FEE", "Service Charge",   "2026-03-18", "10:00:01",    2.50,  5, False, None, 10),
            ("LP",  "Loan Payment",     "2026-03-20", "09:00:00",  215.80,  8, False, None, None),
            ("CD",  "Customer Deposit", "2026-03-20", "13:30:00",  200.00, 11, False, None, None),
            ("WD",  "ATM Withdrawal",   "2026-03-22", "17:45:00",  100.00, 12, True,   1.50, None),
            ("FEE", "ATM Fee",          "2026-03-22", "17:45:01",    1.50, 12, False, None, 14),
            ("LP",  "Loan Payment",     "2026-03-25", "09:00:00",  180.50, 10, False, None, None),
        ],
    },
}

SEED_ORDER = [
    "Branch", "Employee", "_branch_managers",
    "Employee_Phone", "Employee_Dependent",
    "Customer", "Account",
    "Savings_Account", "Checking_Account",
    "MoneyMarket_Account", "Loan_Account",
    "Customer_Account", "Transaction_Log",
]


# ══════════════════════════════════════════════════════════════════
# SCHEMA + SEED RUNNERS
# ══════════════════════════════════════════════════════════════════

def create_schema(conn):
    total = len(DDL_STATEMENTS)
    with conn.cursor() as cur:
        for i, (label, stmt) in enumerate(DDL_STATEMENTS, 1):
            try:
                cur.execute(textwrap.dedent(stmt).strip())
                log(f"  {i:2}/{total}  {label}", "OK")
            except psycopg2.Error as e:
                conn.rollback()
                log(f"DDL failed — {label}", "ERROR")
                log(str(e).strip(), "ERROR")
                sys.exit(1)
    conn.commit()
    log("Schema creation complete.", "OK")


def seed_data(conn):
    with conn.cursor() as cur:
        for key in SEED_ORDER:
            entry = SEED_DATA[key]
            label = key.lstrip("_")
            stmt  = textwrap.dedent(entry["sql"]).strip()
            rows  = entry["rows"]
            try:
                cur.executemany(stmt, rows)
                log(f"  Seeded  {label:<22}  ({len(rows)} rows)", "OK")
            except psycopg2.Error as e:
                conn.rollback()
                log(f"Seed failed — {label}: {e}", "ERROR")
                sys.exit(1)
    conn.commit()
    log("All seed data inserted.", "OK")


# ══════════════════════════════════════════════════════════════════
# VERIFICATION
# ══════════════════════════════════════════════════════════════════

VERIFY_TABLES = [
    "Branch", "Employee", "Employee_Phone", "Employee_Dependent",
    "Customer", "Account", "Customer_Account",
    "Savings_Account", "Checking_Account", "MoneyMarket_Account",
    "Loan_Account", "Transaction_Log",
]

def verify(conn):
    bar = "  " + "─" * 40
    print(f"\n{bar}")
    print(f"  {'Table':<26}  {'Rows':>6}")
    print(bar)
    total = 0
    with conn.cursor() as cur:
        for t in VERIFY_TABLES:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            n = cur.fetchone()[0]
            total += n
            flag = "✓" if n >= 5 else "⚠"
            print(f"  {flag}  {t:<24}  {n:>6}")
    print(bar)
    print(f"  {'TOTAL':<26}  {total:>6}")
    print(bar)


# ══════════════════════════════════════════════════════════════════
# CONNECTION INFO BANNER
# ══════════════════════════════════════════════════════════════════

def print_connection_info():
    c = CONFIG
    pg_url = (f"postgresql://{c['db_user']}:{c['db_password']}"
              f"@{c['db_host']}:{c['db_port']}/{c['db_name']}")
    print("""
  ┌──────────────────────────────────────────────────────────┐
  │               BankingDB — Connection Details             │
  ├──────────────────────────────────────────────────────────┤""")
    print(f"  │  Host          : {c['db_host']:<40} │")
    print(f"  │  Port          : {c['db_port']:<40} │")
    print(f"  │  Database      : {c['db_name']:<40} │")
    print(f"  │  User          : {c['db_user']:<40} │")
    print(f"  │  Password      : {c['db_password']:<40} │")
    print(  "  ├──────────────────────────────────────────────────────────┤")
    print(f"  │  psql          : psql -h {c['db_host']} -p {c['db_port']} -U {c['db_user']} {c['db_name']}")
    print(  "  │  SQLAlchemy URL:                                          │")
    print(f"  │    {pg_url}")
    print(  "  ├──────────────────────────────────────────────────────────┤")
    print(  "  │  pgAdmin UI    : http://localhost:5050                    │")
    print(  "  │  pgAdmin login : admin@example.com / admin               │")
    print(  "  └──────────────────────────────────────────────────────────┘")
    print()


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Deploy BankingDB PostgreSQL via docker-compose"
    )
    parser.add_argument(
        "--reset", action="store_true",
        help="Run 'docker compose down -v' first, then redeploy from scratch"
    )
    parser.add_argument(
        "--stop", action="store_true",
        help="Run 'docker compose down' (add --volumes to also delete data)"
    )
    parser.add_argument(
        "--volumes", action="store_true",
        help="Used with --stop: also remove named volumes (wipes all data)"
    )
    parser.add_argument(
        "--schema-only", action="store_true",
        help="Skip compose; connect to existing container and (re)run schema + seed"
    )
    args = parser.parse_args()

    # ── Verify compose file present (always) ──────────────────────
    check_compose_file()

    # ── Stop mode ─────────────────────────────────────────────────
    if args.stop:
        section("Stopping BankingDB")
        compose_down(volumes=args.volumes)
        return

    # ── Schema-only mode ──────────────────────────────────────────
    if args.schema_only:
        section("Schema-Only Mode — Connecting to Existing Container")
        wait_for_postgres()
        conn = get_connection()
        section("Creating Schema")
        create_schema(conn)
        section("Inserting Seed Data")
        seed_data(conn)
        section("Verification")
        verify(conn)
        conn.close()
        print_connection_info()
        return

    # ── Full deploy ───────────────────────────────────────────────
    section("BankingDB — Docker Compose Deployment")
    log(f"Compose file : {CONFIG['compose_file']}", "INFO")
    log(f"Database     : {CONFIG['db_name']} on port {CONFIG['db_port']}", "INFO")

    if args.reset:
        section("Reset — Removing Existing Stack")
        compose_down(volumes=True)
        log("Existing stack and volumes removed.", "OK")

    section("Step 1: docker compose up")

    # Detect already-running container before calling compose up
    state = get_container_state()
    if state == "running" and not args.reset:
        log("Container 'BankingDB' is already running.", "WARN")
        log("Skipping 'docker compose up' to avoid HTTP 304 error.", "INFO")
        log("Tip: run with --reset to tear down and redeploy from scratch.", "INFO")
    else:
        compose_up()

    section("Step 2: Waiting for PostgreSQL to be Ready")
    wait_for_postgres()

    section("Step 3: Creating Schema")
    conn = get_connection()
    conn.autocommit = False
    create_schema(conn)

    section("Step 4: Inserting Seed Data")
    seed_data(conn)

    section("Step 5: Verification")
    verify(conn)
    conn.close()

    section("Deployment Complete ✓")
    print_connection_info()


if __name__ == "__main__":
    main()