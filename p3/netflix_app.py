import os
import hashlib
import secrets
import webbrowser

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import mysql.connector
from PIL import Image, ImageTk, ImageOps

from db_config import DB_CONFIG

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
POSTER_DIR = os.path.join(BASE_DIR, "posters")
os.makedirs(POSTER_DIR, exist_ok=True)


BG_APP = "#0f1115"          
BG_SURFACE = "#161922"     
BG_CARD = "#1b1f2a"        
BG_CARD_HOVER = "#232838"
BG_INPUT = "#20242f"
BORDER = "#2a2f3d"
BORDER_LIGHT = "#343a4a"

FG_PRIMARY = "#eef0f4"
FG_SECONDARY = "#9aa2b3"
FG_MUTED = "#6b7386"

ACCENT = "#5b7fff"       
ACCENT_HOVER = "#4a6ae8"
ACCENT_SOFT = "#232a45"    
WARN = "#e6a23c"
DANGER = "#e5484d"
GOLD = "#e8b923"

FONT_FAMILY = "Segoe UI" if os.name == "nt" else "Helvetica"

F_H1 = (FONT_FAMILY, 26, "bold")
F_H2 = (FONT_FAMILY, 18, "bold")
F_H3 = (FONT_FAMILY, 13, "bold")
F_BODY = (FONT_FAMILY, 10)
F_BODY_BOLD = (FONT_FAMILY, 10, "bold")
F_SMALL = (FONT_FAMILY, 9)
F_SMALL_BOLD = (FONT_FAMILY, 9, "bold")
F_LABEL = (FONT_FAMILY, 9, "bold")

CARD_W, CARD_H = 168, 260
POSTER_W, POSTER_H = 150, 210
COLUMNS = 5

GENRE_CHOICES = ["Action", "Drama", "Romance", "Comedy", "Thriller", "Horror", "Documentary"]



def get_conn():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except mysql.connector.Error as err:
        messagebox.showerror("Database connection failed", str(err))
        raise SystemExit(1)



def hash_password(password, salt=None):
    """Return (salt_hex, hash_hex). Generates a new random salt if none given."""
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, digest


def verify_password(password, salt, expected_hash):
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, expected_hash)



def ensure_users_table():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(120) UNIQUE NOT NULL,
            salt VARCHAR(32) NOT NULL,
            password_hash VARCHAR(64) NOT NULL,
            is_admin TINYINT(1) NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def ensure_default_admin():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
    admin_count = cur.fetchone()[0]
    if admin_count == 0:
        salt, digest = hash_password("admin123")
        cur.execute(
            "INSERT INTO users (username, email, salt, password_hash, is_admin) "
            "VALUES (%s, %s, %s, %s, 1)",
            ("admin", "admin@example.com", salt, digest),
        )
        conn.commit()
        print("Created default admin account -> username: admin / password: admin123")
        print("Please change this password after your first login.")
    cur.close()
    conn.close()


def authenticate(username, password):
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM users WHERE username = %s", (username,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row and verify_password(password, row["salt"], row["password_hash"]):
        return row
    return None


def username_or_email_taken(username, email):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE username = %s OR email = %s", (username, email))
    taken = cur.fetchone() is not None
    cur.close()
    conn.close()
    return taken


def create_user(username, email, password, is_admin=False):
    salt, digest = hash_password(password)
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (username, email, salt, password_hash, is_admin) VALUES (%s, %s, %s, %s, %s)",
        (username, email, salt, digest, int(is_admin)),
    )
    conn.commit()
    new_id = cur.lastrowid
    cur.close()
    conn.close()
    return new_id


def fetch_users():
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT id, username, email, is_admin, created_at FROM users ORDER BY id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def set_user_admin(user_id, is_admin):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_admin = %s WHERE id = %s", (int(is_admin), user_id))
    conn.commit()
    cur.close()
    conn.close()


def delete_user(user_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
    conn.commit()
    cur.close()
    conn.close()



def ensure_trailer_column():
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("SHOW COLUMNS FROM movies LIKE 'trailer_url'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE movies ADD COLUMN trailer_url VARCHAR(500) NULL")
            conn.commit()
    finally:
        cur.close()
        conn.close()


def load_movies():
    """Fetches all movies from the MySQL `movies` table."""
    conn = get_conn()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, title, genre, year, director, rating, poster, description, trailer_url "
        "FROM movies ORDER BY id"
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    movies = []
    for row in rows:
        row["rating"] = float(row["rating"])
        row["year"] = int(row["year"])
        movies.append(row)
    return movies


def insert_movie(data):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO movies (title, genre, year, director, rating, poster, description, trailer_url) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (data["title"], data["genre"], data["year"], data["director"],
         data["rating"], data["poster"], data["description"], data.get("trailer_url", "")),
    )
    conn.commit()
    new_id = cur.lastrowid
    cur.close()
    conn.close()
    return new_id


def update_movie(movie_id, data):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE movies SET title=%s, genre=%s, year=%s, director=%s, rating=%s, "
        "poster=%s, description=%s, trailer_url=%s WHERE id=%s",
        (data["title"], data["genre"], data["year"], data["director"],
         data["rating"], data["poster"], data["description"], data.get("trailer_url", ""), movie_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def delete_movie(movie_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM movies WHERE id = %s", (movie_id,))
    conn.commit()
    cur.close()
    conn.close()


def save_poster_file(src_path, title):
    """Copy a chosen image into posters/ with a safe unique filename;
    returns just the filename (what the `poster` column expects)."""
    ext = os.path.splitext(src_path)[1].lower() or ".jpg"
    safe_name = "".join(c if c.isalnum() else "_" for c in title).strip("_") or "poster"
    dest_name = f"{safe_name}{ext}"
    dest_path = os.path.join(POSTER_DIR, dest_name)
    counter = 1
    while os.path.exists(dest_path):
        dest_name = f"{safe_name}_{counter}{ext}"
        dest_path = os.path.join(POSTER_DIR, dest_name)
        counter += 1
    Image.open(src_path).convert("RGB").save(dest_path, quality=92)
    return dest_name



def styled_entry(parent, show=None, width=28, bg=BG_INPUT):
    """A flat entry with a bottom focus rule, wrapped in its own frame so we
    can draw a 1px border that lights up with the accent color on focus."""
    wrap = tk.Frame(parent, bg=BORDER, highlightthickness=0)
    inner = tk.Frame(wrap, bg=bg)
    inner.pack(fill="both", expand=True, padx=1, pady=1)
    entry = tk.Entry(inner, show=show, width=width, bg=bg, fg=FG_PRIMARY,
                      insertbackground=FG_PRIMARY, relief="flat",
                      font=F_BODY, borderwidth=0)
    entry.pack(fill="both", expand=True, padx=10, pady=8)

    def on_focus_in(_):
        wrap.configure(bg=ACCENT)

    def on_focus_out(_):
        wrap.configure(bg=BORDER)

    entry.bind("<FocusIn>", on_focus_in)
    entry.bind("<FocusOut>", on_focus_out)
    entry.wrap = wrap
    return entry


def field_label(parent, text, bg=None):
    tk.Label(parent, text=text.upper(), bg=bg or parent["bg"], fg=FG_MUTED,
              font=(FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 5))


def primary_button(parent, text, command, fill="x", pady_out=(0, 0)):
    btn = tk.Button(parent, text=text, command=command, bg=ACCENT, fg="white",
                     activebackground=ACCENT_HOVER, activeforeground="white",
                     relief="flat", bd=0, font=F_BODY_BOLD, cursor="hand2", pady=10)
    if fill == "x":
        btn.pack(fill="x", pady=pady_out)
    return btn


def secondary_button(parent, text, command, **pack_kwargs):
    btn = tk.Button(parent, text=text, command=command, bg=BG_CARD, fg=FG_PRIMARY,
                     activebackground=BG_CARD_HOVER, activeforeground=FG_PRIMARY,
                     relief="flat", bd=0, font=F_BODY, cursor="hand2",
                     padx=14, pady=8, highlightthickness=1,
                     highlightbackground=BORDER, highlightcolor=BORDER)
    btn.pack(**pack_kwargs)
    return btn


def ghost_button(parent, text, command, fg=FG_SECONDARY, **pack_kwargs):
    btn = tk.Button(parent, text=text, command=command, bg=parent["bg"], fg=fg,
                     activebackground=parent["bg"], activeforeground=FG_PRIMARY,
                     relief="flat", bd=0, font=F_SMALL_BOLD, cursor="hand2")
    btn.pack(**pack_kwargs)
    return btn


def section_divider(parent, pady=(14, 14)):
    tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=pady)


def configure_ttk_theme(root):
    style = ttk.Style(root)
    style.theme_use("clam")

    style.configure("Dark.TCombobox", fieldbackground=BG_INPUT, background=BG_INPUT,
                     foreground=FG_PRIMARY, arrowcolor=FG_SECONDARY, bordercolor=BORDER,
                     lightcolor=BG_INPUT, darkcolor=BG_INPUT, relief="flat", padding=6)
    style.map("Dark.TCombobox", fieldbackground=[("readonly", BG_INPUT)],
              foreground=[("readonly", FG_PRIMARY)])

    style.configure("Dark.TNotebook", background=BG_APP, borderwidth=0)
    style.configure("Dark.TNotebook.Tab", background="transparent", foreground=FG_SECONDARY,
                     padding=(18, 10), font=F_BODY_BOLD, borderwidth=0)
    style.map("Dark.TNotebook.Tab",
              background=[("selected", BG_APP)],
              foreground=[("selected", FG_PRIMARY)])

    style.configure("Dark.Treeview", background=BG_CARD, fieldbackground=BG_CARD,
                     foreground=FG_PRIMARY, rowheight=32, borderwidth=0, font=F_BODY)
    style.configure("Dark.Treeview.Heading", background=BG_SURFACE, foreground=FG_SECONDARY,
                     font=F_SMALL_BOLD, borderwidth=0, relief="flat")
    style.map("Dark.Treeview.Heading", background=[("active", BG_SURFACE)])
    style.map("Dark.Treeview",
              background=[("selected", ACCENT_SOFT)],
              foreground=[("selected", FG_PRIMARY)])
    style.layout("Dark.Treeview", [("Dark.Treeview.treearea", {"sticky": "nswe"})])

    style.configure("Dark.Vertical.TScrollbar", background=BG_SURFACE, troughcolor=BG_APP,
                     bordercolor=BG_APP, arrowcolor=FG_MUTED, relief="flat")
    style.map("Dark.Vertical.TScrollbar", background=[("active", BORDER_LIGHT)])
    return style



class LoginScreen(tk.Frame):
    def __init__(self, master, on_login_success, on_create_account):
        super().__init__(master, bg=BG_APP)
        self.pack(fill="both", expand=True)
        self.on_login_success = on_login_success
        self.on_create_account = on_create_account
        self._build()

    def _build(self):
        outer = tk.Frame(self, bg=BORDER)
        outer.place(relx=0.5, rely=0.5, anchor="center")
        card = tk.Frame(outer, bg=BG_SURFACE, padx=48, pady=42)
        card.pack(padx=1, pady=1)

        # Brand mark
        brand_row = tk.Frame(card, bg=BG_SURFACE)
        brand_row.pack(pady=(0, 4))
        tk.Label(brand_row, text="\u25B6", font=(FONT_FAMILY, 16, "bold"),
                 fg=ACCENT, bg=BG_SURFACE).pack(side="left", padx=(0, 8))
        tk.Label(brand_row, text="STREAMBOX", font=(FONT_FAMILY, 20, "bold"),
                 fg=FG_PRIMARY, bg=BG_SURFACE).pack(side="left")

        tk.Label(card, text="Sign in to continue", font=F_BODY,
                 fg=FG_SECONDARY, bg=BG_SURFACE).pack(pady=(0, 26))

       
        field_label(card, "Username", bg=BG_SURFACE)
        self.username_entry = styled_entry(card, width=28)
        self.username_entry.wrap.pack(fill="x", pady=(0, 14))

        field_label(card, "Password", bg=BG_SURFACE)
        self.password_entry = styled_entry(card, show="\u2022", width=28)
        self.password_entry.wrap.pack(fill="x", pady=(0, 6))
        self.password_entry.bind("<Return>", lambda e: self.attempt_login())

        self.error_label = tk.Label(card, text="", bg=BG_SURFACE, fg=DANGER,
                                     font=F_SMALL, wraplength=300, justify="left")
        self.error_label.pack(anchor="w", pady=(4, 4))

        primary_button(card, "Sign In", self.attempt_login, pady_out=(12, 18))

        section_divider(card, pady=(0, 16))

        bottom = tk.Frame(card, bg=BG_SURFACE)
        bottom.pack(fill="x")
        tk.Label(bottom, text="New here?", bg=BG_SURFACE, fg=FG_SECONDARY,
                 font=F_SMALL).pack(side="left")
        link = tk.Label(bottom, text=" Create an account", bg=BG_SURFACE, fg=ACCENT,
                         font=F_SMALL_BOLD, cursor="hand2")
        link.pack(side="left")
        link.bind("<Button-1>", lambda e: self.on_create_account())

    def attempt_login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get()
        if not username or not password:
            self.error_label.configure(text="Enter both username and password.")
            return

        user = authenticate(username, password)
        if not user:
            self.error_label.configure(text="Invalid username or password.")
            return

       
        self.on_login_success(user)



class CreateAccountScreen(tk.Frame):
    def __init__(self, master, on_back, on_created):
        super().__init__(master, bg=BG_APP)
        self.pack(fill="both", expand=True)
        self.on_back = on_back
        self.on_created = on_created
        self._build()

    def _build(self):
        outer = tk.Frame(self, bg=BORDER)
        outer.place(relx=0.5, rely=0.5, anchor="center")
        card = tk.Frame(outer, bg=BG_SURFACE, padx=48, pady=40)
        card.pack(padx=1, pady=1)

        tk.Label(card, text="Create your account", font=F_H2,
                 fg=FG_PRIMARY, bg=BG_SURFACE).pack(anchor="w")
        tk.Label(card, text="It only takes a minute.", font=F_BODY,
                 fg=FG_SECONDARY, bg=BG_SURFACE).pack(anchor="w", pady=(2, 22))

        field_label(card, "Username", bg=BG_SURFACE)
        self.username_entry = styled_entry(card, width=30)
        self.username_entry.wrap.pack(fill="x", pady=(0, 12))

        field_label(card, "Email", bg=BG_SURFACE)
        self.email_entry = styled_entry(card, width=30)
        self.email_entry.wrap.pack(fill="x", pady=(0, 12))

        field_label(card, "Password", bg=BG_SURFACE)
        self.password_entry = styled_entry(card, show="\u2022", width=30)
        self.password_entry.wrap.pack(fill="x", pady=(0, 12))

        field_label(card, "Confirm Password", bg=BG_SURFACE)
        self.confirm_entry = styled_entry(card, show="\u2022", width=30)
        self.confirm_entry.wrap.pack(fill="x", pady=(0, 6))
        self.confirm_entry.bind("<Return>", lambda e: self.submit())

        self.error_label = tk.Label(card, text="", bg=BG_SURFACE, fg=DANGER,
                                     font=F_SMALL, wraplength=300, justify="left")
        self.error_label.pack(anchor="w", pady=(4, 4))

        primary_button(card, "Create Account", self.submit, pady_out=(12, 16))

        back_link = tk.Label(card, text="\u2190  Back to login", bg=BG_SURFACE, fg=FG_SECONDARY,
                              font=F_SMALL_BOLD, cursor="hand2")
        back_link.pack()
        back_link.bind("<Button-1>", lambda e: self.on_back())

    def submit(self):
        username = self.username_entry.get().strip()
        email = self.email_entry.get().strip()
        password = self.password_entry.get()
        confirm = self.confirm_entry.get()

        if not username or not email or not password:
            self.error_label.configure(text="All fields are required.")
            return
        if "@" not in email or "." not in email.split("@")[-1]:
            self.error_label.configure(text="Enter a valid email address.")
            return
        if len(password) < 6:
            self.error_label.configure(text="Password must be at least 6 characters.")
            return
        if password != confirm:
            self.error_label.configure(text="Passwords do not match.")
            return
        if username_or_email_taken(username, email):
            self.error_label.configure(text="That username or email is already registered.")
            return

        create_user(username, email, password, is_admin=False)
        messagebox.showinfo("Account created", "Your account was created. You can now log in.")
        self.on_created()



class MovieDashboard(tk.Frame):
    def __init__(self, master, user, on_logout, on_back_admin=None):
        super().__init__(master, bg=BG_APP)
        self.pack(fill="both", expand=True)
        self.user = user
        self.on_logout = on_logout
        self.on_back_admin = on_back_admin
        configure_ttk_theme(self)

        self.movies = load_movies()
        self.poster_cache = {}
        self.poster_cache_big = {}

        self._build_header()
        self._build_filter_bar()
        self._build_movie_grid_area()

        self.render_movies(self.movies)


    def _build_header(self):
        header = tk.Frame(self, bg=BG_SURFACE)
        header.pack(fill="x")
        inner = tk.Frame(header, bg=BG_SURFACE)
        inner.pack(fill="x", padx=32, pady=18)

        brand = tk.Frame(inner, bg=BG_SURFACE)
        brand.pack(side="left")
        tk.Label(brand, text="\u25B6", font=(FONT_FAMILY, 13, "bold"),
                 fg=ACCENT, bg=BG_SURFACE).pack(side="left", padx=(0, 6))
        tk.Label(brand, text="STREAMBOX", font=(FONT_FAMILY, 13, "bold"),
                 fg=FG_PRIMARY, bg=BG_SURFACE).pack(side="left")

        right = tk.Frame(inner, bg=BG_SURFACE)
        right.pack(side="right")

        avatar = tk.Label(right, text=self.user["username"][:1].upper(), bg=ACCENT, fg="white",
                           font=F_SMALL_BOLD, width=2, height=1)
        avatar.pack(side="left", padx=(0, 10))
        tk.Label(right, text=self.user["username"], bg=BG_SURFACE, fg=FG_PRIMARY,
                 font=F_BODY_BOLD).pack(side="left", padx=(0, 16))

        
        if self.on_back_admin:
            secondary_button(right, "\u2190 Back to Admin", self.on_back_admin, side="left", padx=(0, 8))
        secondary_button(right, "Log out", self.on_logout, side="left")

        section_divider(self, pady=(0, 0))

        title_row = tk.Frame(self, bg=BG_APP)
        title_row.pack(fill="x", padx=32, pady=(24, 4))
        tk.Label(title_row, text="Recommended For You", font=F_H1,
                 fg=FG_PRIMARY, bg=BG_APP, anchor="w").pack(side="left")
        tk.Label(title_row, text="Tamil Cinema Picks", font=F_BODY_BOLD,
                 fg=ACCENT, bg=BG_APP, anchor="w").pack(side="left", padx=(12, 0), pady=(8, 0))

    def _build_filter_bar(self):
        bar_wrap = tk.Frame(self, bg=BG_APP)
        bar_wrap.pack(fill="x", padx=32, pady=(14, 6))

        bar_outer = tk.Frame(bar_wrap, bg=BORDER)
        bar_outer.pack(fill="x")
        bar = tk.Frame(bar_outer, bg=BG_SURFACE, padx=16, pady=14)
        bar.pack(fill="x", padx=1, pady=1)

        search_wrap = tk.Frame(bar, bg=BORDER)
        search_wrap.pack(side="left")
        search_frame = tk.Frame(search_wrap, bg=BG_INPUT)
        search_frame.pack(padx=1, pady=1)

        tk.Label(search_frame, text="\U0001F50D", bg=BG_INPUT, fg=FG_MUTED,
                 font=F_BODY).pack(side="left", padx=(10, 4), pady=8)

        self.search_var = tk.StringVar()
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, width=28,
                                 bg=BG_INPUT, fg=FG_PRIMARY, insertbackground=FG_PRIMARY,
                                 relief="flat", font=F_BODY, borderwidth=0)
        search_entry.pack(side="left", ipady=6, padx=(0, 10))
        search_entry.bind("<KeyRelease>", lambda e: self.apply_filters())
        self._placeholder(search_entry, "Search movies or directors...")

        genres = ["All Genres"] + sorted({m["genre"] for m in self.movies})
        directors = ["All Directors"] + sorted({m["director"] for m in self.movies})
        ratings = ["All Ratings", "9.0+", "8.5+", "8.0+", "7.5+", "7.0+", "6.0+"]

        self.genre_var = tk.StringVar(value=genres[0])
        self.director_var = tk.StringVar(value=directors[0])
        self.rating_var = tk.StringVar(value=ratings[0])

        self._make_dropdown(bar, "Genre", self.genre_var, genres)
        self._make_dropdown(bar, "Director", self.director_var, directors)
        self._make_dropdown(bar, "Rating", self.rating_var, ratings)

        secondary_button(bar, "Reset", self.reset_filters, side="left", padx=(15, 0))

        self.result_label = tk.Label(bar, text="", bg=BG_SURFACE, fg=FG_MUTED, font=F_SMALL)
        self.result_label.pack(side="right")

    def _placeholder(self, entry, text):
        entry.insert(0, text)
        entry.config(fg=FG_MUTED)

        def on_focus_in(_):
            if entry.get() == text:
                entry.delete(0, tk.END)
                entry.config(fg=FG_PRIMARY)

        def on_focus_out(_):
            if not entry.get():
                entry.insert(0, text)
                entry.config(fg=FG_MUTED)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        self._search_placeholder_text = text

    def _make_dropdown(self, parent, label, var, values):
        frame = tk.Frame(parent, bg=BG_SURFACE)
        frame.pack(side="left", padx=(16, 0))
        tk.Label(frame, text=label.upper(), bg=BG_SURFACE, fg=FG_MUTED,
                 font=(FONT_FAMILY, 8, "bold")).pack(anchor="w", pady=(0, 4))
        combo = ttk.Combobox(frame, textvariable=var, values=values, state="readonly",
                              width=16, style="Dark.TCombobox", font=F_BODY)
        combo.pack()
        combo.bind("<<ComboboxSelected>>", lambda e: self.apply_filters())
        return combo

    def _build_movie_grid_area(self):
        container = tk.Frame(self, bg=BG_APP)
        container.pack(fill="both", expand=True, padx=22, pady=10)

        self.canvas = tk.Canvas(container, bg=BG_APP, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview,
                                   style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.grid_frame = tk.Frame(self.canvas, bg=BG_APP)
        self.grid_window = self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")

        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", lambda e: self.canvas.yview_scroll(-2, "units"))
        self.canvas.bind_all("<Button-5>", lambda e: self.canvas.yview_scroll(2, "units"))

    def _on_canvas_resize(self, event):
        self.canvas.itemconfig(self.grid_window, width=event.width)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------- Poster
    def get_poster(self, poster_file, size, cache):
        key = (poster_file, size)
        if key in cache:
            return cache[key]
        path = os.path.join(POSTER_DIR, poster_file)
        try:
            img = Image.open(path).convert("RGB")
            img = ImageOps.fit(img, size, Image.LANCZOS)
        except (FileNotFoundError, OSError):
            img = Image.new("RGB", size, BG_INPUT)
        photo = ImageTk.PhotoImage(img)
        cache[key] = photo
        return photo

   
    def render_movies(self, movies):
        for widget in self.grid_frame.winfo_children():
            widget.destroy()

        if not movies:
            empty = tk.Frame(self.grid_frame, bg=BG_APP)
            empty.grid(row=0, column=0, padx=20, pady=60)
            tk.Label(empty, text="No movies match your filters", bg=BG_APP,
                     fg=FG_PRIMARY, font=F_H3).pack()
            tk.Label(empty, text="Try adjusting your search or filters.", bg=BG_APP,
                     fg=FG_MUTED, font=F_SMALL).pack(pady=(4, 0))
            self.result_label.config(text="0 movies found")
            return

        self.result_label.config(text=f"{len(movies)} movie(s) found")

        for i, movie in enumerate(movies):
            row, col = divmod(i, COLUMNS)
            self._make_card(self.grid_frame, movie, row, col)

        for c in range(COLUMNS):
            self.grid_frame.grid_columnconfigure(c, weight=1)

    def _make_card(self, parent, movie, row, col):
        outer = tk.Frame(parent, bg=BORDER, cursor="hand2")
        outer.grid(row=row, column=col, padx=12, pady=12)
        card = tk.Frame(outer, bg=BG_CARD, width=CARD_W, height=CARD_H)
        card.pack(padx=1, pady=1)
        card.pack_propagate(False)

        photo = self.get_poster(movie["poster"], (POSTER_W, POSTER_H), self.poster_cache)
        poster_wrap = tk.Frame(card, bg=BG_CARD)
        poster_wrap.pack(pady=(10, 8))
        poster_label = tk.Label(poster_wrap, image=photo, bg=BG_CARD)
        poster_label.image = photo
        poster_label.pack()

        title_label = tk.Label(card, text=movie["title"], bg=BG_CARD, fg=FG_PRIMARY,
                                font=F_BODY_BOLD, wraplength=CARD_W - 20, justify="center")
        title_label.pack(padx=10)

        meta_row = tk.Frame(card, bg=BG_CARD)
        meta_row.pack(pady=(4, 0))
        tk.Label(meta_row, text=movie["genre"], bg=BG_CARD, fg=FG_MUTED,
                  font=F_SMALL).pack(side="left")
        tk.Label(meta_row, text=f"  \u2605 {movie['rating']}", bg=BG_CARD, fg=GOLD,
                  font=F_SMALL_BOLD).pack(side="left")

        widgets = [outer, card, poster_wrap, poster_label, title_label, meta_row] + list(meta_row.winfo_children())

        def on_enter(_):
            outer.configure(bg=ACCENT)
            for w in widgets:
                if w is not outer:
                    try:
                        w.configure(bg=BG_CARD_HOVER)
                    except tk.TclError:
                        pass

        def on_leave(_):
            outer.configure(bg=BORDER)
            for w in widgets:
                if w is not outer:
                    try:
                        w.configure(bg=BG_CARD)
                    except tk.TclError:
                        pass

        def on_click(_):
            self.show_detail(movie)

        for w in widgets:
            w.bind("<Enter>", on_enter)
            w.bind("<Leave>", on_leave)
            w.bind("<Button-1>", on_click)


    def apply_filters(self):
        query = self.search_var.get().strip().lower()
        if query == self._search_placeholder_text.lower():
            query = ""

        genre = self.genre_var.get()
        director = self.director_var.get()
        rating_choice = self.rating_var.get()

        min_rating = 0.0
        if rating_choice != "All Ratings":
            min_rating = float(rating_choice.replace("+", ""))

        def matches(m):
            if query and query not in m["title"].lower() and query not in m["director"].lower():
                return False
            if genre != "All Genres" and m["genre"] != genre:
                return False
            if director != "All Directors" and m["director"] != director:
                return False
            if m["rating"] < min_rating:
                return False
            return True

        self.render_movies([m for m in self.movies if matches(m)])

    def reset_filters(self):
        self.search_var.set("")
        self.genre_var.set("All Genres")
        self.director_var.set("All Directors")
        self.rating_var.set("All Ratings")
        self.render_movies(self.movies)


    def show_detail(self, movie):
        popup = tk.Toplevel(self)
        popup.title(movie["title"])
        popup.configure(bg=BG_APP)
        popup.geometry("660x600")
        popup.transient(self)

        top = tk.Frame(popup, bg=BG_APP)
        top.pack(fill="x", padx=26, pady=26)

        big_photo = self.get_poster(movie["poster"], (220, 300), self.poster_cache_big)
        poster_outer = tk.Frame(top, bg=BORDER)
        poster_outer.pack(side="left", padx=(0, 22))
        poster_label = tk.Label(poster_outer, image=big_photo, bg=BG_APP)
        poster_label.image = big_photo
        poster_label.pack(padx=1, pady=1)

        info = tk.Frame(top, bg=BG_APP)
        info.pack(side="left", fill="both", expand=True)

        tk.Label(info, text=movie["title"], bg=BG_APP, fg=FG_PRIMARY, font=F_H2,
                 wraplength=360, justify="left").pack(anchor="w")
        meta = tk.Frame(info, bg=BG_APP)
        meta.pack(anchor="w", pady=(8, 0))
        tk.Label(meta, text=movie["genre"], bg=BG_INPUT, fg=FG_SECONDARY,
                 font=F_SMALL_BOLD, padx=10, pady=3).pack(side="left")
        tk.Label(meta, text=f" {movie['year']}", bg=BG_APP, fg=FG_MUTED,
                 font=F_BODY).pack(side="left", padx=(10, 0))
        tk.Label(info, text=f"Directed by {movie['director']}", bg=BG_APP, fg=FG_SECONDARY,
                 font=F_BODY).pack(anchor="w", pady=(10, 0))
        tk.Label(info, text=f"\u2605 {movie['rating']} / 10", bg=BG_APP, fg=GOLD,
                 font=F_BODY_BOLD).pack(anchor="w", pady=(6, 0))
        tk.Label(info, text=movie["description"], bg=BG_APP, fg=FG_SECONDARY, font=F_BODY,
                 wraplength=360, justify="left").pack(anchor="w", pady=(14, 0))

        def watch_trailer():
            url = (movie.get("trailer_url") or "").strip()
            if not url:
                messagebox.showinfo("Trailer not available",
                                    "No YouTube trailer link has been added for this movie.",
                                    parent=popup)
                return
            webbrowser.open(url)

        primary_button(info, "\u25B6  Watch Trailer", watch_trailer, fill=None)
        info.winfo_children()[-1].pack(anchor="w", pady=(18, 0), ipadx=8)

        section_divider(popup, pady=(4, 10))

        tk.Label(popup, text="More Like This", bg=BG_APP, fg=FG_PRIMARY,
                 font=F_H3).pack(anchor="w", padx=26, pady=(0, 10))

        strip = tk.Frame(popup, bg=BG_APP)
        strip.pack(fill="x", padx=26)

        similar = [m for m in self.movies if m["genre"] == movie["genre"] and m["title"] != movie["title"]][:4]
        for m in similar:
            mini_outer = tk.Frame(strip, bg=BORDER, cursor="hand2")
            mini_outer.pack(side="left", padx=6)
            mini = tk.Frame(mini_outer, bg=BG_CARD, padx=6, pady=6)
            mini.pack(padx=1, pady=1)
            photo = self.get_poster(m["poster"], (90, 130), self.poster_cache)
            lbl = tk.Label(mini, image=photo, bg=BG_CARD)
            lbl.image = photo
            lbl.pack()
            name_lbl = tk.Label(mini, text=m["title"], bg=BG_CARD, fg=FG_SECONDARY, font=F_SMALL,
                     wraplength=90)
            name_lbl.pack(pady=(4, 0))
            for w in (mini_outer, mini, lbl, name_lbl):
                w.bind("<Button-1>", lambda e, mv=m: (popup.destroy(), self.show_detail(mv)))

        tk.Frame(popup, bg=BG_APP, height=10).pack()
        secondary_button(popup, "Close", popup.destroy, pady=20)



class AdminDashboard(tk.Frame):
    def __init__(self, master, user, on_logout, on_view_site=None):
        super().__init__(master, bg=BG_APP)
        self.pack(fill="both", expand=True)
        self.user = user
        self.on_logout = on_logout
        self.on_view_site = on_view_site
        configure_ttk_theme(self)

        self._build_header()
        self._build_tabs()
        self.refresh_movies()
        self.refresh_users()

    def _build_header(self):
        header = tk.Frame(self, bg=BG_SURFACE)
        header.pack(fill="x")
        inner = tk.Frame(header, bg=BG_SURFACE)
        inner.pack(fill="x", padx=32, pady=18)

        brand = tk.Frame(inner, bg=BG_SURFACE)
        brand.pack(side="left")
        tk.Label(brand, text="\u25B6", font=(FONT_FAMILY, 13, "bold"),
                 fg=ACCENT, bg=BG_SURFACE).pack(side="left", padx=(0, 6))
        tk.Label(brand, text="STREAMBOX", font=(FONT_FAMILY, 13, "bold"),
                 fg=FG_PRIMARY, bg=BG_SURFACE).pack(side="left", padx=(0, 10))
        tk.Label(brand, text="ADMIN", bg=ACCENT_SOFT, fg=ACCENT, font=(FONT_FAMILY, 8, "bold"),
                 padx=8, pady=2).pack(side="left")

        right = tk.Frame(inner, bg=BG_SURFACE)
        right.pack(side="right")
        avatar = tk.Label(right, text=self.user["username"][:1].upper(), bg=ACCENT, fg="white",
                           font=F_SMALL_BOLD, width=2, height=1)
        avatar.pack(side="left", padx=(0, 10))
        tk.Label(right, text=self.user["username"], bg=BG_SURFACE, fg=FG_PRIMARY,
                 font=F_BODY_BOLD).pack(side="left", padx=(0, 16))

        if self.on_view_site:
            secondary_button(right, "\u25B6 View Main Site", self.on_view_site, side="left", padx=(0, 8))
        secondary_button(right, "Log out", self.on_logout, side="left")

        section_divider(self, pady=(0, 0))

        title_row = tk.Frame(self, bg=BG_APP)
        title_row.pack(fill="x", padx=32, pady=(22, 4))
        tk.Label(title_row, text="Admin Dashboard", font=F_H1,
                 fg=FG_PRIMARY, bg=BG_APP).pack(side="left")
        tk.Label(title_row, text="Manage catalog and accounts", font=F_BODY,
                 fg=FG_MUTED, bg=BG_APP).pack(side="left", padx=(14, 0), pady=(8, 0))

    def _build_tabs(self):
        notebook = ttk.Notebook(self, style="Dark.TNotebook")
        notebook.pack(fill="both", expand=True, padx=32, pady=(14, 24))

        self.movies_tab = tk.Frame(notebook, bg=BG_APP)
        self.users_tab = tk.Frame(notebook, bg=BG_APP)
        notebook.add(self.movies_tab, text="  Movies  ")
        notebook.add(self.users_tab, text="  Users  ")

        self._build_movies_tab()
        self._build_users_tab()

    
    def _build_movies_tab(self):
        toolbar = tk.Frame(self.movies_tab, bg=BG_APP)
        toolbar.pack(fill="x", pady=(14, 10))

        primary_button(toolbar, "+ Add Movie", self.open_add_movie, fill=None)
        toolbar.winfo_children()[-1].pack(side="left", ipadx=6)
        secondary_button(toolbar, "Edit Selected", self.open_edit_movie, side="left", padx=(10, 0))
        secondary_button(toolbar, "Delete Selected", self.delete_selected_movie, side="left", padx=(10, 0))
        ghost_button(toolbar, "\u21BB Refresh", self.refresh_movies, side="right")

        table_outer = tk.Frame(self.movies_tab, bg=BORDER)
        table_outer.pack(fill="both", expand=True)
        table_inner = tk.Frame(table_outer, bg=BG_CARD)
        table_inner.pack(fill="both", expand=True, padx=1, pady=1)
        table_inner.grid_rowconfigure(0, weight=1)
        table_inner.grid_columnconfigure(0, weight=1)

        columns = ("id", "title", "genre", "year", "director", "rating", "trailer")
        self.movie_tree = ttk.Treeview(table_inner, columns=columns, show="headings",
                                        style="Dark.Treeview", height=16)
        headings = {"id": "ID", "title": "Title", "genre": "Genre", "year": "Year",
                    "director": "Director", "rating": "Rating", "trailer": "Trailer"}
        widths = {"id": 50, "title": 240, "genre": 110, "year": 70, "director": 170, "rating": 70, "trailer": 100}
        for col in columns:
            self.movie_tree.heading(col, text=headings[col])
            self.movie_tree.column(col, width=widths[col], anchor="w")

        movie_scroll = ttk.Scrollbar(table_inner, orient="vertical", command=self.movie_tree.yview,
                                      style="Dark.Vertical.TScrollbar")
        self.movie_tree.configure(yscrollcommand=movie_scroll.set)

        self.movie_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        movie_scroll.grid(row=0, column=1, sticky="ns", padx=(2, 8), pady=8)
        self.movie_tree.tag_configure("odd", background=BG_CARD)
        self.movie_tree.tag_configure("even", background=BG_SURFACE)

    def refresh_movies(self):
        for row in self.movie_tree.get_children():
            self.movie_tree.delete(row)
        self._movies_by_id = {}
        for idx, m in enumerate(load_movies()):
            self._movies_by_id[m["id"]] = m
            tag = "even" if idx % 2 == 0 else "odd"
            self.movie_tree.insert("", "end", iid=str(m["id"]), tags=(tag,),
                                    values=(m["id"], m["title"], m["genre"], m["year"],
                                            m["director"], m["rating"],
                                            "Added" if m.get("trailer_url") else "Not added"))

    def _selected_movie(self):
        sel = self.movie_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a movie in the table first.")
            return None
        return self._movies_by_id.get(int(sel[0]))

    def open_add_movie(self):
        MovieFormDialog(self, on_saved=self.refresh_movies)

    def open_edit_movie(self):
        movie = self._selected_movie()
        if movie:
            MovieFormDialog(self, on_saved=self.refresh_movies, movie=movie)

    def delete_selected_movie(self):
        movie = self._selected_movie()
        if not movie:
            return
        if messagebox.askyesno("Delete Movie", f'Delete "{movie["title"]}"? This cannot be undone.'):
            delete_movie(movie["id"])
            self.refresh_movies()

    def _build_users_tab(self):
        toolbar = tk.Frame(self.users_tab, bg=BG_APP)
        toolbar.pack(fill="x", pady=(14, 10))

        secondary_button(toolbar, "Toggle Admin", self.toggle_selected_admin, side="left")
        secondary_button(toolbar, "Delete User", self.delete_selected_user, side="left", padx=(10, 0))
        ghost_button(toolbar, "\u21BB Refresh", self.refresh_users, side="right")

        table_outer = tk.Frame(self.users_tab, bg=BORDER)
        table_outer.pack(fill="both", expand=True)
        table_inner = tk.Frame(table_outer, bg=BG_CARD)
        table_inner.pack(fill="both", expand=True, padx=1, pady=1)
        table_inner.grid_rowconfigure(0, weight=1)
        table_inner.grid_columnconfigure(0, weight=1)

        columns = ("id", "username", "email", "is_admin", "created_at")
        self.user_tree = ttk.Treeview(table_inner, columns=columns, show="headings",
                                       style="Dark.Treeview", height=16)
        headings = {"id": "ID", "username": "Username", "email": "Email",
                    "is_admin": "Admin?", "created_at": "Joined"}
        widths = {"id": 50, "username": 160, "email": 230, "is_admin": 80, "created_at": 170}
        for col in columns:
            self.user_tree.heading(col, text=headings[col])
            self.user_tree.column(col, width=widths[col], anchor="w")

        user_scroll = ttk.Scrollbar(table_inner, orient="vertical", command=self.user_tree.yview,
                                     style="Dark.Vertical.TScrollbar")
        self.user_tree.configure(yscrollcommand=user_scroll.set)

        self.user_tree.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        user_scroll.grid(row=0, column=1, sticky="ns", padx=(2, 8), pady=8)
        self.user_tree.tag_configure("odd", background=BG_CARD)
        self.user_tree.tag_configure("even", background=BG_SURFACE)

    def refresh_users(self):
        for row in self.user_tree.get_children():
            self.user_tree.delete(row)
        self._users_by_id = {}
        for idx, u in enumerate(fetch_users()):
            self._users_by_id[u["id"]] = u
            tag = "even" if idx % 2 == 0 else "odd"
            self.user_tree.insert("", "end", iid=str(u["id"]), tags=(tag,),
                                   values=(u["id"], u["username"], u["email"],
                                           "Yes" if u["is_admin"] else "No", u["created_at"]))

    def _selected_user(self):
        sel = self.user_tree.selection()
        if not sel:
            messagebox.showinfo("No selection", "Select a user in the table first.")
            return None
        return self._users_by_id.get(int(sel[0]))

    def toggle_selected_admin(self):
        target = self._selected_user()
        if not target:
            return
        if target["id"] == self.user["id"] and target["is_admin"]:
            messagebox.showwarning("Not allowed", "You can't remove your own admin access.")
            return
        set_user_admin(target["id"], not target["is_admin"])
        self.refresh_users()

    def delete_selected_user(self):
        target = self._selected_user()
        if not target:
            return
        if target["id"] == self.user["id"]:
            messagebox.showwarning("Not allowed", "You can't delete the account you're logged in with.")
            return
        if messagebox.askyesno("Delete User", f'Delete user "{target["username"]}"?'):
            delete_user(target["id"])
            self.refresh_users()


class MovieFormDialog(tk.Toplevel):
    """Add/Edit movie form used by the Admin Dashboard."""

    def __init__(self, master, on_saved, movie=None):
        super().__init__(master, bg=BG_APP)
        self.on_saved = on_saved
        self.movie = movie
        self.title("Edit Movie" if movie else "Add Movie")
        self.geometry("460x700")
        self.minsize(400, 320)
        self.configure(bg=BG_APP)
        self.grab_set()
        self.chosen_image_path = None
        self._build()

    def _build(self):
        header = tk.Frame(self, bg=BG_SURFACE)
        header.pack(fill="x")
        tk.Label(header, text="Edit Movie" if self.movie else "Add New Movie",
                 bg=BG_SURFACE, fg=FG_PRIMARY, font=F_H3).pack(anchor="w", padx=24, pady=14)

       
        scroll_container = tk.Frame(self, bg=BG_APP)
        scroll_container.pack(fill="both", expand=True)

        canvas = tk.Canvas(scroll_container, bg=BG_APP, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview,
                                   style="Dark.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        body = tk.Frame(canvas, bg=BG_APP)
        body_window = canvas.create_window((0, 0), window=body, anchor="nw")

        def on_body_configure(_event):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event):
            canvas.itemconfig(body_window, width=event.width)

        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def on_mousewheel_linux_up(_event):
            canvas.yview_scroll(-2, "units")

        def on_mousewheel_linux_down(_event):
            canvas.yview_scroll(2, "units")

        def bind_scroll(_event=None):
            canvas.bind_all("<MouseWheel>", on_mousewheel)
            canvas.bind_all("<Button-4>", on_mousewheel_linux_up)
            canvas.bind_all("<Button-5>", on_mousewheel_linux_down)

        def unbind_scroll(_event=None):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        body.bind("<Configure>", on_body_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.bind("<Enter>", bind_scroll)
        canvas.bind("<Leave>", unbind_scroll)
        self.bind("<Destroy>", unbind_scroll)

        body_inner = tk.Frame(body, bg=BG_APP)
        body_inner.pack(fill="both", expand=True, padx=24, pady=16)
        body = body_inner

        def label(text):
            field_label(body, text, bg=BG_APP)

        label("Title")
        self.title_entry = styled_entry(body, width=30)
        self.title_entry.wrap.pack(fill="x", pady=(0, 14))

        label("Genre")
        self.genre_var = tk.StringVar(value=GENRE_CHOICES[0])
        genre_combo = ttk.Combobox(body, textvariable=self.genre_var, values=GENRE_CHOICES,
                                    state="readonly", style="Dark.TCombobox", font=F_BODY)
        genre_combo.pack(fill="x", ipady=5, pady=(0, 14))

        row = tk.Frame(body, bg=BG_APP)
        row.pack(fill="x", pady=(0, 14))
        year_col = tk.Frame(row, bg=BG_APP)
        year_col.pack(side="left", fill="x", expand=True)
        field_label(year_col, "Year", bg=BG_APP)
        self.year_entry = styled_entry(year_col, width=10)
        self.year_entry.wrap.pack(fill="x")

        rating_col = tk.Frame(row, bg=BG_APP)
        rating_col.pack(side="left", fill="x", expand=True, padx=(12, 0))
        field_label(rating_col, "Rating (0-10)", bg=BG_APP)
        self.rating_entry = styled_entry(rating_col, width=10)
        self.rating_entry.wrap.pack(fill="x")

        label("Director")
        self.director_entry = styled_entry(body, width=30)
        self.director_entry.wrap.pack(fill="x", pady=(0, 14))

        label("Description")
        desc_wrap = tk.Frame(body, bg=BORDER)
        desc_wrap.pack(fill="x", pady=(0, 14))
        self.desc_text = tk.Text(desc_wrap, height=4, bg=BG_INPUT, fg=FG_PRIMARY,
                                  insertbackground=FG_PRIMARY, relief="flat", font=F_BODY,
                                  wrap="word", borderwidth=0)
        self.desc_text.pack(fill="x", padx=1, pady=1, ipadx=8, ipady=8)

        label("YouTube Trailer Link")
        self.trailer_entry = styled_entry(body, width=30)
        self.trailer_entry.wrap.pack(fill="x", pady=(0, 4))
        tk.Label(body, text="Example: https://www.youtube.com/watch?v=VIDEO_ID",
                 fg=FG_MUTED, bg=BG_APP, font=(FONT_FAMILY, 8)).pack(anchor="w", pady=(0, 14))

        label("Poster Image")
        preview_outer = tk.Frame(body, bg=BORDER)
        preview_outer.pack(pady=(2, 8))
        self.preview_label = tk.Label(preview_outer, bg=BG_INPUT, text="No image selected",
                                       fg=FG_MUTED, font=F_SMALL, width=20, height=8)
        self.preview_label.pack(padx=1, pady=1)

        secondary_button(body, "Choose Image...", self.choose_image, fill="x", pady=(0, 8))
        body.winfo_children()[-1].pack_configure(fill="x")

        primary_button(body, "Save Movie", self.save, pady_out=(10, 20))

        if self.movie:
            self._prefill()

    def _prefill(self):
        m = self.movie
        self.title_entry.insert(0, m["title"])
        self.genre_var.set(m["genre"] if m["genre"] in GENRE_CHOICES else GENRE_CHOICES[0])
        self.year_entry.insert(0, str(m["year"]))
        self.rating_entry.insert(0, str(m["rating"]))
        self.director_entry.insert(0, m["director"])
        self.desc_text.insert("1.0", m.get("description") or "")
        self.trailer_entry.insert(0, m.get("trailer_url") or "")

        poster_path = os.path.join(POSTER_DIR, m["poster"])
        if os.path.exists(poster_path):
            try:
                preview = Image.open(poster_path).convert("RGB")
                preview = ImageOps.fit(preview, (140, 190), Image.LANCZOS)
                photo = ImageTk.PhotoImage(preview)
                self.preview_label.configure(image=photo, text="", width=140, height=190)
                self.preview_label.image = photo
            except Exception:
                pass

    def choose_image(self):
        path = filedialog.askopenfilename(
            title="Choose a poster image",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.webp *.bmp")]
        )
        if not path:
            return
        self.chosen_image_path = path
        try:
            preview = Image.open(path).convert("RGB")
            preview = ImageOps.fit(preview, (140, 190), Image.LANCZOS)
            photo = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=photo, text="", width=140, height=190)
            self.preview_label.image = photo
        except Exception:
            self.preview_label.configure(text="Couldn't preview that file", image="")

    def save(self):
        title = self.title_entry.get().strip()
        director = self.director_entry.get().strip()
        if not title or not director:
            messagebox.showerror("Missing info", "Title and director are required.", parent=self)
            return
        try:
            year = int(self.year_entry.get().strip())
        except ValueError:
            messagebox.showerror("Invalid year", "Year must be a number.", parent=self)
            return
        try:
            rating = max(0.0, min(10.0, float(self.rating_entry.get().strip())))
        except ValueError:
            messagebox.showerror("Invalid rating", "Rating must be a number between 0 and 10.", parent=self)
            return

        poster_filename = self.movie["poster"] if self.movie else None
        if self.chosen_image_path:
            try:
                poster_filename = save_poster_file(self.chosen_image_path, title)
            except Exception as exc:
                messagebox.showerror("Image error", f"Couldn't save that image:\n{exc}", parent=self)
                return
        if not poster_filename:
            messagebox.showerror("Missing poster", "Please choose a poster image.", parent=self)
            return

        data = {
            "title": title,
            "genre": self.genre_var.get(),
            "year": year,
            "director": director,
            "rating": rating,
            "poster": poster_filename,
            "description": self.desc_text.get("1.0", "end").strip(),
            "trailer_url": self.trailer_entry.get().strip(),
        }

        if self.movie:
            update_movie(self.movie["id"], data)
        else:
            insert_movie(data)

        self.destroy()
        self.on_saved()



class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("StreamBox")
        self.geometry("1280x820")
        self.configure(bg=BG_APP)
        self.minsize(1024, 680)
        configure_ttk_theme(self)

        ensure_users_table()
        ensure_default_admin()
        ensure_trailer_column()

        self.current_user = None
        self.show_login()

    def _clear(self):
        for w in self.winfo_children():
            w.destroy()

    def show_login(self):
        self._clear()
        LoginScreen(self, on_login_success=self.handle_login, on_create_account=self.show_create_account)

    def show_create_account(self):
        self._clear()
        CreateAccountScreen(self, on_back=self.show_login, on_created=self.show_login)

    def handle_login(self, user):
        self.current_user = user
        self._clear()
        if user["is_admin"]:
            self.show_admin()
        else:
            MovieDashboard(self, user, on_logout=self.logout)

    def show_admin(self):
        """Admin Dashboard for the currently logged-in admin."""
        self._clear()
        AdminDashboard(self, self.current_user, on_logout=self.logout, on_view_site=self.show_site_preview)

    def show_site_preview(self):
        """Lets an admin browse the regular Movie Dashboard (the 'main
        page') without logging out — 'Back to Admin' returns them here."""
        self._clear()
        MovieDashboard(self, self.current_user, on_logout=self.logout, on_back_admin=self.show_admin)

    def logout(self):
        self.current_user = None
        self.show_login()


if __name__ == "__main__":
    app = App()
    app.mainloop()