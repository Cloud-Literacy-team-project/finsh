# D 구현과 통합 확인

## 보호 계약

- `terraform_nos()`는 Object Storage에서 core와 test 기록을 메모리로 읽어 관리 중인 서버·공인 IP·추가 블록 스토리지 번호만 반환한다. 원본 기록을 출력하거나 저장하지 않는다.
- core 기록은 필수다. 아직 만들어지지 않은 test key의 `NoSuchKey`만 허용한다. 접근 거부·JSON 오류·번호 누락은 모두 판정 불가이며 삭제를 차단한다.
- `FINSH_TFSTATE_BUCKET` 또는 settings.yaml의 `tfstate_bucket`을 사용한다. 조회 키는 FINSH_SCANNER 키가 있으면 그 쌍을, 없으면 NCLOUD 키 쌍을 사용한다.
- 사람 보호는 `protect_days`일(기본 30일)이며 갱신할 수 있다. Terraform 보호는 영구이고 사람이 덮어쓰거나 해제할 수 없다.
- 정상적으로 확인한 전체 Terraform 번호를 트랜잭션으로 동기화한다. 확인된 빈 집합과 조회 실패를 구분한다. 동기화 실패 시 정리 후보를 UNKNOWN으로 보류한다.

## 실제 통합 점검

1. `FINSH_DRY_RUN=1`, `FINSH_SOURCE=db`로 실제 API와 DB를 사용한다.
2. `python -m jobs.run_scan` 후 `top`, `stat`, `lsattr`를 확인한다.
3. C 소유의 분리된 테스트 자원에 `chattr +i`, `chattr -i`, `kill`, `trash-restore`를 실행하고 테스트 전 상태로 되돌린다.
4. core 자원은 Terraform 영구 보호이고 `chattr -i`와 `kill`이 거부돼야 한다.
5. `python -m jobs.run_watch`, `python -m jobs.run_purge`로 자동 작업 진입점을 확인한다. 실제 삭제는 FINSH_DRY_RUN=1에서 보내지 않는다.

## Bastion 배포

로컬 변경을 Git에 반영하는 작업은 사용자 담당이다. 배포할 코드와 requirements.txt를 `/opt/finsh`에 설치하고 `.venv`를 만든다.
로컬 PC의 `.env`를 그대로 쓰지 않는다. Bastion에서 DB는 `FINSH_DB_HOST=10.0.1.6`, `FINSH_DB_PORT=3306`으로 직접 연결한다.
`FINSH_SOURCE=db`, `FINSH_DRY_RUN=1`, Object Storage 읽기 권한이 있는 키를 설정한다.
`.env`는 finsh 소유, 권한 600으로 두고 인증값은 문서나 Git에 적지 않는다.

세 자동 작업을 손으로 확인한 뒤 관리자 터미널에서 다음을 실행한다:

```bash
sudo bash /opt/finsh/infra/bastion/install.sh
```

설치 스크립트는 DB와 Terraform 읽기 및 연습 모드를 확인한 뒤 `/usr/local/bin/finsh`와 `/etc/cron.d/finsh`를 설치한다.
scan은 30분, watch는 5분, purge는 10분마다 실행한다. 로그는 `/var/log/finsh`에 남는다.
시연 주기를 짧게 변경할 때는 cron 파일과 관측 공백 기준도 함께 확인한다.

## Terraform 시연

`infra/test`는 VPC 한도를 고려해 기존 core 네트워크를 재사용한다.
`test/terraform.tfstate`에만 기록하며 apply는 비용·plan 확인 후 진행한다.
Terraform 파일을 구현한 것과 실제 시연 서버를 생성한 것은 별개다.

## 2026-10-13 확인 결과

- Object Storage의 core 기록에서 서버 2개·공인 IP 2개의 번호를 확인했다. 아직 없는 test 기록은 정상적으로 건너뛰었다.
- 실제 스캔이 공유 DB에 자원 36개를 저장했고, 정리 후보 12개와 Terraform 영구 보호 4개를 확인했다.
- `finsh-test-c-blk`로 top/stat, 사람 보호·해제, 휴지통 이동·복원, 연습 모드 즉시 삭제를 확인했다. 테스트 후 보호·휴지통 상태를 되돌렸다. 감사 기록은 남는다.
- finsh-bastion의 보호 해제·삭제가 거부됐다. watch/purge 진입점도 연습 모드에서 실행했다. 이때 활성 휴지통 항목이 0개였으므로 실제 재사용·삭제 대기 동작은 자동 테스트로 검증했다.
- 전체 Python 테스트 99개 통과. Terraform fmt/validate 통과. plan은 4 add, 0 change, 0 destroy였다.
- 승인 후 Terraform apply를 실행해 ACG·규칙·NIC·시연 서버 4개를 생성했다(변경·삭제 0개). `finsh-test-tf-web`의 번호는 `146305727`이고 공인 IP가 없다. 생성 후 정지 완료(`NSTOP`)를 확인했다.
- Bastion `/opt/finsh`에 코드·Python 가상환경을 배포했다. C 계정 키는 임시 사용이며 `.env`는 finsh 소유·권한 600이다. DB는 `10.0.1.6:3306`, 실제 DB 모드, 연습 모드를 사용한다. 삭제 전용 키는 배포하지 않았다.
- Bastion에서 전체 테스트 99개 통과. 테스트 중 출력되는 오류 사례는 모의 실패 테스트이며 실제 실행 결과와 구분한다. 실제 scan은 38개 자원과 12개 후보를 확인했고, watch/purge는 활성 휴지통 0개로 오류 없이 완료했다.
- Terraform 영구 보호는 core 4개와 시연 서버 1개, 총 5개다. 실제 셸의 top·stat·lsattr와 시연 서버 kill 거부·보호 해제 거부를 확인했다.
- 시스템 명령·cron 등록은 사용자 sudo 실행이 남아 있다: `sudo bash /opt/finsh/infra/bastion/install.sh`. 이 명령 실행 전까지 자동 실행이 설치됐다고 보고하지 않는다. 설치 후 cron 서비스와 세 작업 로그를 확인한다.
- DB backup과 마이그레이션은 앞 단계에서 완료됐으며 추가 DB 컬럼 변경은 필요 없다.
