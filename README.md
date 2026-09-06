# 리햅톡 (RehabTalk) — 데모

수술 후 재활 운동처방을 **설계하고 전달하는** 흐름을 끝까지 보여주는 데모입니다.
설계 원칙과 범위는 [CLAUDE.md](CLAUDE.md)에 있습니다.

> 데모용입니다. 프로토콜 수치와 환자 정보는 구조를 보여주기 위한 예시이며
> **실제 임상 처방에 사용할 수 없습니다.**

## 실행

### Docker (권장)

```bash
cp .env.example .env      # UPSTAGE_API_KEY 채우기 (비워도 목업으로 돕니다)
docker compose up -d --build
```

| 화면 | 주소 |
|---|---|
| 치료사 (Streamlit) | http://localhost:8501 |
| 환자 모바일 웹 | http://localhost:8000/p/tok_kim62 |
| API 문서 | http://localhost:8000/docs |

8000·8501번을 이미 쓰고 있다면 `.env`에서 바꿉니다. 환자 링크도 따라갑니다.

```bash
BACKEND_PORT=18000
FRONTEND_PORT=18501
```

```bash
docker compose logs -f backend    # 로그
docker compose down               # 정지 (데이터는 볼륨에 남습니다)
docker compose down -v            # 데이터까지 초기화
```

### 로컬 (Docker 없이)

```bash
./run.sh
```

## AI 모드

`.env`의 키에 따라 `backend/ai/client.py`가 알아서 정합니다. 나머지 코드는 provider를 모릅니다.

| 모드 | 조건 | 쓰는 것 |
|---|---|---|
| `upstage` (기본) | `UPSTAGE_API_KEY` | Solar Pro 4 (JSON 스키마 강제) · Document Parse (사진→표) · 임베딩 4096차원 |
| `anthropic` | `ANTHROPIC_API_KEY` + `AI_PROVIDER=anthropic` | Claude (채팅 + vision) |
| `mock` | 키 없음 | 각 모듈의 목업. 데모 6장면은 키 없이도 끝까지 돕니다 |

```bash
cp .env.example .env      # 키를 채우면 실제 호출
curl -s localhost:8000/api/health   # 현재 모드 확인
```

프로토콜 사진은 Upstage에서 **Document Parse → Solar 구조화** 순서로 처리합니다.
Solar 채팅 모델은 이미지를 받지 않기 때문이고, 한국어 표는 이쪽이 더 정확합니다.

## 시연 순서

1. **환자 목록**에서 김O호(62세, 대형 파열, 3주차)를 엽니다.
2. **프로토콜** 화면에 `data/sample_protocol.png`를 올리고 *AI로 6칸 추출*.
   2단계·4단계가 **확인 필요**로 표시됩니다 — 못 읽은 칸은 지어내지 않고 비워 둡니다.
   값을 고치고 *맞음*을 누르면 확정(version+1)됩니다.
3. **처방** 화면에서 *AI 초안 만들기*.
   통과한 운동 옆에 **제외된 항목이 이유와 rule_id와 함께** 나옵니다.
   (1단계에서 능동보조 운동 3개가 `RC-P1-FORBID-AAROM`으로 잘립니다)
4. 체크 후 *카카오톡으로 보내기* → 알림톡 미리보기와 **세팅~발송 소요 시간**이 표시됩니다.
5. 환자 링크를 열어 완료 체크·통증·가동범위를 기록합니다.
   메모에 "빨갛게 붓고 열이 나요"를 적으면 **적신호**로 인박스에 올라갑니다.
6. **인박스**에서 "2주째 가동범위 정체" 카드와 조정 후보 2개를 확인하고 하나를 골라 보냅니다.
   적신호 카드에는 조정 후보 대신 **규칙이 만든 연락 안내**만 나옵니다.

## 구조

```
backend/core/    규칙 — LLM 호출 없음. 순수 함수. 같은 입력이면 같은 출력
backend/ai/      LLM 호출은 여기서만. 목업 ↔ 실제 전환도 여기서
backend/lib/     sanitize(PII 제거) · db(SQLite) · notify(알림톡 미리보기)
backend/api/     FastAPI 라우터 + 환자 모바일 웹(Jinja2)
frontend/        Streamlit — 표시와 입력만. 규칙 검사도 AI 호출도 하지 않음
```

### 컨테이너 (역할별로 하나씩)

| 서비스 | 책임 | 노출 |
|---|---|---|
| `chroma` | 검색 인덱스 저장·조회 | 내부만 |
| `backend` | 규칙 판정 · AI 호출 · API · 환자 웹 | 8000 |
| `frontend` | 치료사 화면 (백엔드 API만 호출) | 8501 |

의존성도 역할별로 나눠 둡니다 — `requirements/backend.txt`, `requirements/frontend.txt`.
치료사 화면 이미지에는 AI·DB 라이브러리가 들어가지 않습니다.

상태는 두 볼륨에만 있습니다.

| 볼륨 | 내용 |
|---|---|
| `rehabtalk-data` | SQLite — 환자·프로토콜·처방·피드백 |
| `chroma-data` | 검색 인덱스 |

파이프라인 순서는 항상 `sanitize → 검색 → AI → rules.check → 화면`입니다.
AI 출력은 규칙 검사를 통과해야만 화면에 뜹니다.

## 테스트

```bash
.venv/bin/python -m pytest -q          # 30개
```

- `tests/test_rules.py` — CLAUDE.md의 판정 표 7개 케이스 + 순수성·3층 병합·정체 감지
- `tests/test_sanitize.py` — 식별정보가 AI 입력에 남지 않는지
- `tests/test_api.py` — 시연 6장면
- `tests/test_frontend.py` — 치료사 화면 3개 (백엔드가 떠 있을 때만 실행)
- `tests/test_live_ai.py` — 실제 provider 호출 (키가 있을 때만 실행)

테스트는 기본적으로 **목업 AI**로 돕니다(결정론적·무료). `test_live_ai.py`만 실제 키를 씁니다.

## 아직 하지 않은 것

실제 카카오 알림톡 발송, 환자 챗봇, 로그인, EMR 연동, 회전근개 외 질환.
`lib/notify.py`의 `send_kakao()` 하나만 교체하면 실제 발송으로 넘어갑니다.
