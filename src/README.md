# Mergington High School Activities API

A super simple FastAPI application that allows students to view and sign up for extracurricular activities.

## Features

- View all available extracurricular activities
- Sign up for activities without creating an account
- Staff sign-in with administrator and organizer roles
- Administrator management of organizer accounts and activity assignments
- Organizer access limited to assigned activities
- Persistent staff accounts with hashed passwords

## Getting Started

1. Install the dependencies:

   ```
   pip install -r requirements.txt
   ```

2. Configure the required staff credentials and signing key. Generate a unique
   signing key (for example, with `openssl rand -hex 32`) and choose a strong
   initial administrator password of at least 12 characters:

   ```
   export AUTH_SECRET_KEY="<unique secret of at least 32 characters>"
   export INITIAL_ADMIN_USERNAME="school-admin"
   export INITIAL_ADMIN_PASSWORD="<strong password of at least 12 characters>"
   ```

   `AUTH_SECRET_KEY` must remain stable between restarts so issued tokens remain
   valid. The initial administrator is created on first startup; changing the
   environment password later does not overwrite an existing account. Staff
   accounts are stored in `src/staff.sqlite3` by default. Set
   `STAFF_DATABASE_PATH` to use another location.

3. Start the application from the `src` directory:

   ```
   cd src
   uvicorn app:app --reload
   ```

4. Open your browser and go to:
   - API documentation: http://localhost:8000/docs
   - Alternative documentation: http://localhost:8000/redoc

## API Endpoints

| Method | Endpoint | Access | Description |
| ------ | -------- | ------ | ----------- |
| GET | `/activities` | Public | Get all activities and participants |
| POST | `/activities/{activity_name}/signup?email=student@mergington.edu` | Public | Sign up a student |
| POST | `/auth/token` | Public | Sign in and receive a bearer token |
| GET | `/auth/me` | Staff | Get the signed-in staff member and role |
| DELETE | `/activities/{activity_name}/unregister?email=student@mergington.edu` | Admin or assigned organizer | Unregister a student |
| GET, POST | `/staff/organizers` | Admin | List or create organizer accounts |
| PATCH, DELETE | `/staff/organizers/{username}` | Admin | Update assignments/password or deactivate an organizer |

Organizer passwords must be at least 12 characters. The login endpoint accepts
JSON containing `username` and `password`; send its returned `access_token` in
the `Authorization: Bearer <token>` header for staff-only operations.

## Data Model

The application uses a simple data model with meaningful identifiers:

1. **Activities** - Uses activity name as identifier:

   - Description
   - Schedule
   - Maximum number of participants allowed
   - List of student emails who are signed up

2. **Students** - Uses email as identifier:
   - Name
   - Grade level

Activity and participant data is currently stored in memory and resets when the
server restarts. Staff accounts and password hashes are stored in SQLite.
