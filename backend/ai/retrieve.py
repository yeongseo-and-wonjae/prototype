"""Chroma 검색. 메타데이터 필터를 먼저 걸고 그 안에서 의미 검색한다.

색인 대상은 프로토콜 조각과 문헌 근거 카드뿐이다.
운동 라이브러리와 금지 목록은 벡터에 넣지 않는다 — 태그 필터와 rules.check의 몫.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from . import client

DATA = Path(__file__).resolve().parents[2] / "data"
CHROMA_DIR = Path(__file__).resolve().parents[2] / ".chroma"
HASH_DIM = 256


def _hash_vec(text: str) -> list[float]:
    """오프라인 결정론적 임베딩 (문자 2-gram 해시). 임베딩 API가 없을 때만 쓴다."""
    cleaned = re.sub(r"\s+", "", text or "")
    grams = [cleaned[i:i + 2] for i in range(max(0, len(cleaned) - 1))] or [cleaned or "∅"]
    vec = [0.0] * HASH_DIM
    for gram in grams:
        idx = int(hashlib.md5(gram.encode()).hexdigest()[:8], 16) % HASH_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def backend_name() -> str:
    """어떤 임베딩으로 검색하는지. 컬렉션 이름을 나눠 차원 충돌을 막는다."""
    return "upstage" if client.provider() == "upstage" else "hash"


@lru_cache(maxsize=1)
def _embedding_fn():
    from chromadb.api.types import EmbeddingFunction

    class RehabEmbedding(EmbeddingFunction):
        """문서는 passage, 질의는 query 임베딩을 쓴다 (Upstage 권장).

        Upstage가 없으면 로컬 해시로 떨어진다 — 검색 품질은 낮지만 오프라인으로 돈다.
        """

        def __init__(self) -> None:
            pass

        @staticmethod
        def name() -> str:
            return f"rehab_{backend_name()}"

        def __call__(self, input):  # noqa: A002 — chroma 계약
            return self._embed(list(input), "passage")

        def embed_query(self, input):  # noqa: A002
            return self._embed(list(input), "query")

        def _embed(self, texts: list[str], kind: str) -> list[list[float]]:
            vectors = client.embed(texts, kind)
            return vectors if vectors is not None else [_hash_vec(t) for t in texts]

        def get_config(self) -> dict:
            return {"backend": backend_name()}

        @staticmethod
        def build_from_config(config: dict):
            return _embedding_fn()

    return RehabEmbedding()


#: 문헌 근거 카드. 데모용 요약이며 실제 인용으로 쓸 수 없다.
EVIDENCE_CARDS = [
    {"id": "ev01", "phase": 1, "text": "봉합 직후 6주간은 수동 관절운동만 시행하고 능동 거상은 피한다. 조기 능동 운동은 재파열 위험을 높인다.", "source": "문헌 요약(데모)"},
    {"id": "ev02", "phase": 1, "text": "진자 운동은 통증 감소와 관절 유착 예방에 도움이 되며 1단계 표준 항목으로 권장된다.", "source": "문헌 요약(데모)"},
    {"id": "ev03", "phase": 1, "text": "대형·광범위 파열에서는 외회전 각도를 더 보수적으로 제한하고 보조기 착용 기간을 늘린다.", "source": "문헌 요약(데모)"},
    {"id": "ev04", "phase": 2, "text": "6주 이후 능동보조 운동으로 전환하며 통증 없는 범위 안에서 점진적으로 각도를 늘린다.", "source": "문헌 요약(데모)"},
    {"id": "ev05", "phase": 2, "text": "등척성 수축은 저항 운동 전 단계로 안전하게 근력을 유지하는 방법이다.", "source": "문헌 요약(데모)"},
    {"id": "ev06", "phase": 3, "text": "12주 이후 가벼운 저항밴드 운동을 시작하되 통증과 보상 동작을 관찰한다.", "source": "문헌 요약(데모)"},
    {"id": "ev07", "phase": 4, "text": "16주 이후 기능적 과제와 지구력 훈련으로 넘어가며 스포츠 복귀는 집도의 확인 후 결정한다.", "source": "문헌 요약(데모)"},
    {"id": "ev08", "phase": 2, "text": "2주 이상 가동범위가 정체되면 용량을 늘리기 전에 통증·부종·보상 패턴을 먼저 확인한다.", "source": "문헌 요약(데모)"},
]


@lru_cache(maxsize=1)
def _collection():
    import chromadb

    chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = chroma.get_or_create_collection(
        name=f"rehab_evidence_{backend_name()}", embedding_function=_embedding_fn()
    )
    if col.count() == 0:
        _index(col)
    return col


def _index(col) -> None:
    docs, metas, ids = [], [], []

    protocol = json.loads((DATA / "standard_protocol.json").read_text(encoding="utf-8"))
    for slot in protocol["slots"]:
        docs.append(
            f"{slot['phase']}단계 {slot['weeks'][0]}~{slot['weeks'][1]}주. "
            f"보조기: {slot['brace']}. 허용: {', '.join(slot['allowed'])}. "
            f"금지: {', '.join(slot['forbidden'])}. {slot['source_text']}"
        )
        metas.append({"surgery": "rotator_cuff", "phase": slot["phase"], "kind": "protocol", "source": "표준본"})
        ids.append(f"proto-{slot['phase']}")

    for card in EVIDENCE_CARDS:
        docs.append(card["text"])
        metas.append({"surgery": "rotator_cuff", "phase": card["phase"], "kind": "evidence", "source": card["source"]})
        ids.append(card["id"])

    col.add(documents=docs, metadatas=metas, ids=ids)


def search(query: str, phase: int, surgery: str = "rotator_cuff", n_results: int = 5) -> list[dict]:
    """메타데이터 필터 → 의미 검색. 실패하면 빈 목록 (지어내지 않는다)."""
    try:
        col = _collection()
        res = col.query(
            query_texts=[query],
            where={"$and": [{"surgery": surgery}, {"phase": phase}]},
            n_results=n_results,
        )
    except Exception as exc:  # 색인이 없거나 chroma가 안 뜨면 검색 없이 진행한다
        print(f"[retrieve] 검색 건너뜀: {exc}")
        return []

    out = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        out.append({"text": doc, "kind": meta["kind"], "source": meta["source"], "phase": meta["phase"]})
    return out


def reset(wipe: bool = False) -> None:
    """캐시를 비운다. wipe=True면 색인 파일까지 지운다 (데이터를 고친 뒤)."""
    _collection.cache_clear()
    if wipe:
        import shutil

        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
