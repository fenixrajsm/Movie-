import sys
import hashlib
import secrets

try:
    import mysql.connector
except ImportError:
    print("FAIL: mysql-connector-python isn't installed.")
    print("      Run: pip install mysql-connector-python")
    sys.exit(1)

try:
    from db_config import DB_CONFIG
except ImportError:
    print("FAIL: Couldn't import DB_CONFIG from db_config.py.")
    print("      Make sure db_config.py is in the same folder as this script.")
    sys.exit(1)


def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, digest


def verify_password(password, salt, expected_hash):
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, expected_hash)


def main():
    print("=" * 60)
    print("STEP 1: Connecting to the database")
    print("=" * 60)
    print(f"host={DB_CONFIG.get('host')}  db={DB_CONFIG.get('database')}  user={DB_CONFIG.get('user')}")
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        print("PASS: Connected successfully.\n")
    except mysql.connector.Error as err:
        print(f"FAIL: Could not connect — {err}")
        print("      Check host/user/password/database in db_config.py, and that")
        print("      MySQL is actually running.")
        sys.exit(1)

    cur = conn.cursor()

    print("=" * 60)
    print("STEP 2: Checking the `users` table")
    print("=" * 60)
    cur.execute("SHOW TABLES LIKE 'users'")
    if not cur.fetchone():
        print("FAIL: No `users` table exists in this database yet.")
        print("      Run the main app once (streambox_mysql.py) — it creates this")
        print("      table automatically on startup via ensure_users_table().")
        cur.close()
        conn.close()
        sys.exit(1)
    print("PASS: `users` table exists.")

    cur.execute("DESCRIBE users")
    columns = {row[0] for row in cur.fetchall()}
    required = {"id", "username", "email", "salt", "password_hash", "is_admin", "created_at"}
    missing = required - columns
    if missing:
        print(f"FAIL: `users` table is missing columns: {sorted(missing)}")
        print("      This usually means a `users` table already existed (from something")
        print("      else, or an earlier version) before the app tried to create its own,")
        print("      so CREATE TABLE IF NOT EXISTS silently did nothing.")
        print("      Fix: rename/drop the old table, e.g.:")
        print("          RENAME TABLE users TO users_old;")
        print("      then re-run the app so it creates a fresh, correct `users` table.")
        cur.close()
        conn.close()
        sys.exit(1)
    print(f"PASS: All required columns present: {sorted(required)}\n")

    print("=" * 60)
    print("STEP 3: Looking for an admin account")
    print("=" * 60)
    cur.execute("SELECT id, username, email, salt, password_hash, is_admin FROM users WHERE is_admin = 1")
    admins = cur.fetchall()
    if not admins:
        print("FAIL: No user has is_admin = 1.")
        print("      Either ensure_default_admin() never ran (run the main app once,")
        print("      it does this automatically on startup), or every admin flag got")
        print("      toggled off. Quick manual fix:")
        print("          UPDATE users SET is_admin = 1 WHERE username = 'admin';")
        cur.close()
        conn.close()
        sys.exit(1)

    print(f"PASS: Found {len(admins)} admin account(s):")
    for row in admins:
        uid, username, email, salt, pw_hash, is_admin = row
        print(f"   id={uid}  username={username!r}  email={email!r}  is_admin={is_admin!r} (type={type(is_admin).__name__})")
    print()

    print("=" * 60)
    print("STEP 4: Test a login")
    print("=" * 60)
    try:
        test_username = input("Enter the admin username to test [admin]: ").strip() or "admin"
        test_password = input("Enter the password to test [admin123]: ").strip() or "admin123"
    except EOFError:
        print("(no interactive input available — skipping live password test)")
        cur.close()
        conn.close()
        return

    cur.execute("SELECT * FROM users WHERE username = %s", (test_username,))
    row = cur.fetchone()
    col_names = [d[0] for d in cur.description]
    if not row:
        print(f"FAIL: No user found with username {test_username!r}.")
        print("      Check for typos, trailing spaces, or case — MySQL's default")
        print("      collation is usually case-insensitive, but confirm the exact value:")
        cur.execute("SELECT username FROM users")
        print("      Existing usernames:", [r[0] for r in cur.fetchall()])
    else:
        user = dict(zip(col_names, row))
        ok = verify_password(test_password, user["salt"], user["password_hash"])
        if ok:
            print(f"PASS: Password matches for {test_username!r}.")
            if user["is_admin"]:
                print("PASS: This account has is_admin = 1 — admin login should work.")
                print("      If it still fails in the app, the bug is in the app's login")
                print("      flow itself, not the data — let me know and I'll check that.")
            else:
                print("FAIL: This account has is_admin = 0 — it's a regular user, not an admin.")
                print("      Fix: UPDATE users SET is_admin = 1 WHERE username = "
                      f"'{test_username}';")
        else:
            print(f"FAIL: Password does NOT match the stored hash for {test_username!r}.")
            print("      You're typing the wrong password for this account. If this is")
            print("      supposed to be the default admin, the default is 'admin123' —")
            print("      unless it was already changed, or a different `users` table")
            print("      (from a previous test) already had an 'admin' row before this")
            print("      version of the app ran, in which case ensure_default_admin()")
            print("      skipped creating a fresh one (it only runs when NO admin exists).")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
