# Online Cinema (FastAPI)

An asynchronous backend for a movie catalog and purchase platform. Users can
manage their accounts and profiles, discover movies, leave ratings and comments,
and buy movies through Stripe Checkout.

The application is organized into routers, services and repositories. It is a
backend project, not a streaming service or a complete frontend; HTML pages are
included only for activation, password recovery and payment results.

## Tech stack

- **FastAPI + Pydantic 2** — API endpoints, request validation and response schemas.
- **SQLAlchemy 2 + Alembic** — asynchronous database access and migrations.
- **PostgreSQL 17 / SQLite** — container environments / local development.
- **Celery + Redis 7.4** — email delivery and scheduled cleanup.
- **MinIO / S3 + boto3** — private avatar storage with signed URLs.
- **Stripe** — hosted checkout, webhook verification and full refunds.
- **Poetry + Docker Compose** — dependencies and application infrastructure.
- **pytest + pytest-cov, Flake8, mypy** — tests, coverage, style and type checks.
- **GitHub Actions** — continuous integration and deployment.

## Local setup

### 1. Prepare the environment

Install Git and Docker with Compose v2, clone the repository, and open its root
directory. On Windows, start Docker Desktop.

Copy the settings template:

```bash
cp .env.example .env
```

In PowerShell, use `Copy-Item .env.example .env` instead. Do not overwrite an
already configured file.

**Every value in `.env.example` is a placeholder.** Replace them before startup.
The following development configuration uses the included MailHog server.

- JWT secrets must be different and at least 32 characters long. With Python
  installed, run `python -c "import secrets; print(secrets.token_urlsafe(48))"`
  twice to generate them.
- Choose your own MinIO credentials: Compose uses `S3_ACCESS_KEY` and
  `S3_SECRET_KEY` as its root username/password. Use a strong password of at
  least 8 characters.
- MailHog captures emails locally, without real delivery or SMTP credentials.
  To use Mailtrap or another provider, replace the SMTP settings with its
  credentials. Enable TLS or STARTTLS as required, but not both.
- Stripe keys can remain empty until payment testing. Use test credentials and
  keep `STRIPE_LIVE_MODE=false` during development.
- Compose overrides the database connection, Redis URL and internal S3 address.
  **Both Docker dev and prod use PostgreSQL**, even with `DATABASE_TYPE=sqlite`
  in this file. Local SQLite is a separate database.

### 2. Start the services

```bash
docker compose -f docker-compose-dev.yml config --quiet
docker compose -f docker-compose-dev.yml up -d --build
docker compose -f docker-compose-dev.yml ps -a
```

The stack runs the API, PostgreSQL, Redis, MinIO, MailHog, Celery worker and Beat.
A one-shot `migrate` service applies Alembic migrations before the API starts.
It also inserts the `USER`, `MODERATOR` and `ADMIN` groups.
An exited migration container with code `0` is normal.

| Service | Address |
| --- | --- |
| Swagger / ReDoc | http://localhost:8000/docs / http://localhost:8000/redoc |
| OpenAPI schema | http://localhost:8000/openapi.json |
| MailHog inbox | http://localhost:8025 |
| MinIO console | http://localhost:9001 |
| MinIO S3 endpoint | http://localhost:9000 |

Open the MinIO console with your S3 credentials and create a **private** bucket
matching `S3_BUCKET_NAME`. The application does not create it automatically.
Avatars use temporary signed links; public bucket access is unnecessary.

Optional pgAdmin:

```bash
docker compose -f docker-compose-dev.yml --profile tools up -d pgadmin
```

Open http://localhost:3333 and connect to `postgres:5432` using your PostgreSQL
credentials. PostgreSQL and Redis are not exposed to the host by these files.

### 3. Register and open Swagger

Documentation requires HTTP Basic authentication with an **active account**.
On a fresh database, register through Postman first:

```http
POST http://localhost:8000/api/v1/accounts/register/
Content-Type: application/json
```

```json
{
  "email": "demo@example.com",
  "password": "CinemaDemo123!"
}
```

These are demo credentials, not production credentials. With MailHog, no real
inbox is needed.

1. Read the activation email at http://localhost:8025 and click its button.
2. Open Swagger and enter your email/password in the browser's Basic Auth prompt.
3. Call `POST /api/v1/accounts/login/` with the same JSON.
4. Copy `access_token` into Swagger's **Authorize → HTTPBearer** field.

Documentation login and API authorization are separate. Protected API calls use
`Authorization: Bearer <access_token>`; in Swagger's bearer field, paste only
the token.

### 4. Create the first administrator

Registration assigns the `USER` role. After activating your account, open a
development database shell:

```bash
docker compose -f docker-compose-dev.yml exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Replace the email below with your registered address:

```sql
UPDATE users
SET group_id = (SELECT id FROM user_groups WHERE name = 'ADMIN')
WHERE email = 'demo@example.com';
```

Expect `UPDATE 1`; `UPDATE 0` means the email did not match. Exit with `\q`.
Later, administrators can change groups through the API. Database role names
are uppercase; API values are `user`, `moderator` and `admin`.

### Updating and stopping

```bash
docker compose -f docker-compose-dev.yml up -d --build
docker compose -f docker-compose-dev.yml logs --tail=100 app worker migrate
docker compose -f docker-compose-dev.yml down
```

Dev mounts `src` and reloads the API. Restart `worker` and `beat` when changing
task code. Recreate containers after editing `.env`; a restart alone does not
reload environment variables.

`down` keeps named volumes. Avoid `down -v` unless you intend to delete the
database and stored files. For an empty environment without deleting existing
data, stop the current stack and use a new project name:

```bash
docker compose -p online-cinema-clean -f docker-compose-dev.yml up -d --build
```

Use the same `-p` value for subsequent commands. Both stacks use the same ports,
so they cannot run simultaneously unchanged.

### Running locally with SQLite

With Python 3.10 and Poetry 2:

```bash
poetry env use 3.10
poetry install --with dev --no-root
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload
```

Set `DATABASE_TYPE=sqlite` and `PATH_TO_DB=db.sqlite3` before these commands.
Local processes need host-accessible SMTP, Redis and S3 addresses, not Docker
service names. The supplied Compose files do not publish Redis or MailHog's SMTP
port to the host. For the complete stack on Windows, Docker dev is the simpler
option.

When running outside Docker, start a worker and Beat separately in Linux/WSL
against your configured Redis broker:

```bash
poetry run celery -A src.core.celery_app:celery_app worker --loglevel=info
poetry run celery -A src.core.celery_app:celery_app beat --loglevel=info
```

## Database migrations

Migrations are stored in `src/database/alembic/versions`.
Docker startup applies them automatically. To create and apply a migration in
the running dev environment:

```bash
docker compose -f docker-compose-dev.yml exec app alembic revision --autogenerate -m "describe the change"
docker compose -f docker-compose-dev.yml exec app alembic upgrade head
```

Review generated migrations before applying them. The dev source mount keeps
new migration files in the local project.

For local SQLite, Alembic uses `sqlalchemy.url` in `alembic.ini`, pointing to
the root `db.sqlite3`. If you change `PATH_TO_DB`, update this URL too.
For PostgreSQL, the migration URL is built from application settings.
SQLite and Docker PostgreSQL have independent data and migration histories.

## Architecture

```text
routers → services → repositories → database
```

- **Routers** parse requests, apply access dependencies and call services.
- **Services** implement business rules, coordinate repositories, manage
  transactions and call external integrations.
- **Repositories** encapsulate database queries and share the session supplied
  through dependency injection.
- **Models and schemas** describe persistent data and API input/output separately.
- **Adapters and tasks** handle Stripe, avatar storage and queued email delivery.

```text
src/
├── api/
│   ├── dependencies.py       # Dependency wiring
│   └── v1/routers/           # Versioned endpoints
├── core/                     # Settings and Celery configuration
├── database/
│   ├── alembic/              # Migrations
│   ├── models/               # SQLAlchemy models
│   ├── validators/           # Shared validation
│   ├── session_sqlite.py
│   └── session_postgresql.py
├── repositories/             # Queries and shared repository helpers
├── services/                 # Business logic
├── schemas/                  # Pydantic request/response schemas
├── security/                 # Passwords, JWTs and access checks
├── notifications/            # Email sender, queue and HTML templates
├── storages/                 # S3-compatible storage adapter
├── payments/                 # Stripe adapter and checkout helpers
├── tasks/                    # Celery jobs
├── tests/
│   ├── unit/
│   └── integration/
└── main.py
```

## API endpoints

All endpoints below use the `/api/v1` prefix. Protected operations require an
access token in the `Authorization: Bearer <access_token>` header, except token
refresh/logout and Stripe webhooks, which use their own credentials. Request
fields, access rules and operation details are described above and in Swagger.

### Accounts

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/accounts/login/` | Log in to an activated account |
| POST | `/accounts/token/refresh/` | Refresh the access token |
| POST | `/accounts/logout/` | Log out of the current session |
| PATCH | `/accounts/password/change/` | Change the current user's password |
| POST | `/accounts/password/forgot/` | Request a password reset email |
| POST | `/accounts/password/reset/` | Set a new password using a reset token |
| POST | `/accounts/activate/` | Activate a user account |
| GET | `/accounts/activate/` | Activate an account using the email link |
| POST | `/accounts/register/` | Register a user |
| POST | `/accounts/activation/resend/` | Resend an activation email |
| PATCH | `/accounts/{user_id}/group/` | Change a user's group as an administrator |
| POST | `/accounts/{user_id}/activate/` | Activate a user account as an administrator |

### Profiles

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/profiles/{user_id}/` | Get a user profile |
| PATCH | `/profiles/{user_id}/` | Update your profile |

### Movies

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/movies/` | Browse the movie catalog |
| GET | `/movies/{movie_id}/` | Get movie details |
| POST | `/movies/` | Create a movie |
| PUT | `/movies/{movie_id}/` | Replace a movie |
| DELETE | `/movies/{movie_id}/` | Delete a movie |

### Genres

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/genres/` | List genres with movie counts |
| GET | `/genres/{genre_id}/` | Get a genre |
| POST | `/genres/` | Create a genre |
| PATCH | `/genres/{genre_id}/` | Rename a genre |
| DELETE | `/genres/{genre_id}/` | Delete a genre |

### Actors

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/stars/` | List actors |
| GET | `/stars/{star_id}/` | Get a star |
| POST | `/stars/` | Create a star |
| PATCH | `/stars/{star_id}/` | Rename a star |
| DELETE | `/stars/{star_id}/` | Delete a star |

### Directors

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/directors/` | List directors |
| POST | `/directors/` | Create a director |
| PATCH | `/directors/{director_id}/` | Rename a director |
| DELETE | `/directors/{director_id}/` | Delete a director |

### Certifications

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/certifications/` | List certifications |
| POST | `/certifications/` | Create a certification |
| PATCH | `/certifications/{certification_id}/` | Rename a certification |
| DELETE | `/certifications/{certification_id}/` | Delete a certification |

### Favorites

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/favorites/` | List your favorite movies |
| POST | `/favorites/` | Add a movie to your favorites |
| DELETE | `/favorites/{movie_id}/` | Remove a favorite movie |

### Likes and dislikes

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/movies/{movie_id}/reaction/` | Get your movie reaction |
| PUT | `/movies/{movie_id}/reaction/` | Like or dislike a movie |
| DELETE | `/movies/{movie_id}/reaction/` | Remove your movie reaction |

### Ratings

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/movies/{movie_id}/rating/` | Get your movie rating |
| PUT | `/movies/{movie_id}/rating/` | Rate a movie from 1 to 10 |
| DELETE | `/movies/{movie_id}/rating/` | Remove your movie rating |

### Comments

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/movies/{movie_id}/comments/` | List movie comments and replies |
| POST | `/movies/{movie_id}/comments/` | Write a comment or reply |
| PUT | `/comments/{comment_id}/like/` | Like a comment |
| DELETE | `/comments/{comment_id}/like/` | Remove your comment like |

### Shopping cart

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/cart/` | View your cart |
| POST | `/cart/items/` | Add a movie to your cart |
| DELETE | `/cart/items/{movie_id}/` | Remove a movie from your cart |
| DELETE | `/cart/` | Clear your cart |
| GET | `/cart/users/{user_id}/` | View a user's cart as an administrator |
| POST | `/cart/checkout/` | Create an order from your cart |

### Orders

| Method | Endpoint | Description |
| --- | --- | --- |
| GET | `/orders/` | List your orders |
| GET | `/orders/admin/` | List all orders as an administrator |
| GET | `/orders/{order_id}/` | View your order |
| PATCH | `/orders/{order_id}/cancel/` | Cancel your pending order |

### Payments

| Method | Endpoint | Description |
| --- | --- | --- |
| POST | `/payments/checkout/` | Pay for your order with Stripe |
| POST | `/payments/checkout/{order_id}/cancel/` | Cancel an unpaid checkout |
| GET | `/payments/` | View your payment history |
| GET | `/payments/admin/` | Filter all payments as an administrator |
| GET | `/payments/purchased/` | List your purchased movies |
| POST | `/payments/refund/` | Request a full refund |
| POST | `/payments/webhook/` | Receive signed Stripe events |
| GET | `/payments/return/` | Show checkout result |
| GET | `/payments/{payment_id}/` | View your payment |

## Running tests

```bash
poetry install --with dev --no-root
poetry run flake8 src
poetry run mypy src
poetry run pytest src/tests -q
```

Unit and integration tests cover validators, models, schemas, services, access
rules and API workflows. External integrations are mocked; tests do not send
real email or charge cards. SQLite-based tests do not replace PostgreSQL and
external-service smoke tests.

For an isolated container run:

```bash
docker compose -f docker-compose-tests.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f docker-compose-tests.yml down
```

The test container has no network, local `.env`, published ports or application
data volumes. Some tests currently emit Pydantic field-metadata warnings.

### Coverage

```bash
poetry run pytest src/tests -q --cov=src --cov-report=term-missing --cov-report=html --cov-report=xml
```

Open `htmlcov/index.html` for a line-by-line report. Configuration is in
`pyproject.toml`; test files are excluded from measured application coverage.
Regenerate the report for the current commit rather than relying on a fixed
percentage. CI publishes coverage but currently does not enforce a minimum
coverage threshold.
