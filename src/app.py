"""
High School Management System API.

Students can browse activities and sign up without an account. Staff accounts
are persisted separately and use role-based access for management operations.
"""

from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from typing import Iterator, Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

current_dir = Path(__file__).parent

# In-memory activity database
activities = {
    "Chess Club": {
        "description": "Learn strategies and compete in chess tournaments",
        "schedule": "Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 12,
        "participants": ["michael@mergington.edu", "daniel@mergington.edu"]
    },
    "Programming Class": {
        "description": "Learn programming fundamentals and build software projects",
        "schedule": "Tuesdays and Thursdays, 3:30 PM - 4:30 PM",
        "max_participants": 20,
        "participants": ["emma@mergington.edu", "sophia@mergington.edu"]
    },
    "Gym Class": {
        "description": "Physical education and sports activities",
        "schedule": "Mondays, Wednesdays, Fridays, 2:00 PM - 3:00 PM",
        "max_participants": 30,
        "participants": ["john@mergington.edu", "olivia@mergington.edu"]
    },
    "Soccer Team": {
        "description": "Join the school soccer team and compete in matches",
        "schedule": "Tuesdays and Thursdays, 4:00 PM - 5:30 PM",
        "max_participants": 22,
        "participants": ["liam@mergington.edu", "noah@mergington.edu"]
    },
    "Basketball Team": {
        "description": "Practice and play basketball with the school team",
        "schedule": "Wednesdays and Fridays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["ava@mergington.edu", "mia@mergington.edu"]
    },
    "Art Club": {
        "description": "Explore your creativity through painting and drawing",
        "schedule": "Thursdays, 3:30 PM - 5:00 PM",
        "max_participants": 15,
        "participants": ["amelia@mergington.edu", "harper@mergington.edu"]
    },
    "Drama Club": {
        "description": "Act, direct, and produce plays and performances",
        "schedule": "Mondays and Wednesdays, 4:00 PM - 5:30 PM",
        "max_participants": 20,
        "participants": ["ella@mergington.edu", "scarlett@mergington.edu"]
    },
    "Math Club": {
        "description": "Solve challenging problems and participate in math competitions",
        "schedule": "Tuesdays, 3:30 PM - 4:30 PM",
        "max_participants": 10,
        "participants": ["james@mergington.edu", "benjamin@mergington.edu"]
    },
    "Debate Team": {
        "description": "Develop public speaking and argumentation skills",
        "schedule": "Fridays, 4:00 PM - 5:30 PM",
        "max_participants": 12,
        "participants": ["charlotte@mergington.edu", "henry@mergington.edu"]
    }
}


def database_path() -> Path:
    return Path(os.environ.get(
        "STAFF_DATABASE_PATH", str(current_dir / "staff.sqlite3")
    ))


@contextmanager
def connect_database() -> Iterator[sqlite3.Connection]:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def auth_secret() -> str:
    secret = os.environ.get("AUTH_SECRET_KEY", "")
    if len(secret) < 32:
        raise RuntimeError("AUTH_SECRET_KEY must contain at least 32 characters")
    return secret


def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 600_000
    )
    return f"{salt.hex()}:{digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    salt_hex, expected_digest = password_hash.split(":", maxsplit=1)
    actual_digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 600_000
    ).hex()
    return hmac.compare_digest(actual_digest, expected_digest)


def initialize_staff_store() -> None:
    auth_secret()
    admin_username = os.environ.get("INITIAL_ADMIN_USERNAME", "").strip()
    admin_password = os.environ.get("INITIAL_ADMIN_PASSWORD", "")
    if not admin_username or len(admin_password) < 12:
        raise RuntimeError(
            "Set INITIAL_ADMIN_USERNAME and an INITIAL_ADMIN_PASSWORD "
            "of at least 12 characters"
        )

    with connect_database() as connection:
        with connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS staff_users (
                    username TEXT PRIMARY KEY COLLATE NOCASE,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('admin', 'organizer')),
                    assignments TEXT NOT NULL DEFAULT '[]',
                    active INTEGER NOT NULL DEFAULT 1
                )
                """
            )
            row = connection.execute(
                "SELECT role FROM staff_users WHERE username = ?",
                (admin_username,),
            ).fetchone()
            if row is None:
                connection.execute(
                    """
                    INSERT INTO staff_users
                        (username, password_hash, role, assignments, active)
                    VALUES (?, ?, 'admin', '[]', 1)
                    """,
                    (admin_username, hash_password(admin_password)),
                )
            elif row["role"] != "admin":
                raise RuntimeError(
                    "INITIAL_ADMIN_USERNAME is already assigned to an organizer"
                )


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_staff_store()
    yield


app = FastAPI(
    title="Mergington High School API",
    description="API for viewing and signing up for extracurricular activities",
    lifespan=lifespan,
)
app.mount(
    "/static",
    StaticFiles(directory=os.path.join(current_dir, "static")),
    name="static",
)


@dataclass(frozen=True)
class StaffUser:
    username: str
    role: str
    assignments: list[str]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class OrganizerCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    assignments: list[str] = Field(default_factory=list)


class OrganizerUpdate(BaseModel):
    password: Optional[str] = Field(default=None, min_length=12, max_length=256)
    assignments: Optional[list[str]] = None


security = HTTPBearer(auto_error=False)
TOKEN_LIFETIME_SECONDS = 8 * 60 * 60


def get_current_staff(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> StaffUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid staff authentication is required",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = jwt.decode(
            credentials.credentials,
            auth_secret(),
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        raise unauthorized
    username = payload.get("sub")
    if not isinstance(username, str) or not username:
        raise unauthorized

    with connect_database() as connection:
        row = connection.execute(
            """
            SELECT username, role, assignments, active
            FROM staff_users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if row is None or not row["active"]:
        raise unauthorized
    return StaffUser(
        username=row["username"],
        role=row["role"],
        assignments=json.loads(row["assignments"]),
    )


def require_admin(user: StaffUser = Depends(get_current_staff)) -> StaffUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator access is required",
        )
    return user


def ensure_valid_assignments(assignments: list[str]) -> None:
    if len(assignments) != len(set(assignments)):
        raise HTTPException(status_code=400, detail="Assignments must be unique")
    unknown = sorted(set(assignments) - set(activities))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown activities: {', '.join(unknown)}",
        )


def organizer_response(row: sqlite3.Row) -> dict:
    return {
        "username": row["username"],
        "role": row["role"],
        "assignments": json.loads(row["assignments"]),
        "active": bool(row["active"]),
    }


@app.get("/")
def root():
    return RedirectResponse(url="/static/index.html")


@app.post("/auth/token")
def login(request: LoginRequest):
    with connect_database() as connection:
        row = connection.execute(
            """
            SELECT username, password_hash, role, active
            FROM staff_users WHERE username = ?
            """,
            (request.username.strip(),),
        ).fetchone()
    if (
        row is None
        or not row["active"]
        or not verify_password(request.password, row["password_hash"])
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": row["username"],
            "iat": now,
            "exp": now + TOKEN_LIFETIME_SECONDS,
        },
        auth_secret(),
        algorithm="HS256",
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": TOKEN_LIFETIME_SECONDS,
        "username": row["username"],
        "role": row["role"],
    }


@app.get("/auth/me")
def current_staff(user: StaffUser = Depends(get_current_staff)):
    return {
        "username": user.username,
        "role": user.role,
        "assignments": user.assignments,
    }


@app.get("/activities")
def get_activities():
    return activities


@app.post("/activities/{activity_name}/signup")
def signup_for_activity(activity_name: str, email: str):
    """Allow students to sign up without creating a staff account."""
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")

    activity = activities[activity_name]
    if email in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is already signed up",
        )

    activity["participants"].append(email)
    return {"message": f"Signed up {email} for {activity_name}"}


@app.delete("/activities/{activity_name}/unregister")
def unregister_from_activity(
    activity_name: str,
    email: str,
    user: StaffUser = Depends(get_current_staff),
):
    """Allow staff to unregister students from activities they manage."""
    if activity_name not in activities:
        raise HTTPException(status_code=404, detail="Activity not found")
    if user.role != "admin" and activity_name not in user.assignments:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not assigned to manage this activity",
        )

    activity = activities[activity_name]
    if email not in activity["participants"]:
        raise HTTPException(
            status_code=400,
            detail="Student is not signed up for this activity",
        )

    activity["participants"].remove(email)
    return {"message": f"Unregistered {email} from {activity_name}"}


@app.get("/staff/organizers")
def list_organizers(_: StaffUser = Depends(require_admin)):
    with connect_database() as connection:
        rows = connection.execute(
            """
            SELECT username, role, assignments, active
            FROM staff_users WHERE role = 'organizer' ORDER BY username
            """
        ).fetchall()
    return [organizer_response(row) for row in rows]


@app.post("/staff/organizers", status_code=status.HTTP_201_CREATED)
def create_organizer(
    request: OrganizerCreate,
    _: StaffUser = Depends(require_admin),
):
    username = request.username.strip()
    if len(username) < 3:
        raise HTTPException(
            status_code=400,
            detail="Username must contain at least 3 non-whitespace characters",
        )
    ensure_valid_assignments(request.assignments)
    with connect_database() as connection:
        with connection:
            try:
                connection.execute(
                    """
                    INSERT INTO staff_users
                        (username, password_hash, role, assignments, active)
                    VALUES (?, ?, 'organizer', ?, 1)
                    """,
                    (
                        username,
                        hash_password(request.password),
                        json.dumps(request.assignments),
                    ),
                )
            except sqlite3.IntegrityError:
                raise HTTPException(
                    status_code=409,
                    detail="A staff account with that username already exists",
                )
        row = connection.execute(
            """
            SELECT username, role, assignments, active
            FROM staff_users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    return organizer_response(row)


@app.patch("/staff/organizers/{username}")
def update_organizer(
    username: str,
    request: OrganizerUpdate,
    _: StaffUser = Depends(require_admin),
):
    changes = request.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=400, detail="No organizer changes supplied")
    if "assignments" in changes and changes["assignments"] is None:
        raise HTTPException(status_code=400, detail="Assignments cannot be null")
    if "assignments" in changes:
        ensure_valid_assignments(changes["assignments"])

    with connect_database() as connection:
        row = connection.execute(
            "SELECT role FROM staff_users WHERE username = ?",
            (username,),
        ).fetchone()
        if row is None or row["role"] != "organizer":
            raise HTTPException(status_code=404, detail="Organizer not found")

        assignments = changes.get("assignments")
        password = changes.get("password")
        with connection:
            if assignments is not None and password is not None:
                connection.execute(
                    """
                    UPDATE staff_users SET assignments = ?, password_hash = ?
                    WHERE username = ?
                    """,
                    (json.dumps(assignments), hash_password(password), username),
                )
            elif assignments is not None:
                connection.execute(
                    "UPDATE staff_users SET assignments = ? WHERE username = ?",
                    (json.dumps(assignments), username),
                )
            elif password is not None:
                connection.execute(
                    "UPDATE staff_users SET password_hash = ? WHERE username = ?",
                    (hash_password(password), username),
                )
        updated = connection.execute(
            """
            SELECT username, role, assignments, active
            FROM staff_users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    return organizer_response(updated)


@app.delete("/staff/organizers/{username}")
def deactivate_organizer(
    username: str,
    _: StaffUser = Depends(require_admin),
):
    with connect_database() as connection:
        with connection:
            cursor = connection.execute(
                """
                UPDATE staff_users SET active = 0
                WHERE username = ? AND role = 'organizer' AND active = 1
                """,
                (username,),
            )
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Active organizer not found")
    return {"message": f"Deactivated organizer {username}"}
