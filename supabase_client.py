"""
Supabase REST API (PostgREST) thin client — works with sb_publishable_ keys.
"""
import httpx
from typing import Any, Optional

import os
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://yurasobkmfyoraabtyjg.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_Khj6wUETdmDS83TiLihoiA_e218Q_Fj")

_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

def _url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"

def _get(table: str, params: dict | None = None) -> list[dict]:
    r = httpx.get(_url(table), headers=_HEADERS, params=params or {}, timeout=15, verify=False)
    r.raise_for_status()
    return r.json()

def _post(table: str, data: list[dict] | dict) -> list[dict]:
    r = httpx.post(_url(table), headers=_HEADERS, json=data, timeout=15, verify=False)
    r.raise_for_status()
    return r.json()

def _patch(table: str, params: dict, data: dict) -> list[dict]:
    r = httpx.patch(_url(table), headers=_HEADERS, params=params, json=data, timeout=15, verify=False)
    r.raise_for_status()
    return r.json()

def _delete(table: str, params: dict) -> list[dict]:
    r = httpx.delete(_url(table), headers=_HEADERS, params=params, timeout=15, verify=False)
    r.raise_for_status()
    return r.json() if r.content else []

# ── 공개 API ─────────────────────────────────────────────────

def ping() -> bool:
    try:
        _get("tasks", {"select": "id", "limit": "1"})
        return True
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return False  # table not found
        raise

# tasks
def select_tasks(filters: dict | None = None) -> list[dict]:
    """filters 값은 보통 문자열(=eq 완전일치)이지만, (연산자, 값) 튜플을
    넘기면 해당 PostgREST 연산자를 사용한다. 예: ("ilike", "*조은혜*")"""
    params = {"select": "*", "order": "id.asc"}
    for k, v in (filters or {}).items():
        if isinstance(v, tuple):
            op, val = v
            params[k] = f"{op}.{val}"
        else:
            params[k] = f"eq.{v}"
    return _get("tasks", params)

def get_task(task_id: int) -> dict:
    rows = _get("tasks", {"select": "*", "id": f"eq.{task_id}"})
    if not rows:
        raise ValueError(f"Task {task_id} not found")
    return rows[0]

def insert_tasks(rows: list[dict]) -> list[dict]:
    return _post("tasks", rows)

def delete_all_tasks() -> None:
    _delete("tasks", {"id": "gte.0"})

# task_logs
def select_logs(task_id: int) -> list[dict]:
    return _get("task_logs", {"select": "*", "task_id": f"eq.{task_id}", "order": "logged_at.desc"})

def select_logs_for_month(month_prefix: str) -> list[dict]:
    year = month_prefix[:4]
    monthly   = _get("task_logs", {"select": "*", "period_key": f"like.{month_prefix}%"})
    weekly    = _get("task_logs", {"select": "*", "period_key": f"like.{year}-W%"})
    quarterly = _get("task_logs", {"select": "*", "period_key": f"like.{year}-Q%"})
    return monthly + weekly + quarterly

def select_recent_logs(limit: int = 20) -> list[dict]:
    return _get("task_logs", {"select": "*", "order": "logged_at.desc", "limit": str(limit)})

def find_log(task_id: int, period_key: str) -> dict | None:
    rows = _get("task_logs", {
        "select": "id",
        "task_id": f"eq.{task_id}",
        "period_key": f"eq.{period_key}",
    })
    return rows[0] if rows else None

def insert_log(task_id: int, period_key: str, status: str, memo: str) -> list[dict]:
    return _post("task_logs", {"task_id": task_id, "period_key": period_key, "status": status, "memo": memo})

def update_log(log_id: int, status: str, memo: str) -> list[dict]:
    return _patch("task_logs", {"id": f"eq.{log_id}"}, {"status": status, "memo": memo})

def delete_log(log_id: int) -> None:
    _delete("task_logs", {"id": f"eq.{log_id}"})

def delete_all_logs() -> None:
    _delete("task_logs", {"id": "gte.0"})

def delete_all_logs_for_task(task_id: int) -> None:
    _delete("task_logs", {"task_id": f"eq.{task_id}"})

def insert_task(data: dict) -> dict:
    rows = _post("tasks", data)
    return rows[0] if rows else {}

def delete_task(task_id: int) -> None:
    _delete("tasks", {"id": f"eq.{task_id}"})

# contracts
def select_contracts() -> list[dict]:
    return _get("contracts", {"select": "*", "order": "계약기간종료일.asc"})

def insert_contract(data: dict) -> dict:
    rows = _post("contracts", data)
    return rows[0] if rows else {}

def update_contract(contract_id: int, data: dict) -> dict:
    rows = _patch("contracts", {"id": f"eq.{contract_id}"}, data)
    return rows[0] if rows else {}

def delete_contract(contract_id: int) -> None:
    _delete("contracts", {"id": f"eq.{contract_id}"})
