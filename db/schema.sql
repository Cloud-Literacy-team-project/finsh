-- finsh DB 표 5개.  적용: python -m db.init
-- 여러 번 실행해도 안전 (IF NOT EXISTS)

-- 1. 자원: B의 run_scan()이 30분마다 덮어씀
CREATE TABLE IF NOT EXISTS resources (
    ncp_no          VARCHAR(32)  NOT NULL PRIMARY KEY,   -- 네이버 자원 번호
    id              VARCHAR(16)  NOT NULL UNIQUE,        -- 짧은 ID (srv-1a2b)
    type            VARCHAR(16)  NOT NULL,               -- server / publicip / blockstorage
    name            VARCHAR(255) NOT NULL DEFAULT '',
    state           VARCHAR(32)  NOT NULL,               -- RUNNING / STOPPED / ATTACHED / DETACHED
    grade           VARCHAR(16)  NOT NULL DEFAULT 'OK',  -- ORPHAN / ZOMBIE / IDLE (top) · WAITING / UNKNOWN / OK (DB만)
    reason          VARCHAR(255) NULL,                   -- 판정 이유 (예: CPU 조회 실패, 정지 관측 3.2일)
    idle_days       DECIMAL(8,2) NOT NULL DEFAULT 0,
    cost_hourly     DECIMAL(10,2) NULL,                  -- 단가 미확인이면 NULL
    cost_total      DECIMAL(12,2) NULL,                  -- 금액 미확인이면 NULL
    cost_yesterday  DECIMAL(12,2) NULL,
    creator         VARCHAR(64)  NULL,
    created_at      DATETIME     NULL,
    vpc             VARCHAR(64)  NULL,
    console_path    VARCHAR(64)  NOT NULL DEFAULT '',
    terraform       TINYINT(1)   NOT NULL DEFAULT 0,
    detail          JSON         NULL,
    state_since     DATETIME     NULL,   -- 지금 상태를 처음 관측한 시각 (정지 서버면 first_seen_stopped_at)
    first_seen      DATETIME     NOT NULL,
    last_seen       DATETIME     NOT NULL,
    gone            TINYINT(1)   NOT NULL DEFAULT 0   -- 콘솔에서 사라졌으면 1
);

-- 2. 휴지통: C의 trash.py
CREATE TABLE IF NOT EXISTS trash (
    no           INT AUTO_INCREMENT PRIMARY KEY,
    ncp_no       VARCHAR(32) NOT NULL,
    id           VARCHAR(16) NOT NULL,
    name         VARCHAR(255) NOT NULL DEFAULT '',
    type         VARCHAR(16) NOT NULL,
    put_at       DATETIME    NOT NULL,
    due_at       DATETIME    NOT NULL,                    -- 이 시각이 지나면 영구 삭제
    delete_requested_at DATETIME NULL,                    -- NCP 삭제 요청을 보냈을 수 있는 시각
    status       VARCHAR(16) NOT NULL DEFAULT 'WAITING',  -- WAITING / DELETE_REQUESTED / HELD / RESTORED / PURGED / FAILED
    hold_reason  VARCHAR(255) NULL,
    snapshot     JSON        NULL,                        -- 넣을 때의 상태 (변화 감지용)
    notified     TINYINT(1)  NOT NULL DEFAULT 0,          -- 하루 전 알림 보냈으면 1
    tries        INT         NOT NULL DEFAULT 0,          -- 삭제 실패 횟수 (3번이면 FAILED)
    INDEX (ncp_no), INDEX (status)
);

-- 3. 보호: D의 protect.py (chattr +i, Terraform 자동 보호)
CREATE TABLE IF NOT EXISTS protections (
    ncp_no      VARCHAR(32)  NOT NULL PRIMARY KEY,
    reason      VARCHAR(255) NOT NULL DEFAULT '',
    source      VARCHAR(16)  NOT NULL DEFAULT 'user',  -- user / terraform
    until       DATETIME     NULL,                     -- terraform이면 NULL (영구)
    created_at  DATETIME     NOT NULL
);

-- 4. 기록: last 명령어
CREATE TABLE IF NOT EXISTS events (
    no       INT AUTO_INCREMENT PRIMARY KEY,
    at       DATETIME     NOT NULL,
    action   VARCHAR(32)  NOT NULL,   -- kill / kill-9 / restore / hold / purge / protect / unprotect / scan
    ncp_no   VARCHAR(32)  NULL,
    id       VARCHAR(16)  NULL,
    name     VARCHAR(255) NULL,
    result   VARCHAR(16)  NOT NULL DEFAULT 'OK',  -- OK / FAIL / DRYRUN
    message  VARCHAR(500) NULL,
    INDEX (at)
);

-- 5. 알림: 셸 시작할 때 "새 알림 N건"
CREATE TABLE IF NOT EXISTS alerts (
    no       INT AUTO_INCREMENT PRIMARY KEY,
    at       DATETIME     NOT NULL,
    level    VARCHAR(8)   NOT NULL DEFAULT 'INFO',  -- INFO / WARN
    message  VARCHAR(500) NOT NULL,
    seen     TINYINT(1)   NOT NULL DEFAULT 0
);
