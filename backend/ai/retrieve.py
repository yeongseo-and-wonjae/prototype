"""Chroma 검색. 메타데이터 필터를 먼저 걸고 그 안에서 의미 검색한다.

색인 대상은 프로토콜 조각과 문헌 근거 카드뿐이다.
운동 라이브러리와 금지 목록은 벡터에 넣지 않는다 — 태그 필터와 rules.check의 몫.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from functools import lru_cache
from pathlib import Path

from . import client

DATA = Path(__file__).resolve().parents[2] / "data"
CHROMA_DIR = Path(os.getenv("CHROMA_DIR", Path(__file__).resolve().parents[2] / ".chroma"))
CHROMA_HOST = os.getenv("CHROMA_HOST")          # 있으면 별도 컨테이너의 인덱스를 쓴다
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
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

        def _embed(self, texts: list[str], kind: str):
            import numpy as np

            vectors = client.embed(texts, kind)
            if vectors is None:
                vectors = [_hash_vec(t) for t in texts]
            # chroma HttpClient 는 배열에 .tolist() 를 호출한다 — 리스트를 주면 깨진다
            return [np.asarray(v, dtype=np.float32) for v in vectors]

        def get_config(self) -> dict:
            return {"backend": backend_name()}

        @staticmethod
        def build_from_config(config: dict):
            return _embedding_fn()

    return RehabEmbedding()


#: Patient.tear_size → 근거 트랙. 파열 크기에 따라 갈리는 근거를 걸러내기 위한 것이다.
TEAR_TRACK = {"소형~중형": "소~중", "대형": "대·광범위", "광범위": "대·광범위"}


@lru_cache(maxsize=1)
def _evidence() -> tuple[list[dict], dict[str, dict]]:
    """근거 카드와 출처 레지스트리. 카드에는 출처 id만 두고 표시할 때 조인한다."""
    cards = json.loads((DATA / "evidence.json").read_text(encoding="utf-8"))["cards"]
    sources = {s["id"]: s for s in
               json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["sources"]}
    unknown = [c["id"] for c in cards if c["source_id"] not in sources]
    if unknown:                                    # 출처 없는 카드는 색인하지 않는다
        raise ValueError(f"출처 미등록 카드: {unknown}")
    return cards, sources


@lru_cache(maxsize=1)
def _collection():
    import chromadb

    if CHROMA_HOST:                                # docker compose: chroma 서비스
        chroma = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    else:                                          # 로컬 실행: 파일로 보관
        chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = chroma.get_or_create_collection(
        name=f"rehab_evidence_v2_{backend_name()}", embedding_function=_embedding_fn()
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
        metas.append({
            "surgery": "rotator_cuff", "kind": "protocol",
            "phase_min": slot["phase"], "phase_max": slot["phase"],
            "tear_track": "공통", "evidence_level": "표준본",
            "source": "표준본", "source_id": "standard", "url": "", "needs_review": False,
        })
        ids.append(f"proto-{slot['phase']}")

    cards, sources = _evidence()
    for card in cards:
        src = sources[card["source_id"]]
        docs.append(card["text"])
        metas.append({
            "surgery": card.get("surgery", "rotator_cuff"), "kind": "evidence",
            "phase_min": card["phase_min"], "phase_max": card["phase_max"],
            "tear_track": card["tear_track"], "evidence_level": card["evidence_level"],
            "source": src["label"], "source_id": card["source_id"],
            "url": src["url"], "needs_review": card["needs_review"],
        })
        ids.append(card["id"])

    col.add(documents=docs, metadatas=metas, ids=ids)


def search(query: str, phase: int, tear_size: str | None = None,
           surgery: str = "rotator_cuff", n_results: int = 5) -> list[dict]:
    """메타데이터 필터 → 의미 검색. 실패하면 빈 목록 (지어내지 않는다).

    카드가 걸쳐 있는 단계를 phase_min~phase_max로 두었으므로 정확일치가 아니라 범위로 본다.
    tear_size를 주면 그 트랙과 '공통' 카드만 남긴다 — 대파열 환자에게
    소~중 파열에서만 성립하는 근거가 딸려가지 않게 하려는 것이다.
    """
    where = [
        {"surgery": surgery},
        {"phase_min": {"$lte": phase}},
        {"phase_max": {"$gte": phase}},
    ]
    track = TEAR_TRACK.get(tear_size or "")
    if track:
        where.append({"tear_track": {"$in": [track, "공통"]}})

    try:
        col = _collection()
        res = col.query(query_texts=[query], where={"$and": where}, n_results=n_results)
    except Exception as exc:  # 색인이 없거나 chroma가 안 뜨면 검색 없이 진행한다
        print(f"[retrieve] 검색 건너뜀: {exc}")
        return []

    out = []
    for doc, meta in zip(res["documents"][0], res["metadatas"][0]):
        out.append({
            "text": doc, "kind": meta["kind"], "source": meta["source"],
            "evidence_level": meta["evidence_level"], "tear_track": meta["tear_track"],
            "url": meta["url"], "needs_review": bool(meta["needs_review"]),
        })
    return out


def reset(wipe: bool = False) -> None:
    """캐시를 비운다. wipe=True면 색인 파일까지 지운다 (데이터를 고친 뒤)."""
    _collection.cache_clear()
    _evidence.cache_clear()
    if wipe:
        import shutil

        shutil.rmtree(CHROMA_DIR, ignore_errors=True)
