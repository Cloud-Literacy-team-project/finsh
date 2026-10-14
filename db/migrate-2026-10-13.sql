-- 기존 finsh DB에 한 번 적용한다. 새 설치는 db/schema.sql에 이미 반영돼 있다.
-- 배포 전에 팀장과 함께 백업·적용 순서를 확인한다.

ALTER TABLE resources
    MODIFY COLUMN cost_hourly DECIMAL(10,2) NULL DEFAULT NULL,
    MODIFY COLUMN cost_total DECIMAL(12,2) NULL DEFAULT NULL;

SELECT COUNT(*) INTO @finsh_has_delete_requested_at
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'trash'
  AND COLUMN_NAME = 'delete_requested_at';

SET @finsh_migration_sql = IF(
    @finsh_has_delete_requested_at = 0,
    'ALTER TABLE trash ADD COLUMN delete_requested_at DATETIME NULL AFTER due_at',
    'SELECT 1'
);
PREPARE finsh_migration FROM @finsh_migration_sql;
EXECUTE finsh_migration;
DEALLOCATE PREPARE finsh_migration;
