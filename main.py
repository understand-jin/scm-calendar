from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import date, timedelta
import calendar
from typing import Optional
import os
import supabase_client as db

app = FastAPI(title="SCM 통합 캘린더")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
def root():
    with open(os.path.join(os.path.dirname(__file__), "static", "index.html"), encoding="utf-8") as f:
        return f.read()


# ── 업무 API ─────────────────────────────────────────────────

@app.get("/api/tasks")
def list_tasks(
    파트: Optional[str] = None,
    주기: Optional[str] = None,
    구분: Optional[str] = None,
    주인: Optional[str] = None,
):
    f = {}
    if 파트: f["파트"] = 파트
    if 주기: f["주기"] = 주기
    if 구분: f["구분"] = 구분
    if 주인: f["주인"] = 주인
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


@app.get("/api/filters")
def get_filters():
    tasks = db.select_tasks()
    def uniq(k):
        return sorted({t[k] for t in tasks if t.get(k)})
    return {"파트": uniq("파트"), "주기": uniq("주기"), "구분": uniq("구분"), "주인": uniq("주인")}


# ── 캘린더 이벤트 생성 ────────────────────────────────────────

def _dates_for_task(task: dict, year: int, month: int) -> list[tuple[int, str]]:
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
            days = all_wd(0)
        else:
            target = next((n for nm,n in wd_map.items() if nm in 시기), 0)
            days = all_wd(target)
        return [(d, week_key(d)) for d in days]

    if 주기 == "매월":
        mk = f"{year}-{month:02d}"
        if "결산" in 시기:
            days = [25]
        elif "1~4주차" in 시기 or "1-4주차" in 시기:
            days = all_wd(0)
        elif "월말" in 시기:
            days = [last]
        elif "중순~말" in 시기:
            days = [20]
        elif "중순" in 시기:
            days = [15]
        elif "첫째주" in 시기 or "월초" in 시기:
            days = [1]
        elif "월 2회" in 시기 or "월2회" in 시기:
            days = [10, 25]
        elif "수시" in 시기:
            days = [1]
        else:
            days = [1]
        return [(d, mk) for d in days if d <= last]

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
