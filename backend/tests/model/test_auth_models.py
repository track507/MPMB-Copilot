from app.model.orm import AuthSession, Base, LoginAttempt, User


def test_auth_tables_registered():
    tables = Base.metadata.tables
    assert "users" in tables
    assert "auth_sessions" in tables
    assert "login_attempts" in tables


def test_users_columns():
    cols = Base.metadata.tables["users"].columns
    assert cols["password_hash"].nullable is True  # ! nullable by design: OIDC/JIT users
    assert cols["username"].nullable is False
    assert cols["disabled"].nullable is False


def test_auth_session_fk_cascade():
    fk = next(iter(Base.metadata.tables["auth_sessions"].columns["user_id"].foreign_keys))
    assert fk.ondelete == "CASCADE"


def test_models_importable():
    assert User.__tablename__ == "users"
    assert AuthSession.__tablename__ == "auth_sessions"
    assert LoginAttempt.__tablename__ == "login_attempts"
