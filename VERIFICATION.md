# Проверка проекта

Проверки выполнялись 10–20 октября 2026. Исходная рабочая копия была чистой.

31 тестов прошли. JWT, CRUD, Decimal/ID, атомарное списание и rollback; eager Celery/fakeredis; Ruff/strict mypy. Исправлен sync URL PostgreSQL для установленного psycopg2.

Почта — имитация. generate_invoice_pdf исторически назван так, но создаёт текстовый .txt счёт; настоящего PDF нет. Нагрузочные цифры README не измерялись.

## Повторный запуск

Команды из папки проекта после создания и активации Python venv. Для API задайте DATABASE_URL отдельной локальной БД и тестовый SECRET_KEY по примеру конфигурации; не используйте рабочие подключения.

```bash
python -m venv .venv
# Активируйте .venv согласно ОС.
python -m pip install . -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Тесты в отдельном тестовом окружении:

```bash
python -m pytest -o addopts= -q
```

Docker-проверки использовали отдельную сеть, PostgreSQL *_test и Redis; реальные данные, платежи и внешние сообщения не затрагивались. Результат локального запуска не означает production-ready.

20 октября Docker HTTP + настоящий Celery worker/Redis/PostgreSQL прошли: статус success, файл счёта виден API через общий volume.
