from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from pypdf import PdfReader
import pypdfium2 as pdfium

OUT_PDF = Path('output/pdf/gametracker_app_summary.pdf')
OUT_PNG = Path('tmp/pdfs/gametracker_app_summary_page1.png')


def build_pdf() -> None:
    doc = SimpleDocTemplate(
        str(OUT_PDF),
        pagesize=A4,
        leftMargin=14 * mm,
        rightMargin=14 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title='GameTracker App Summary',
        author='Codex',
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        'Title',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=21,
        spaceAfter=5,
        textColor=colors.HexColor('#0f172a'),
    )
    subtitle = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#475569'),
        spaceAfter=9,
    )
    h2 = ParagraphStyle(
        'H2',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=13,
        textColor=colors.HexColor('#0f172a'),
        spaceBefore=3,
        spaceAfter=3,
    )
    body = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#111827'),
        spaceAfter=3,
    )
    bullet = ParagraphStyle('Bullet', parent=body, leftIndent=8, firstLineIndent=-8, spaceAfter=2)

    story = []
    story.append(Paragraph('GameTracker - App Summary', title))
    story.append(Paragraph('Evidence source: repository files under frontend/, backend/, agent/, and docker-compose.yml.example', subtitle))

    story.append(Paragraph('What It Is', h2))
    story.append(
        Paragraph(
            'GameTracker is a full-stack game library tracker with a web UI (Vite/TypeScript), a FastAPI backend, and an optional desktop agent for automated play session tracking and game launching. '
            'It combines manual game management with Steam sync, achievements, checklists, notes, and random game facts.',
            body,
        )
    )

    story.append(Paragraph("Who It's For", h2))
    story.append(
        Paragraph(
            'Primary persona: Not explicitly documented in repo. Inferred from API/UI and integrations as an individual PC gamer who wants to organize a personal library, track progress/playtime, and optionally automate tracking via a paired Windows agent.',
            body,
        )
    )

    story.append(Paragraph('What It Does', h2))
    feature_items = [
        'User auth + profile/settings management, including admin user management endpoints.',
        'Game library CRUD with statuses (playing/backlog/completed/deferred), ratings, genres, covers, and sorting/filtering UI.',
        'Progress tracking via checklist items, custom checklist categories, notes, and session history.',
        'Steam integrations for game search, app metadata/images, manual playtime sync, and achievement sync.',
        'Random game facts endpoint with rebuild pipeline from Fandom sources into gametracker_data/game_facts.json.',
        'Agent device lifecycle: pair code, device registration/revocation, token refresh, and agent binary download endpoint.',
        'Real-time agent channel via WebSocket + command polling/ack flow for launch and active session ping updates.',
    ]
    for item in feature_items:
        story.append(Paragraph(f'- {item}', bullet))

    story.append(Spacer(1, 3))
    story.append(Paragraph('How It Works (Architecture)', h2))
    arch_lines = [
        '<b>Frontend:</b> Single-page app in <b>frontend/src/app/main.ts</b> and feature modules calls REST APIs in <b>frontend/src/shared/api/index.ts</b>.',
        '<b>Backend:</b> FastAPI app in <b>backend/app/main.py</b> mounts routers for auth/users, games, settings, facts, and agent.',
        '<b>Data:</b> SQLModel entities in <b>backend/app/domain/models.py</b>; Alembic migrations + script <b>backend/scripts/manage_db.py</b>; default SQLite at <b>./data/database.db</b> (via compose volume <b>./gametracker_data</b>).',
        '<b>External services:</b> Steam Web APIs + Steam Store API (<b>backend/app/integrations/steam.py</b>) and Fandom scraping/facts JSON pipeline (<b>backend/app/integrations/fandom_facts.py</b>).',
        '<b>Agent flow:</b> Desktop agent (<b>agent/agent.py</b>) pairs with backend, opens websocket at <b>/api/agent/ws</b>, receives config/commands, sends ping/ack updates, and can launch configured executables.',
        '<b>Data flow:</b> User action in web UI -> FastAPI router/service logic -> DB + optional Steam/Fandom calls -> JSON response to UI; for runtime tracking, backend <-> agent channels sync session state.',
    ]
    for line in arch_lines:
        story.append(Paragraph(line, body))

    story.append(Paragraph('How To Run (Minimal)', h2))
    run_lines = [
        '1) Copy env template and set required secrets: <b>cp .env.example .env</b>, then set <b>SECRET_KEY</b> and <b>SUPERADMIN_PASSWORD</b>.',
        '2) Start stack with Docker Compose file: <b>docker compose -f docker-compose.yml.example up --build</b>.',
        '3) Open UI at <b>http://localhost:3000</b>; backend is on <b>http://localhost:8000</b> with health endpoint <b>/health</b>.',
        '4) Optional: pair the Windows agent from web settings using pair code flow and run the agent binary endpoint/download.',
        '5) Local non-Docker dev startup commands: <b>Not found in repo</b>.',
    ]
    for line in run_lines:
        story.append(Paragraph(line, body))

    story.append(Spacer(1, 3))
    story.append(Paragraph('Generated: 2026-03-24', subtitle))

    doc.build(story)


def assert_single_page() -> None:
    reader = PdfReader(str(OUT_PDF))
    pages = len(reader.pages)
    if pages != 1:
        raise RuntimeError(f'Expected 1 page, got {pages}')


def render_first_page_png() -> None:
    pdf = pdfium.PdfDocument(str(OUT_PDF))
    page = pdf[0]
    bitmap = page.render(scale=2.0)
    pil_image = bitmap.to_pil()
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    pil_image.save(OUT_PNG)


if __name__ == '__main__':
    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    build_pdf()
    assert_single_page()
    render_first_page_png()
    print(OUT_PDF)
    print(OUT_PNG)
