# Hackaton

MVP-сервис для редактирования договоров с возможностью загрузить файл, внести правки в браузере и сразу скачать исправленную версию.

## Структура

- `backend/` - FastAPI-приложение с луковой архитектурой.
- `frontend/` - React SPA с модульной структурой.
- `.github/workflows/ci.yml` - CI-пайплайн для тестов, сборки фронтенда и проверки Docker-образов.
- `docker-compose.yml` - локальный запуск всего проекта через Docker.

## Что умеет MVP

- загрузка договора из `.txt` или `.docx`;
- редактирование текста договора в браузере;
- постраничное отображение `DOCX`;
- сохранение форматирования `DOCX`, включая стили заголовков, размеры шрифта и выравнивание;
- скачивание исправленного договора в формате `.txt` или `.docx`.

## Локальный запуск

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn src.main:app --reload
```

Backend будет доступен на `http://127.0.0.1:8000`, Swagger UI на `http://127.0.0.1:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend будет доступен на `http://127.0.0.1:5173`.

## Тесты

### Backend

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Сейчас есть smoke-тесты для API:

- загрузка, редактирование и скачивание `.txt`;
- загрузка `.docx` и проверка метаданных форматирования заголовка.

### Frontend

```bash
cd frontend
npm install
npm run test -- --run
```

Сейчас есть UI-тест для DOCX-редактора, который проверяет одностраничный режим редактирования без блока оригинала.

## Makefile

На уровне репозитория есть единая точка входа для основных проверок:

```bash
make lint
make test
make build
make docker-build
make ci
```

Полезные таргеты:

- `make lint-backend` - `ruff` для `backend/src` и `backend/tests`;
- `make lint-frontend` - `eslint` для `frontend/src`;
- `make test-backend` - `pytest`;
- `make test-frontend` - `vitest --run`;
- `make build-frontend` - production build фронтенда;
- `make docker-build` - сборка образов через `docker compose build`;
- `make ci` - полный локальный прогон линтеров, тестов, сборки фронтенда и Docker-образов.

## Docker

### Запуск

```bash
docker compose up -d --build
```

После запуска:

- frontend будет доступен на `http://127.0.0.1:5173`;
- backend будет доступен на `http://127.0.0.1:8000`;
- запросы `/api` с frontend контейнера проксируются в backend через `nginx`.

### Остановка

```bash
docker compose down
```

## CI

GitHub Actions в `.github/workflows/ci.yml` запускает три независимые проверки:

- `backend` - установка Python-зависимостей и запуск `pytest`;
- `frontend` - `npm ci`, `vitest` и production build;
- `docker` - сборка Docker-образов через `docker compose build`.

Пайплайн стартует на `push` в `main` и `master`, а также на каждый `pull_request`.

## Следующие шаги

- сохранить договоры в постоянное хранилище вместо памяти процесса;
- улучшить пагинацию и поддержку сложной верстки `DOCX`;
- добавить автоматическое выявление некорректных терминов и предложения по замене.
