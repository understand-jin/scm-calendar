-- 기존에 이미 생성된 Supabase tasks 테이블에 '팀' 컬럼을 추가하는 마이그레이션
-- Supabase 대시보드 > SQL Editor 에서 아래 SQL을 그대로 실행하세요.
-- (1회만 실행하면 됩니다. 이후 파트가 위탁파트/수탁파트인 행은 위수탁사업팀,
--  나머지는 SCM팀으로 항상 자동 계산되어 별도 관리가 필요 없습니다.)

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS 팀 TEXT GENERATED ALWAYS AS (
    CASE WHEN 파트 IN ('위탁파트', '수탁파트') THEN '위수탁사업팀' ELSE 'SCM팀' END
) STORED;
