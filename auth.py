"""Authentication blueprint — email/password + Google OAuth."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_bcrypt import Bcrypt
from flask_login import login_user, logout_user, current_user

from models.user import User

auth_bp = Blueprint("auth", __name__)
bcrypt = Bcrypt()


def _get_storage():
    """Import storage from app module (avoids circular imports)."""
    from app import storage
    return storage


def _get_oauth_client():
    """Get the Google OAuth client (lazy import)."""
    from app import oauth
    return oauth.google


def _claim_orphans(user):
    """On first login, claim any entries with no user_id."""
    storage = _get_storage()
    claimed = storage.claim_orphaned_entries(user.id)
    if claimed:
        print(f"Claimed {claimed} orphaned entries for user {user.email}")


# ── Email / Password ───────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = _get_storage().get_user_by_email(email)
        if user and user.password_hash and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            _claim_orphans(user)
            next_page = request.args.get("next") or url_for("index")
            return redirect(next_page)

        flash("Invalid email or password.", "error")

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Email and password are required.", "error")
            return render_template("register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("register.html")

        if _get_storage().get_user_by_email(email):
            flash("An account with that email already exists.", "error")
            return render_template("register.html")

        user = User(
            email=email,
            password_hash=bcrypt.generate_password_hash(password).decode("utf-8"),
            name=name or email.split("@")[0],
        )
        _get_storage().create_user(user)
        login_user(user, remember=True)
        _claim_orphans(user)
        return redirect(url_for("index"))

    return render_template("register.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))


# ── Google OAuth ───────────────────────────────────────────────

@auth_bp.route("/auth/google")
def google_login():
    redirect_uri = url_for("auth.google_callback", _external=True)
    return _get_oauth_client().authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    token = _get_oauth_client().authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        flash("Could not retrieve your Google account info.", "error")
        return redirect(url_for("auth.login"))

    google_id = userinfo["sub"]
    email = userinfo.get("email", "").lower()
    name = userinfo.get("name", "")
    avatar = userinfo.get("picture", "")
    refresh_token = token.get("refresh_token", "")

    storage = _get_storage()

    # 1. Already linked?
    user = storage.get_user_by_google_id(google_id)
    if user:
        user.avatar_url = avatar
        if refresh_token:
            user.google_refresh_token = refresh_token
        storage.update_user(user)
        login_user(user, remember=True)
        _claim_orphans(user)
        return redirect(url_for("index"))

    # 2. Existing account with same email? Link Google.
    user = storage.get_user_by_email(email)
    if user:
        user.google_id = google_id
        user.avatar_url = avatar
        if not user.name:
            user.name = name
        if refresh_token:
            user.google_refresh_token = refresh_token
        storage.update_user(user)
        login_user(user, remember=True)
        _claim_orphans(user)
        return redirect(url_for("index"))

    # 3. New user via Google
    user = User(
        email=email,
        name=name or email.split("@")[0],
        google_id=google_id,
        avatar_url=avatar,
        google_refresh_token=refresh_token,
    )
    storage.create_user(user)
    login_user(user, remember=True)
    _claim_orphans(user)
    return redirect(url_for("index"))
