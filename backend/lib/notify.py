"""알림톡 발송. 데모에서는 미리보기 문자열만 만든다.

실제 연동 시 send_kakao()의 본문만 교체하면 된다 — 호출부는 그대로.
"""

from __future__ import annotations

import os
from datetime import date

TEMPLATE_CODE = "REHAB_DAILY_01"
BASE_URL = os.getenv("PATIENT_BASE_URL", "http://localhost:8000")


def patient_link(token: str) -> str:
    return f"{BASE_URL}/p/{token}"


def send_kakao(name: str | None, token: str, exercises: list[dict], today: date | None = None,
               status: str | None = None) -> dict:
    """실제 발송 대신 알림톡 미리보기를 돌려준다.

    영상이 등록된 운동은 링크를 함께 보낸다. 없으면 글 설명만 간다 — 지어내지 않는다.
    """
    today = today or date.today()
    minutes = sum(e.get("minutes", 5) for e in exercises)
    lines = [f"[리햅톡] {name or '환자'}님, 오늘의 재활 운동입니다",
             f"{today.month}월 {today.day}일 · 총 {len(exercises)}개 · 약 {minutes}분", ""]
    if status:
        lines += [status, ""]
    for i, ex in enumerate(exercises, 1):
        rom = f" ({ex['rom']}°까지)" if ex.get("rom") else ""
        lines.append(f"{i}. {ex['name']}{rom} — {ex['dose']}")
        if ex.get("video_url"):
            lines.append(f"   ▶ 영상 {ex['video_url']}")
    lines += ["", "▼ 아래 링크에서 오늘 운동을 확인하고 완료를 체크해 주세요", patient_link(token)]

    return {
        "sent": False,                       # 데모: 실제로 보내지 않음
        "channel": "kakao_alimtalk(preview)",
        "template_code": TEMPLATE_CODE,
        "preview": "\n".join(lines),
        "link": patient_link(token),
    }
