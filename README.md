# SSMART Backend

FastAPI + PostgreSQL + SQLAlchemy 2.0 (async).

## Tuzilma

```
ssmartBack/
├── app/
│   ├── main.py              # Entry point
│   ├── routers/user.py      # API endpoints
│   ├── models/user.py       # DB models (SQLAlchemy)
│   ├── schemas/user.py      # Request/response (Pydantic)
│   ├── services/user_service.py  # Business logic
│   ├── db/database.py       # Engine + session
│   └── core/
│       ├── config.py        # Settings (.env)
│       └── security.py      # Hash + JWT
├── requirements.txt
└── .env
```

## O'rnatish

```bash
cd ssmartBack
python -m venv venv
venv\Scripts\activate         # Windows
# yoki: source venv/bin/activate  (Linux/Mac)
pip install -r requirements.txt
```

## PostgreSQL tayyorlash

```sql
CREATE DATABASE ssmartshop;
```

`.env` ichida `DATABASE_URL` ni o'z parolingizga moslang:

```
DATABASE_URL=postgresql+asyncpg://postgres:SIZNINGPAROLINGIZ@localhost:5432/ssmartshop
```

## Ishga tushirish

```bash
uvicorn app.main:app --reload --port 8000
```

API: http://localhost:8000
Docs: http://localhost:8000/docs

## Endpointlar

- `POST /api/users/register` — ro'yxatdan o'tish
- `POST /api/users/login` — kirish (JWT qaytaradi)
- `GET /api/users/me` — joriy user (Bearer token kerak)
