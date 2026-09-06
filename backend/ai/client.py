"""LLM 호출은 이 파일을 거친다. 다른 곳에서 provider SDK를 직접 부르지 않는다.

세 가지 모드로 돈다 — 키에 따라 자동으로 정해진다.

    upstage    UPSTAGE_API_KEY  → Solar (채팅) + Document Parse (사진) + 임베딩
    anthropic  ANTHROPIC_API_KEY → Claude (채팅 + vision)
    mock       키 없음          → 각 모듈의 목업. 데모 6장면은 그대로 돈다

둘 다 있으면 UPSTAGE_API_KEY를 먼저 쓴다(AI_PROVIDER 로 강제 가능).
"""

from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

PROMPT_DIR = Path(__file__).parent / "prompts"

UPSTAGE_BASE = os.getenv("UPSTAGE_BASE_URL", "https://api.upstage.ai/v1")
UPSTAGE_MODEL = os.getenv("UPSTAGE_MODEL", "solar-pro4")
UPSTAGE_PARSE_MODEL = "document-parse"
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

TIMEOUT = 180
RETRIES = 2


# ─────────────────────────────────────────────────────────────
# 모드 판정
# ─────────────────────────────────────────────────────────────

def provider() -> str:
    forced = os.getenv("AI_PROVIDER")
    if forced:
        return forced
    if os.getenv("UPSTAGE_API_KEY"):
        return "upstage"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "mock"


def model() -> str:
    return {"upstage": UPSTAGE_MODEL, "anthropic": ANTHROPIC_MODEL}.get(provider(), "-")


def is_live() -> bool:
    return provider() != "mock"


def can_read_documents() -> bool:
    """사진에서 글자를 읽을 수 있는가 (Upstage Document Parse / Claude vision)."""
    return is_live()


def prompt(name: str, **fields: object) -> str:
    """prompts/*.txt 를 읽어 {필드}를 채운다. 프롬프트는 코드와 분리한다."""
    text = (PROMPT_DIR / f"{name}.txt").read_text(encoding="utf-8")
    for key, value in fields.items():
        text = text.replace("{" + key + "}", str(value))
    return text


# ─────────────────────────────────────────────────────────────
# Upstage
# ─────────────────────────────────────────────────────────────

def _upstage(path: str, *, json_body: dict | None = None, files: dict | None = None,
             data: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {os.environ['UPSTAGE_API_KEY']}"}
    last: Exception | None = None
    for attempt in range(RETRIES + 1):
        try:
            res = requests.post(f"{UPSTAGE_BASE}{path}", headers=headers, json=json_body,
                                files=files, data=data, timeout=TIMEOUT)
            if res.status_code == 429 or res.status_code >= 500:
                raise RuntimeError(f"{res.status_code} {res.text[:200]}")
            if res.status_code >= 400:
                raise RuntimeError(f"Upstage {res.status_code}: {res.text[:400]}")
            return res.json()
        except (requests.RequestException, RuntimeError) as exc:
            last = exc
            if attempt == RETRIES or "Upstage 4" in str(exc):
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(str(last))


@lru_cache(maxsize=1)
def _anthropic():
    import anthropic

    return anthropic.Anthropic()


# ─────────────────────────────────────────────────────────────
# 공개 함수
# ─────────────────────────────────────────────────────────────

def ask_json(system: str, user: str, schema: dict, effort: str = "high",
             max_tokens: int = 8000, images: list[bytes] | None = None) -> dict:
    """JSON만 받아온다. 스키마를 서버가 강제하므로 파싱은 안전하다."""
    kind = provider()

    if kind == "upstage":
        body = {
            "model": UPSTAGE_MODEL,
            "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_schema", "json_schema": {
                "name": "result", "schema": schema, "strict": True}},
        }
        res = _upstage("/chat/completions", json_body=body)
        return json.loads(res["choices"][0]["message"]["content"])

    if kind == "anthropic":
        content: list = [{"type": "text", "text": user}]
        for raw in images or []:
            content.insert(0, _image_block(raw))
        res = _anthropic().messages.create(
            model=ANTHROPIC_MODEL, max_tokens=max_tokens, system=system,
            thinking={"type": "adaptive"},
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            messages=[{"role": "user", "content": content}],
        )
        if res.stop_reason == "refusal":
            raise RuntimeError(f"모델이 응답을 거절했습니다: {res.stop_details}")
        return json.loads(next(b.text for b in res.content if b.type == "text"))

    raise RuntimeError("AI 키가 없습니다 — 목업 경로로 처리해야 합니다")


def read_document(data: bytes, filename: str = "upload.png") -> str:
    """사진·PDF에서 글자와 표 구조를 읽어 텍스트로 돌려준다.

    Upstage Document Parse는 한국어 표를 구조 그대로 뽑아준다.
    Claude는 vision으로 직접 읽으므로 여기서는 빈 문자열을 준다(extract가 이미지로 넘긴다).
    """
    if provider() != "upstage":
        return ""
    res = _upstage("/document-digitization",
                   files={"document": (filename, data)},
                   data={"model": UPSTAGE_PARSE_MODEL})
    content = res.get("content", {})
    return content.get("markdown") or content.get("html") or content.get("text") or ""


def embed(texts: list[str], kind: str = "passage") -> list[list[float]] | None:
    """검색용 임베딩. Upstage가 아니면 None (retrieve가 로컬 해시로 대체한다)."""
    if provider() != "upstage":
        return None
    res = _upstage("/embeddings", json_body={"model": f"embedding-{kind}", "input": texts})
    return [row["embedding"] for row in sorted(res["data"], key=lambda r: r["index"])]


def _image_block(data: bytes, media_type: str = "image/png") -> dict:
    import base64

    return {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                        "data": base64.standard_b64encode(data).decode()}}
