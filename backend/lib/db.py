"""SQLite (데모 단계). 임상 정보와 식별정보를 다른 테이블에 둔다."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from ..core.schemas import Feedback, InboxItem, Patient, Protocol

ROOT = Path(__file__).resolve().parents[2]
DB_PATH = ROOT / "data" / "rehabtalk.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS patients      (id TEXT PRIMARY KEY, token TEXT UNIQUE, body TEXT);
CREATE TABLE IF NOT EXISTS patient_pii   (patient_id TEXT PRIMARY KEY, name TEXT, phone TEXT);
CREATE TABLE IF NOT EXISTS protocols     (id TEXT PRIMARY KEY, body TEXT);
CREATE TABLE IF NOT EXISTS plans         (patient_id TEXT, date TEXT, body TEXT, sent_at TEXT,
                                          PRIMARY KEY (patient_id, date));
CREATE TABLE IF NOT EXISTS feedback      (patient_id TEXT, date TEXT, body TEXT,
                                          PRIMARY KEY (patient_id, date));
CREATE TABLE IF NOT EXISTS inbox         (id TEXT PRIMARY KEY, patient_id TEXT, body TEXT);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init(force: bool = False) -> None:
    if force and DB_PATH.exists():
        DB_PATH.unlink()
    fresh = not DB_PATH.exists()
    with connect() as conn:
        conn.executescript(SCHEMA)
        if fresh or not conn.execute("SELECT 1 FROM patients LIMIT 1").fetchone():
            _seed(conn)


# ─────────────────────────────────────────────────────────────

def _seed(conn: sqlite3.Connection) -> None:
    seed = json.loads((ROOT / "data" / "seed.json").read_text(encoding="utf-8"))
    for p in seed["patients"]:
        conn.execute("INSERT OR REPLACE INTO patients VALUES (?,?,?)",
                     (p["id"], p["token"], json.dumps(p, ensure_ascii=False)))
    for pii in seed["patient_pii"]:
        conn.execute("INSERT OR REPLACE INTO patient_pii VALUES (?,?,?)",
                     (pii["patient_id"], pii["name"], pii["phone"]))

    proto = json.loads((ROOT / "data" / "standard_protocol.json").read_text(encoding="utf-8"))
    proto = {k: v for k, v in proto.items() if not k.startswith("_")}
    conn.execute("INSERT OR REPLACE INTO protocols VALUES (?,?)",
                 (proto["id"], json.dumps(proto, ensure_ascii=False)))

    # 데모용 피드백 이력: p1은 3주 전 어깨 높이까지 올라온 뒤 2주째 그대로다
    today = date.today()
    for i in range(20, -1, -2):
        day = today - timedelta(days=i)
        fb = Feedback(
            patient_id="p1", date=day, pain=4 if i > 6 else 5,
            completed=["진자 운동", "수동 전방거상 (테이블 슬라이드)"],
            rom_self="어깨" if i <= 16 else "허리",
            note="어깨 올릴 때 조금 뻐근해요" if i == 0 else None,
        )
        save_feedback(fb, conn)

    save_inbox(InboxItem(
        id="ib1", patient_id="p1", origin="정체 감지",
        summary="2주째 가동범위 정체 (어깨 높이에서 멈춤)",
        related_limits=["1단계: 수동 외회전 30° 이내", "능동 거상 금지"],
        recent="통증 4→5 (2주), 수행 8/8회",
    ), conn)
    save_inbox(InboxItem(
        id=f"rf-p3-{today.isoformat()}", patient_id="p3", origin="적신호",
        summary="환자 메모: 어깨가 빨갛게 붓고 열이 나요",
        related_limits=["1단계: 보조기 상시 착용"],
        recent="통증 8, 부종 있음",
    ), conn)


# ── 환자 ──────────────────────────────────────────────────────

def list_patients() -> list[dict]:
    """치료사 화면용. 이름은 여기서만 붙인다 — AI에는 절대 넘기지 않는다."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT p.body, i.name FROM patients p LEFT JOIN patient_pii i ON i.patient_id = p.id"
        ).fetchall()
    return [{**json.loads(r["body"]), "name": r["name"]} for r in rows]


def get_patient(patient_id: str) -> Patient | None:
    with connect() as conn:
        row = conn.execute("SELECT body FROM patients WHERE id=?", (patient_id,)).fetchone()
    return Patient(**json.loads(row["body"])) if row else None


def get_patient_by_token(token: str) -> Patient | None:
    with connect() as conn:
        row = conn.execute("SELECT body FROM patients WHERE token=?", (token,)).fetchone()
    return Patient(**json.loads(row["body"])) if row else None


def patient_name(patient_id: str) -> str | None:
    with connect() as conn:
        row = conn.execute("SELECT name FROM patient_pii WHERE patient_id=?", (patient_id,)).fetchone()
    return row["name"] if row else None


def save_patient(patient: Patient) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO patients VALUES (?,?,?)",
                     (patient.id, patient.token, patient.model_dump_json()))


# ── 프로토콜 ──────────────────────────────────────────────────

def get_protocol(protocol_id: str) -> Protocol | None:
    with connect() as conn:
        row = conn.execute("SELECT body FROM protocols WHERE id=?", (protocol_id,)).fetchone()
    return Protocol(**json.loads(row["body"])) if row else None


def save_protocol(protocol: Protocol) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO protocols VALUES (?,?)",
                     (protocol.id, protocol.model_dump_json()))


# ── 처방 ──────────────────────────────────────────────────────

def save_plan(patient_id: str, day: date, exercises: list[dict], sent: bool = False) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO plans VALUES (?,?,?,?)",
            (patient_id, day.isoformat(), json.dumps(exercises, ensure_ascii=False),
             datetime.now().isoformat() if sent else None),
        )


def get_plan(patient_id: str, day: date | None = None) -> list[dict]:
    day = day or date.today()
    with connect() as conn:
        row = conn.execute("SELECT body FROM plans WHERE patient_id=? AND date=?",
                           (patient_id, day.isoformat())).fetchone()
        if row is None:      # 오늘 것이 없으면 가장 최근 처방을 보여준다
            row = conn.execute(
                "SELECT body FROM plans WHERE patient_id=? ORDER BY date DESC LIMIT 1", (patient_id,)
            ).fetchone()
    return json.loads(row["body"]) if row else []


# ── 피드백 ────────────────────────────────────────────────────

def save_feedback(fb: Feedback, conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    conn.execute("INSERT OR REPLACE INTO feedback VALUES (?,?,?)",
                 (fb.patient_id, fb.date.isoformat(), fb.model_dump_json()))
    if own:
        conn.commit()
        conn.close()


def get_feedback(patient_id: str) -> list[Feedback]:
    with connect() as conn:
        rows = conn.execute("SELECT body FROM feedback WHERE patient_id=? ORDER BY date",
                            (patient_id,)).fetchall()
    return [Feedback(**json.loads(r["body"])) for r in rows]


# ── 인박스 ────────────────────────────────────────────────────

def save_inbox(item: InboxItem, conn: sqlite3.Connection | None = None) -> None:
    own = conn is None
    conn = conn or connect()
    conn.execute("INSERT OR REPLACE INTO inbox VALUES (?,?,?)",
                 (item.id, item.patient_id, item.model_dump_json()))
    if own:
        conn.commit()
        conn.close()


def list_inbox() -> list[InboxItem]:
    with connect() as conn:
        rows = conn.execute("SELECT body FROM inbox").fetchall()
    return [InboxItem(**json.loads(r["body"])) for r in rows]


def get_inbox(item_id: str) -> InboxItem | None:
    with connect() as conn:
        row = conn.execute("SELECT body FROM inbox WHERE id=?", (item_id,)).fetchone()
    return InboxItem(**json.loads(row["body"])) if row else None
