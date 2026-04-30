# BankingDB — Database Triggers

All triggers are defined in `add_loan_balance_protection.sql` and are included automatically in fresh deployments via `deploy_bankingdb.py`.

To apply to an existing database:
```bash
psql -h localhost -p 5433 -U bankadmin bankingdb -f add_loan_balance_protection.sql
```

---

## Trigger Summary

| Trigger | Table | Timing | Event | Action |
|---|---|---|---|---|
| `trg_prevent_savings_deletion` | `savings_account` | BEFORE | DELETE | Block if balance > 0 |
| `trg_prevent_checking_deletion` | `checking_account` | BEFORE | DELETE | Block if balance > 0 |
| `trg_prevent_mm_deletion` | `moneymarket_account` | BEFORE | DELETE | Block if balance > 0 |
| `trg_prevent_loan_deletion` | `loan_account` | BEFORE | DELETE | Block if balance > 0 |
| `trg_prevent_account_deletion` | `account` | BEFORE | DELETE | Block if balance > 0 |
| `trg_prevent_customer_deletion` | `customer` | BEFORE | DELETE | Block if any linked account has balance > 0 |
| `trg_prevent_customer_account_deletion` | `customer_account` | BEFORE | DELETE | Block removal of last customer link if account balance > 0 |
| `trg_cleanup_orphaned_account` | `customer_account` | AFTER | DELETE | Auto-delete account if last holder removed and balance = $0.00 |

---

## Trigger Details

### 1. `trg_prevent_savings_deletion`
**Table:** `savings_account` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_subtype_deletion_with_balance()`

Fires before a row is deleted from the `savings_account` subtype table. Looks up the corresponding balance from the `account` supertype. If the balance is greater than $0.00, the deletion is blocked and an error is raised identifying the account number and outstanding amount.

**Error example:**
```
Cannot delete SAVINGS Account #1 — outstanding balance of $5200.00.
The balance must be $0.00 before the account can be closed.
```

---

### 2. `trg_prevent_checking_deletion`
**Table:** `checking_account` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_subtype_deletion_with_balance()`

Same logic as the savings trigger — fires before a `checking_account` row is deleted. Checks the account balance from the `account` table and blocks the deletion if funds remain.

**Error example:**
```
Cannot delete CHECKING Account #5 — outstanding balance of $3100.00.
The balance must be $0.00 before the account can be closed.
```

---

### 3. `trg_prevent_mm_deletion`
**Table:** `moneymarket_account` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_subtype_deletion_with_balance()`

Fires before a `moneymarket_account` row is deleted. Prevents removal of any money market account that still holds a balance, protecting variable-rate account balances from being lost through accidental deletion.

**Error example:**
```
Cannot delete MONEY_MARKET Account #3 — outstanding balance of $22000.00.
The balance must be $0.00 before the account can be closed.
```

---

### 4. `trg_prevent_loan_deletion`
**Table:** `loan_account` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_subtype_deletion_with_balance()`

Fires before a `loan_account` row is deleted. Ensures that an outstanding loan cannot be written off by simply deleting the record — the full principal must be repaid (balance = $0.00) before the loan account can be removed.

**Error example:**
```
Cannot delete LOAN Account #7 — outstanding balance of $25000.00.
The balance must be $0.00 before the account can be closed.
```

---

### 5. `trg_prevent_account_deletion`
**Table:** `account` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_account_deletion_with_balance()`

Fires before any row is deleted from the `account` supertype table. This is a safety net that catches deletions attempted directly at the supertype level — which would otherwise cascade down to the subtype table via `ON DELETE CASCADE` without the subtype triggers firing first.

Protects all four account types (SAVINGS, CHECKING, MONEY_MARKET, LOAN) from the top level.

**Error example:**
```
Cannot delete Account #5 (CHECKING) — outstanding balance of $3100.00.
The balance must reach $0.00 before this account can be closed.
```

---

### 6. `trg_prevent_customer_deletion`
**Table:** `customer` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_customer_deletion_with_balance()`

Fires before a customer row is deleted. Loops through every account linked to the customer via `customer_account` and raises an exception for the first account found with a balance greater than $0.00.

This prevents a customer record from being removed while they still have funds in any account — even if they share that account with another customer.

**Error example:**
```
Cannot delete customer Rachel Silver — Account #6 (MONEY_MARKET)
has an outstanding balance of $41000.00.
All account balances must be $0.00 before the customer can be removed.
```

---

### 7. `trg_prevent_customer_account_deletion`
**Table:** `customer_account` &nbsp;|&nbsp; **Timing:** BEFORE DELETE &nbsp;|&nbsp; **Function:** `prevent_customer_account_deletion_with_balance()`

Fires before any row is deleted directly from the `customer_account` junction table. This closes the gap where a user could run `DELETE FROM customer_account WHERE customer_ssn = '...'` and bypass all other balance protection triggers.

The trigger only blocks the deletion if this is the **last customer** linked to that account. If other customers still hold the account (shared account), the link can be removed freely. If this is the last holder and the account balance is greater than $0.00, the deletion is blocked.

**Error example:**
```
Cannot remove the last customer link for CHECKING Account #2 —
outstanding balance of $1850.50.
The balance must be $0.00 before the account can be unlinked or closed.
```

---

### 8. `trg_cleanup_orphaned_account`
**Table:** `customer_account` &nbsp;|&nbsp; **Timing:** AFTER DELETE &nbsp;|&nbsp; **Function:** `cleanup_orphaned_account()`

Fires after a row is deleted from the `customer_account` junction table — either explicitly or as a result of a `customer` row being deleted (which cascades to `customer_account`).

After the junction row is removed, the trigger checks whether any other customers still hold that account:

- **If other holders remain** — the account stays as-is (shared account, still owned by other customers)
- **If no holders remain AND balance = $0.00** — the orphaned `account` row is automatically deleted, which cascades to remove the subtype row (`savings_account`, `checking_account`, etc.)
- **If no holders remain AND balance > 0** — the account is left in place (the balance protection triggers would block deletion anyway)

This prevents ghost accounts from accumulating in the database after customers are removed.

---

## Trigger Functions

| Function | Used By |
|---|---|
| `prevent_subtype_deletion_with_balance()` | Triggers 1–4 (all subtype tables share this single function) |
| `prevent_account_deletion_with_balance()` | Trigger 5 (`account` supertype) |
| `prevent_customer_deletion_with_balance()` | Trigger 6 (`customer` table) |
| `prevent_customer_account_deletion_with_balance()` | Trigger 7 (`customer_account` — direct unlink protection) |
| `cleanup_orphaned_account()` | Trigger 8 (`customer_account` — orphan cleanup) |

---

## Verify Triggers Are Active

Run in pgAdmin or psql to confirm all seven triggers are installed:

```sql
SELECT trigger_name,
       event_object_table AS "table",
       event_manipulation AS "event",
       action_timing      AS "timing"
FROM   information_schema.triggers
WHERE  trigger_schema = 'public'
ORDER  BY event_object_table, trigger_name;
```

---

*BankingDB — CS631 Database Systems*