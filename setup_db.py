#!/usr/bin/env python3
"""
SCM 캘린더 DB 설정 스크립트
엑셀 데이터를 읽어 Supabase에 삽입합니다.
"""
import os, sys
import pandas as pd
import httpx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def check_tables():
    """tasks 테이블 존재 여부 확인"""
    from supabase_client import ping
    try:
        return ping()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return False
        raise
    except Exception:
        return False

def show_schema_instructions():
    import webbrowser
    schema_path = os.path.join(BASE_DIR, "schema.sql")
    print("\n" + "=" * 65)
    print("  [1단계] Supabase SQL Editor에서 테이블을 생성해야 합니다.")
    print("=" * 65)
    try:
        with open(schema_path, encoding="utf-8") as f:
            sql = f.read()
    except FileNotFoundError:
        sql = ""
    url = "https://supabase.com/dashboard/project/yurasobkmfyoraabtyjg/sql/new"
    print(f"\n  브라우저가 열립니다: {url}")
    print("\n  아래 SQL을 복사하여 SQL Editor에 붙여넣고 [Run] 버튼을 클릭하세요:\n")
    print("-" * 65)
    print(sql)
    print("-" * 65)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    input("\n  SQL 실행 완료 후 Enter를 누르세요... ")

def load_excel_data():
    files = {
        "SCM쉐어드파트": (os.path.join(BASE_DIR, "SCM쉐어드파트.xlsx"), "쉐어드파트"),
        "수출입파트": (os.path.join(BASE_DIR, "수출입파트.xlsx"), "수출입파트"),
    }

    tasks = []
    for part, (path, sheet) in files.items():
        print(f"  읽는 중: {os.path.basename(path)}")
        df = pd.read_excel(path, sheet_name=sheet)
        df.columns = [str(c).strip() for c in df.columns]

        for _, row in df.iterrows():
            def v(col):
                val = row.get(col)
                if val is None:
                    return None
                try:
                    import math
                    if isinstance(val, float) and math.isnan(val):
                        return None
                except Exception:
                    pass
                s = str(val).strip()
                return None if s in ("", "nan", "NaN", "None") else s

            task_name = v("업무")
            if not task_name:
                continue

            tasks.append({
                "파트": part,
                "주기": v("주기"),
                "구분": v("구분"),
                "업무": task_name,
                "주인": v("주인(담당)"),
                "시기_마감": v("시기/마감"),
                "output": v("Output"),
                "비고": v("비고"),
            })

    return tasks

def insert_tasks(tasks):
    from supabase_client import delete_all_logs, delete_all_tasks, insert_tasks as db_insert
    try:
        delete_all_logs()
        delete_all_tasks()
        print("  기존 데이터 삭제 완료")
    except Exception as e:
        print(f"  기존 데이터 삭제 건너뜀: {e}")

    batch = 20
    for i in range(0, len(tasks), batch):
        chunk = tasks[i: i + batch]
        db_insert(chunk)
        print(f"  {min(i + batch, len(tasks))}/{len(tasks)} 행 삽입...")

    print(f"\n  완료: {len(tasks)}개 업무 데이터 삽입")

def main():
    print("\n" + "=" * 50)
    print("  SCM 통합 캘린더 - DB 설정")
    print("=" * 50)

    if not check_tables():
        show_schema_instructions()
        if not check_tables():
            print("\n  테이블 생성 확인 실패. setup_db.py를 다시 실행하세요.")
            sys.exit(1)

    print("\n  테이블 확인 완료")

    print("\n  엑셀 파일 읽는 중...")
    tasks = load_excel_data()
    print(f"  {len(tasks)}개 업무 로드")

    print("\n  Supabase에 데이터 삽입 중...")
    insert_tasks(tasks)

    print("\n" + "=" * 50)
    print("  설정 완료! 서버를 시작하세요:")
    print("    uvicorn main:app --reload")
    print("=" * 50 + "\n")

if __name__ == "__main__":
    main()
