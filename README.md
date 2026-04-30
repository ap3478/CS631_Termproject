# BankingDB — Term Project
### CS631 Database Systems

A full-stack banking database application built with **PostgreSQL 16**, **Docker**, **Python (Flask)**, and **pgAdmin 4**.

---

## Project Overview

BankingDB models a multi-branch bank with customers, employees, accounts, loans, and financial transactions. The web application provides three core views:

- **Customer view** — register and open an account, log in to see accounts, balances, transaction history, deposit funds, send money to other customers, and transfer between your own accounts
- **Admin view** — bank-wide overview of all customers, accounts, and branches, with the ability to transfer funds on behalf of any customer
- **Account detail view** — full transaction history and account-specific information for any account

---

## Project Structure

```
cs631_termproject/
│
├── docker-compose.yml          # PostgreSQL 16 + pgAdmin 4 services
├── deploy_bankingdb.py         # Deploys DB containers, schema, and seed data
├── add_phone_number.sql        # Migration: adds phone_number to Customer table
├── pgpass                      # pgAdmin auto-authentication file
├── pgadmin_servers.json        # pgAdmin pre-configured server entry
├── requirements.txt            # Dependencies for deploy script
│
└── banking_app/                # Flask web application
    ├── app.py                  # Main application and all routes
    ├── requirements.txt        # Dependencies for web app
    └── templates/
        ├── base.html                     # Shared layout and navigation
        ├── login.html                    # Login page with Open Account link
        ├── register.html                 # 5-step account registration wizard
        ├── customer_dashboard.html       # Customer account overview
        ├── account_detail.html           # Account and transaction detail
        ├── deposit.html                  # Deposit funds into an account
        ├── send.html                     # Send money by phone number (Zelle-style)
        ├── transfer.html                 # Transfer between own accounts
        ├── admin_dashboard.html          # Admin bank-wide overview
        ├── admin_accounts.html           # All accounts with search/filter
        ├── admin_customer_detail.html    # Admin customer profile
        └── admin_transfer.html           # Admin transfer on behalf of customer
```

---

## Application Features

### Account Registration
- New customers can open an account directly from the login page via a **5-step wizard**:
  1. **Account Type** — choose Savings (1.50% p.a.), Checking, or Money Market (4.00% variable)
  2. **Branch Location** — select from all available branches
  3. **Personal Details** — name, SSN (auto-formatted), phone number, full address
  4. **Login Details** — choose a username, password (with live strength indicator), and confirmation
  5. **Review & Open** — summary of all selections before submitting
- On success the account is created, the customer record is inserted, and the user is automatically logged in
- Loan accounts require branch approval and cannot be self-registered

### Customer
- View all linked accounts — Savings, Checking, Money Market, and Loan
- Account balances, interest rates, overdraft limits, and loan repayment details
- Full transaction history per account
- **Deposit** — add funds to any non-loan account with quick-amount buttons and an optional description
- **Send Money** — send funds to any other BankingDB customer by entering their registered phone number (Zelle-style). The recipient is found by phone lookup and funds are credited to their primary account automatically
- **Transfer** — move funds between your own accounts (non-loan only)

### Admin
- Bank-wide statistics — total assets, deposits, customer and account counts
- Account type breakdown and branch summary tables
- Browse and search all accounts across all branches
- View individual customer profiles with phone number, address, and account details
- **Transfer on behalf of customer** — select a customer, choose source and destination accounts, and execute the transfer

### Transactions
- Every deposit, send, and transfer creates transaction log entries with descriptive names
- Transaction codes: `CD` Deposit · `SND` Send · `RCV` Receive · `TRO` Transfer Out · `TRI` Transfer In
- Admin-initiated transfers are labelled distinctly in the transaction log
- Loan accounts are excluded from all deposit, send, and transfer operations

### Database Notes
- The `app_users` table is created automatically the **first time `python app.py` is run** — it will not appear in pgAdmin until the web app has been started at least once
- To query it in pgAdmin use: `SELECT * FROM app_users;`

---

## Installation

### Visual Studio Code

#### macOS
1. Download from [https://code.visualstudio.com](https://code.visualstudio.com)
2. Open the `.zip` and drag **Visual Studio Code.app** to Applications
3. In VS Code press `Cmd+Shift+P` → **Shell Command: Install 'code' command in PATH**

#### Windows
1. Download from [https://code.visualstudio.com](https://code.visualstudio.com)
2. Run the `.exe` installer and check **Add to PATH** during setup

---

### Python

#### macOS
```bash
# Option A — Official installer
# Download from https://www.python.org/downloads and run the .pkg

# Option B — Homebrew
brew install python

# Verify
python3 --version
```

#### Windows (native)
1. Download from [https://www.python.org/downloads](https://www.python.org/downloads)
2. Run the installer and check **Add Python to PATH**
3. Verify in PowerShell: `python --version`

#### Windows (inside WSL 2)
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv
```

---

### Docker Desktop

#### macOS
1. Download from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop) — choose **Apple Silicon** or **Intel** as appropriate
2. Open the `.dmg` and drag Docker to Applications
3. Open Docker Desktop and wait for it to fully start

#### Windows
> Install WSL 2 first (see below) before installing Docker Desktop.

1. Download from [https://www.docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
2. Run the installer and ensure **Use WSL 2 instead of Hyper-V** is checked
3. Restart when prompted and open Docker Desktop

---

### WSL 2 — Windows Only

WSL 2 is required for Docker Desktop on Windows.

**Open PowerShell as Administrator and run:**
```powershell
wsl --install
```
This installs Ubuntu and the WSL 2 kernel. Restart when prompted, then complete the Ubuntu username and password setup.

**After restarting — update Ubuntu packages:**
```bash
sudo apt update && sudo apt upgrade -y
```

**Enable Docker Desktop WSL integration:**
Docker Desktop → Settings → Resources → WSL Integration → enable Ubuntu → Apply & Restart

**Access your project files from WSL:**
```bash
cd /mnt/c/Users/YourUsername/cs631_termproject
```

---

## Running the Project

### 1. Deploy the Database

Make sure **Docker Desktop is open and running**, then from the project root:

```bash
pip3 install -r requirements.txt
python3 deploy_bankingdb.py
```

| Flag | Action |
|------|--------|
| `python3 deploy_bankingdb.py` | First-time deploy |
| `python3 deploy_bankingdb.py --reset` | Wipe and redeploy from scratch |
| `python3 deploy_bankingdb.py --stop` | Stop containers (data preserved) |
| `python3 deploy_bankingdb.py --stop --volumes` | Stop and delete all data |

> **Note:** If the database was previously deployed without the `phone_number` column, run the migration script before starting the web app:
> ```bash
> psql -h localhost -p 5433 -U bankadmin bankingdb -f add_phone_number.sql
> ```

### 2. Start the Web Application

Open a **new terminal**, then:

```bash
cd cs631_termproject/banking_app
pip3 install -r requirements.txt
python3 app.py
```

Open your browser and go to **[http://localhost:5055](http://localhost:5055)**

> The `app_users` table is created automatically on first startup.

---

## Database Triggers

Seven `BEFORE`/`AFTER DELETE` triggers enforce data integrity at the database level, independently of the application layer.

| Trigger | Table | Protects |
|---------|-------|---------|
| `trg_prevent_savings_deletion` | `savings_account` | Block delete if balance > $0.00 |
| `trg_prevent_checking_deletion` | `checking_account` | Block delete if balance > $0.00 |
| `trg_prevent_mm_deletion` | `moneymarket_account` | Block delete if balance > $0.00 |
| `trg_prevent_loan_deletion` | `loan_account` | Block delete if balance > $0.00 |
| `trg_prevent_account_deletion` | `account` | Block delete of any account type with balance > $0.00 |
| `trg_prevent_customer_deletion` | `customer` | Block delete if any linked account has balance > $0.00 |
| `trg_prevent_customer_account_deletion` | `customer_account` | Block removal of last customer link if account balance > $0.00 |
| `trg_cleanup_orphaned_account` | `customer_account` | Auto-delete account when last customer link removed and balance = $0.00 |

Triggers are created automatically during `python3 deploy_bankingdb.py`. To apply them to an existing database:

```bash
psql -h localhost -p 5433 -U bankadmin bankingdb -f add_loan_balance_protection.sql
```

### Verify triggers are active

Run in pgAdmin or psql:

```sql
SELECT trigger_name,
       event_object_table AS "table",
       event_manipulation AS "event",
       action_timing      AS "timing"
FROM   information_schema.triggers
WHERE  trigger_schema = 'public'
ORDER  BY event_object_table, trigger_name;
```

You should see **8 rows** — one for each trigger listed above. For full documentation of each trigger see `TRIGGERS.md`.

---

## Services

| Service | URL |
|---------|-----|
| Web Application | http://localhost:5055 |
| pgAdmin | http://localhost:5050 |

---

*CS631 Database Systems — Term Project*