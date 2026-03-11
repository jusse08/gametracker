# 🎮 GameTracker

Трекер игрового времени с автоматическим отслеживанием сессий, интеграцией со Steam и импортом чеклистов из вики.

## 🚀 Возможности

- **Автоматический трекинг** — агент мониторит процессы и записывает время в игре
- **Steam интеграция** — синхронизация достижений и времени из Steam
- **Wiki импорт** — парсинг чеклистов миссий из Fandom/Wikia
- **Заметки** — записывайте мысли, решения загадок, идеи
- **Drag-and-drop** — перетаскивайте игры между статусами
- **Современный UI** — тёмная тема, анимации, адаптивный дизайн

## 📁 Структура проекта

```
gametracker/
├── backend/          # FastAPI сервер
│   ├── main.py       # API endpoints
│   ├── models.py     # SQLModel модели
│   ├── database.py   # Подключение к БД
│   ├── scraper.py    # Парсер вики
│   ├── steam.py      # Steam API
│   └── alembic/      # Миграции БД
├── frontend/         # React + TypeScript + Vite
│   ├── src/
│   │   ├── api.ts    # API клиент
│   │   └── pages/    # Страницы
│   └── Dockerfile
├── agent/            # Python агент для трекинга
│   └── agent.py
└── docker-compose.yml
```

## 🔧 Установка и запуск

### Вариант 1: Docker Compose (рекомендуется)

```bash
# 1. Клонируйте репозиторий
git clone <repository-url>
cd gametracker

# 2. Скопируйте .env.example
cp .env.example .env

# 3. Отредактируйте .env при необходимости

# 4. Запустите
docker-compose up -d --build

# 5. Откройте браузер
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
```

**Порты:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

> **Примечание:** Если используешь Caddy или другой reverse proxy, настрой проксирование на эти порты.

### Вариант 2: Локальная разработка

#### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Инициализация БД
alembic upgrade head

# Запуск сервера
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API Docs: http://localhost:8000/docs

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: http://localhost:5173

#### Agent

```bash
cd agent
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python agent.py
```

## ⚙️ Настройка

### Steam API

1. Получите API ключ на https://steamcommunity.com/dev/apikey
2. Откройте настройки в приложении
3. Введите API ключ и ссылку на профиль Steam

**Важно:** Профиль Steam должен быть открыт (Public) в настройках приватности.

### Агент

Агент автоматически опрашивает сервер каждые 5 минут для получения конфигурации. Для добавления игры в отслеживание:

1. Откройте настройки игры в приложении
2. Укажите `exe_name` (имя исполняемого файла)
3. Агент начнёт отслеживать этот процесс

Пример: `Cyberpunk2077.exe`, `witcher3.exe`

## 📊 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/api/games` | Список игр |
| POST | `/api/games` | Создать игру |
| GET | `/api/games/{id}` | Информация об игре |
| PUT | `/api/games/{id}` | Обновить игру |
| DELETE | `/api/games/{id}` | Удалить игру |
| POST | `/api/games/{id}/import/wiki` | Импорт из вики |
| POST | `/api/games/{id}/sync/steam` | Синхронизация Steam |
| GET | `/api/games/{id}/checklist` | Чеклист игры |
| GET | `/api/games/{id}/notes` | Заметки игры |
| GET | `/api/games/{id}/sessions` | История сессий |
| GET | `/api/settings` | Настройки |
| PUT | `/api/settings` | Обновить настройки |

Полная документация: http://localhost:8000/docs

## 🗄️ Миграции базы данных

```bash
cd backend

# Создать новую миграцию
alembic revision --autogenerate -m "Description"

# Применить миграции
alembic upgrade head

# Откатить миграцию
alembic downgrade -1
```

## 🔐 Безопасность

- Не публикуйте `.env` файлы с реальными ключами
- Steam API ключ хранится в базе данных (не зашифрован)
- Для production настройте HTTPS

## 🛠️ Технологии

**Backend:**
- FastAPI
- SQLModel (SQLAlchemy + Pydantic)
- SQLite
- Alembic
- BeautifulSoup4

**Frontend:**
- TypeScript
- Vite
- Tailwind CSS v4
- Vanilla JS (без фреймворков)

**Agent:**
- Python
- psutil
- requests

## 📝 Лицензия

MIT
