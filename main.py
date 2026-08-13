from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date, timedelta
import calendar
import re
from typing import Optional
import os
import supabase_client as db

app = FastAPI(title="SCM 통합 캘린더")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
@app.head("/")
def root():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8") as f:
        return f.read()


@app.get("/health")
@app.head("/health")
def health():
    return {"status": "ok"}


# ── 업무 API ─────────────────────────────────────────────────

@app.get("/api/tasks")
def list_tasks(
    파트: Optional[str] = None,
    팀: Optional[str] = None,
    주기: Optional[str] = None,
    구분: Optional[str] = None,
    주인: Optional[str] = None,
):
    f = {}
    if 파트: f["파트"] = 파트
    if 팀: f["팀"] = 팀
    if 주기: f["주기"] = 주기
    if 구분: f["구분"] = 구분
    # 주인은 콤마/마침표로 여러 명이 함께 적혀있을 수 있어 부분(포함) 일치로 검색
    if 주인: f["주인"] = ("ilike", f"*{주인}*")
    return db.select_tasks(f)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: int):
    try:
        return db.get_task(task_id)
    except ValueError:
        raise HTTPException(404, "업무를 찾을 수 없습니다")


# ── 캘린더 API ───────────────────────────────────────────────

@app.get("/api/calendar/{year}/{month}")
def get_calendar(year: int, month: int):
    tasks = db.select_tasks()
    logs  = db.select_logs_for_month(f"{year}-{month:02d}")

    log_lookup: dict[int, dict[str, str]] = {}
    for log in logs:
        tid = log["task_id"]
        log_lookup.setdefault(tid, {})[log["period_key"]] = log["status"]

    events = _generate_events(tasks, year, month, log_lookup)
    task_map = {t["id"]: t for t in tasks}
    return {"year": year, "month": month, "events": events, "tasks": task_map}


# ── 로그 API ─────────────────────────────────────────────────

@app.get("/api/tasks/{task_id}/logs")
def get_logs(task_id: int):
    return db.select_logs(task_id)


class LogIn(BaseModel):
    period_key: str
    status: str = "done"
    memo: Optional[str] = ""


@app.post("/api/tasks/{task_id}/logs")
def upsert_log(task_id: int, body: LogIn):
    existing = db.find_log(task_id, body.period_key)
    if existing:
        return db.update_log(existing["id"], body.status, body.memo or "")
    return db.insert_log(task_id, body.period_key, body.status, body.memo or "")


@app.delete("/api/task_logs/{log_id}")
def remove_log(log_id: int):
    db.delete_log(log_id)
    return {"deleted": True}


class TaskCreate(BaseModel):
    파트: Optional[str] = None
    주기: Optional[str] = None
    구분: Optional[str] = None
    업무: str
    주인: Optional[str] = None
    시기_마감: Optional[str] = None
    output: Optional[str] = None
    비고: Optional[str] = None


@app.post("/api/tasks")
def create_task(body: TaskCreate):
    return db.insert_task({k: v for k, v in body.dict().items() if v is not None})


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    db.delete_task(task_id)
    return {"deleted": True}


# ── 통계 API ─────────────────────────────────────────────────

@app.get("/api/stats")
def get_stats():
    tasks = db.select_tasks()
    logs  = db.select_recent_logs(20)

    by_part: dict = {}
    by_cycle: dict = {}
    by_cat:  dict = {}
    by_owner: dict = {}

    for t in tasks:
        for bucket, key in [(by_part,"파트"),(by_cycle,"주기"),(by_cat,"구분"),(by_owner,"주인")]:
            val = t.get(key) or "미지정"
            bucket[val] = bucket.get(val, 0) + 1

    return {"total": len(tasks), "by_part": by_part, "by_cycle": by_cycle,
            "by_category": by_cat, "by_owner": by_owner, "recent_logs": logs}


@app.get("/api/contracts")
def get_contracts():
    today = date.today()
    deadline = date(today.year + (today.month + 5) // 12, (today.month + 5) % 12 + 1, today.day)

    rows = db.select_contracts()
    result = []
    for row in rows:
        end = date.fromisoformat(row["계약기간종료일"])
        result.append({
            "id": row["id"],
            "계약구분": row["계약구분"],
            "공급업체명": row["공급업체명"],
            "계약기간종료일": row["계약기간종료일"],
            "d_day": (end - today).days,
            "expiring_soon": end <= deadline,
        })
    return result


class ContractIn(BaseModel):
    계약구분: str
    공급업체명: str
    계약기간종료일: str


@app.post("/api/contracts")
def create_contract(body: ContractIn):
    return db.insert_contract(body.dict())


@app.patch("/api/contracts/{contract_id}")
def update_contract(contract_id: int, body: ContractIn):
    return db.update_contract(contract_id, body.dict())


@app.delete("/api/contracts/{contract_id}")
def delete_contract(contract_id: int):
    db.delete_contract(contract_id)
    return {"deleted": True}


@app.get("/api/filters")
def get_filters():
    tasks = db.select_tasks()
    def uniq(k):
        return sorted({t[k] for t in tasks if t.get(k)})

    # 주인 컬럼은 "김예지, 조은혜"처럼 콤마/마침표로 여러 명이 함께 적혀있어
    # 담당자 필터는 개별 이름 단위로 쪼개서 목록을 만든다.
    owners: set[str] = set()
    for t in tasks:
        for name in re.split(r"[,.]", t.get("주인") or ""):
            name = name.strip()
            if name:
                owners.add(name)

    return {
        "파트": uniq("파트"), "팀": uniq("팀"), "주기": uniq("주기"),
        "구분": uniq("구분"), "주인": sorted(owners),
    }


# ── 캘린더 이벤트 생성 ────────────────────────────────────────

def _dates_for_task(task: dict, year: int, month: int) -> list[tuple[int, str]]:
    import re as _re
    주기 = task.get("주기") or ""
    시기 = (task.get("시기_마감") or "").strip()
    last = calendar.monthrange(year, month)[1]

    def all_wd(wd: int) -> list[int]:
        return [d for d in range(1, last + 1) if date(year, month, d).weekday() == wd]

    def week_key(d: int) -> str:
        dt = date(year, month, d)
        mon = dt - timedelta(days=dt.weekday())
        return mon.strftime("%Y-W%W")

    if 주기 == "매일":
        return [(d, f"{year}-{month:02d}-{d:02d}") for d in range(1, last + 1)
                if date(year, month, d).weekday() < 5]

    if 주기 == "매주":
        wd_map = {"월":0,"화":1,"수":2,"목":3,"금":4,"토":5,"일":6}
        if "주 2회" in 시기 or "주2회" in 시기:
            days = [d for d in range(1, last+1) if date(year,month,d).weekday() in (1,3)]
        elif "주1회" in 시기 or "주 1회" in 시기:
            days = all_wd(2)  # 수요일
        else:
            target = next((n for nm,n in wd_map.items() if nm in 시기), 0)
            days = all_wd(target)
        return [(d, week_key(d)) for d in days]

    if 주기 == "매월":
        mk = f"{year}-{month:02d}"
        WD_KO = {"월":0,"화":1,"수":2,"목":3,"금":4}

        def first_biz() -> int:
            """당월 첫 영업일 (1일이 주말이면 다음 월요일)"""
            d = 1
            while date(year, month, d).weekday() >= 5:
                d += 1
            return d

        def last_biz() -> int:
            """당월 마지막 영업일 (말일이 주말이면 직전 금요일)"""
            d = last
            while date(year, month, d).weekday() >= 5:
                d -= 1
            return d

        def to_biz(d: int) -> int:
            """특정 날짜가 주말이면 다음 영업일로 (월 밖이면 직전 금요일)"""
            dt = date(year, month, min(d, last))
            wd = dt.weekday()
            if wd == 5:
                nxt = dt + timedelta(days=2)
                return nxt.day if nxt.month == month else (dt - timedelta(1)).day
            if wd == 6:
                nxt = dt + timedelta(days=1)
                return nxt.day if nxt.month == month else (dt - timedelta(2)).day
            return dt.day

        def nth_monday(week: int) -> int:
            """월 내 N번째 월요일 날짜 (없으면 0) — 주차 계산 기준"""
            count = 0
            for d in range(1, last + 1):
                if date(year, month, d).weekday() == 0:
                    count += 1
                    if count == week:
                        return d
            return 0

        def week_n_day(week: int, wd: int) -> int:
            """N주차(월요일 기준)의 wd 요일 날짜. wd: 월=0 화=1 수=2 목=3 금=4"""
            mon = nth_monday(week)
            if not mon:
                return 0
            d = mon + wd
            return d if d <= last else 0

        def mid_biz() -> int:
            """해당 월 영업일 목록의 가운데 날짜"""
            biz = [d for d in range(1, last + 1) if date(year, month, d).weekday() < 5]
            return biz[len(biz) // 2]

        def parse_single(s: str) -> list[int]:
            s = s.strip()

            # N/M주차 요일 (예: '2/4주차 목요일')
            m = _re.match(r'^(\d)/(\d)주차\s*([월화수목금])', s)
            if m:
                wd = WD_KO[m.group(3)]
                return [d for d in [week_n_day(int(m.group(1)), wd),
                                     week_n_day(int(m.group(2)), wd)] if d]

            # N주차 요일 (예: '2주차 목요일', '3주차 월요일')
            m = _re.match(r'^(\d)주차\s*([월화수목금])', s)
            if m:
                d = week_n_day(int(m.group(1)), WD_KO[m.group(2)])
                return [d] if d else []

            # N주차 단독 (예: '1주차', '2주차') → 해당 주 금요일
            m = _re.match(r'^(\d)주차$', s)
            if m:
                d = week_n_day(int(m.group(1)), 4)
                return [d] if d else []

            # 결산 후 즉시 → 5일 기준 첫 영업일
            if "결산" in s:
                return [to_biz(5)]

            # 중순~말 / 월중순~말 → 월 영업일 중간
            if "중순~말" in s:
                return [mid_biz()]

            # 월말 / 말일 / 당월 말
            if "월말" in s or "말일" in s or "당월 말" in s:
                return [last_biz()]

            # 1~4주차 (매주 반복)
            if "1~4주차" in s or "1-4주차" in s:
                return all_wd(0)

            # 첫 영업일 / 월초
            if "첫 영업일" in s or "첫영업일" in s or "월초" in s:
                return [first_biz()]

            # 중순 → 월 영업일 중간
            if "중순" in s:
                return [mid_biz()]

            # 월 2회
            if "월 2회" in s or "월2회" in s:
                return [to_biz(10), to_biz(25)]

            # 수시
            if "수시" in s:
                return [first_biz()]

            # N일 패턴 (예: '매월 20일', '20일')
            m = _re.search(r'(\d+)일', s)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 31:
                    return [to_biz(n)]

            # 기본: 첫 영업일
            return [first_biz()]

        # 콤마로 구분된 복합 패턴 처리 (예: '3주차 월요일, 4주차 금요일')
        parts = [p.strip() for p in 시기.split(",")]
        days_set: list[int] = []
        for part in parts:
            days_set.extend(parse_single(part))

        days = sorted(set(d for d in days_set if 1 <= d <= last))
        return [(d, mk) for d in days]

    if 주기 == "분기":
        # 분기 말월(3/6/9/12)의 마지막 영업일에 1회 표시
        if month not in (3, 6, 9, 12):
            return []
        quarter = (month - 1) // 3 + 1
        d = last
        while date(year, month, d).weekday() >= 5:
            d -= 1
        return [(d, f"{year}-Q{quarter}")]

    return []


def _generate_events(tasks, year, month, log_lookup):
    events: dict[str, list] = {}
    for task in tasks:
        tid = task["id"]
        for (d, pk) in _dates_for_task(task, year, month):
            ds = f"{year}-{month:02d}-{d:02d}"
            status = log_lookup.get(tid, {}).get(pk, "pending")
            events.setdefault(ds, []).append({"task_id": tid, "period_key": pk, "status": status})
    return events
