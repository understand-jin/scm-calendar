-- SCM 통합 캘린더 데이터베이스 스키마

-- 업무 테이블
CREATE TABLE IF NOT EXISTS tasks (
    id BIGSERIAL PRIMARY KEY,
    파트 TEXT NOT NULL,
    -- 파트에 따라 자동 계산되는 소속 팀 (위탁파트/수탁파트 → 위수탁사업팀, 그 외 → SCM팀)
    팀 TEXT GENERATED ALWAYS AS (
        CASE WHEN 파트 IN ('위탁파트', '수탁파트') THEN '위수탁사업팀' ELSE 'SCM팀' END
    ) STORED,
    주기 TEXT,
    구분 TEXT,
    업무 TEXT NOT NULL,
    주인 TEXT,
    시기_마감 TEXT,
    output TEXT,
    비고 TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 업무 로그 테이블 (완료 이력)
CREATE TABLE IF NOT EXISTS task_logs (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    period_key TEXT NOT NULL,
    status TEXT DEFAULT 'done',
    memo TEXT,
    logged_at TIMESTAMPTZ DEFAULT NOW()
);

-- 산출물 테이블
CREATE TABLE IF NOT EXISTS outputs (
    id BIGSERIAL PRIMARY KEY,
    task_id BIGINT NOT NULL,
    output_name TEXT,
    file_url TEXT,
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS 활성화 및 공개 정책 설정
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE task_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE outputs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tasks_all" ON tasks FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "task_logs_all" ON task_logs FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "outputs_all" ON outputs FOR ALL USING (true) WITH CHECK (true);
