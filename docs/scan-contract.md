# `run_scan()` 연결 약속

`engine.scan.run_scan()`은 DB 기능이 비어 있으면 시작하지 않는다. 실제 스캔을 켜기 전에 아래 함수가 필요하다.

## DB (`db/database.py`)

- `get_known() -> dict[str, dict]`: NCP 자원 번호를 키로 하고, 각 값에 정규화된 `state`, `state_since`, `last_seen`을 담는다. 시각은 KST `datetime` 또는 ISO 문자열이다.
- `save_resources(resources, failed)`: 이번에 읽은 **모든** 자원을 판정이 `OK`·`WAITING`·`UNKNOWN`이어도 갱신한다. `failed`에 들어 있는 자원 종류의 기존 DB 행은 삭제하거나 후보로 남기지 말고 `UNKNOWN`(목록 조회 실패)으로 바꾼다. 정상 조회한 종류에서 사라진 자원도 이전 후보가 `top`에 남지 않도록 처리한다.
- `log("scan", result="OK" | "FAIL", message=...)`: 스캔 요약을 기록한다.

`resources`의 각 행에는 `id`, `ncp_no`, `type`, `name`, `state`, `state_since`, `last_seen`, `grade`, `reason`, `cost_hourly`, `cost_total`, `terraform` 등이 들어 있다. `terraform=None`은 Terraform 기록 확인 실패를 뜻하므로 비보호로 취급하면 안 된다.

## CPU (`ncp/insight.py`)

`cpu_stats_many(server_nos, days=...)`는 NCP 번호별 dict를 반환한다. 7일 이상 실행 상태로 **연속 관측**된 서버에만 호출한다. 각 서버의 값에는 `cpu_avg`, `cpu_sample_count`, `cpu_expected_count`, `cpu_max_missing`, `cpu_window_start`, `cpu_window_end`, `cpu_last_at`, `cpu_interval_minutes`, `cpu_error`가 필요하다. 시각은 `datetime` 또는 ISO 문자열이다. 조회 실패나 필드 부족 시 `judge()`는 `IDLE` 대신 `UNKNOWN`으로 둔다.

## Terraform (`engine/iac.py`, `engine/protect.py`)

`terraform_nos() -> set[str]`로 Terraform 자원 번호를 읽는다. 읽기에 실패하면 스캔은 계속하지만 `terraform=None`으로 저장한다. `sync_terraform(nos)`는 확인된 번호를 보호 목록에 동기화한다. 삭제 전에는 C의 안전장치가 Terraform·보호 여부를 다시 확인해야 한다.
