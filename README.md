# BankingDB — Term Project
### CS631 Database Systems

A full-stack banking database application built with **PostgreSQL 16**, **Docker**, **Python (Flask)**, and **pgAdmin 4**.

---

## Project Overview

BankingDB models a multi-branch bank with customers, employees, accounts, loans, and financial transactions. The web application provides three core views:

- **Customer view** — log in to see your own accounts, balances, transaction history, deposit funds, send money to other customers, and transfer between your own accounts
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
        ├── login.html                    # Login page
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

---

## Services

| Service | URL |
|---------|-----|
| Web Application | http://localhost:5055 |
| pgAdmin | http://localhost:5050 |

---

*CS631 Database Systems — Term Project*