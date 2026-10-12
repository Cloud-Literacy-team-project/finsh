# finsh core Terraform

작업 브랜치는 `features/infra`입니다. `feat/d-terraform-core`는 사용하지 않습니다.
Terraform 1.10 이상과 lock 파일의 NCP Provider 4.0.7을 사용합니다. 검증 CLI는 1.16.2입니다.

## 구성과 범위

| 자원 | 이름/설정 |
|---|---|
| VPC | `finsh-vpc`, `10.0.0.0/16` |
| Subnet | `finsh-sub`, `10.0.1.0/24`, PUBLIC/GEN, KR-1 |
| Bastion ACG | `finsh-acg-bastion`, 팀원 공인 IPv4 /32에서 TCP 22만 인바운드 허용 |
| DB ACG | `finsh-acg-db`, Bastion ACG에서 TCP 22 및 3306만 인바운드 허용 |
| 로그인 키 | `finsh-key`, 두 서버가 공통 사용 |
| NIC | `finsh-bastion-nic`, `finsh-db-nic`, 각각 지정한 ACG만 연결 |
| 서버 | `finsh-bastion`, `finsh-db`, 같은 KR-1 Public Subnet |
| 공인 IP | 서버별 1개, `server_instance_no`로 연결; 이 Provider에는 `name` 인자가 없음 |

두 ACG 모두 TCP/UDP 1-65535 아웃바운드를 허용합니다. DB 공인 IP는 이후 패키지 설치를 위한 것이며, 인터넷이나 팀원 공인 IP에서 DB로 직접 들어오는 인바운드 규칙은 없습니다. ACG 규칙 생성 후 NIC가 생성되고, 그 NIC를 서버의 기본 인터페이스(order 0)로 연결합니다.

Resource 블록은 13개입니다. 실제 Plan의 생성/변경/삭제 개수는 기존 State에 따라 다릅니다. MySQL 설치, OS 사용자 생성, 팀원 SSH 공개키 등록, Init Script, provisioner, LB, NAT Gateway, 추가 디스크는 포함하지 않습니다.

## 이미지와 사양 확인

2026-10-09 프로젝트 인증으로 읽기 전용 NCP API를 조회한 결과:

- `104630229`: `ubuntu-24.04-base`, 서비스 중인 Ubuntu 24.04 x86_64 KVM 이미지.
- 해당 이미지와 `zoneCode=KR-1`을 지정한 `getServerSpecList`에 `c2-g3a`가 포함됨.
- `c2-g3a` 상세: G3/KVM/x86_64, 2 vCPU, 4 GiB RAM, NIC 최대 3개.
- Micro를 제외한 조회 사양의 최소 메모리/CPU 범주에서 `c2-g3a`를 선택함. Micro는 계정당 1대 제한이 있어 동일 사양 서버 2개 구성에 사용하지 않음.

이 조회는 생성 성공이나 남은 계정 할당량을 보장하지 않습니다. Apply 직전에 재확인하세요. NCP CLI가 설치되고 프로젝트 인증이 구성된 PowerShell에서는 다음 읽기 전용 명령을 사용할 수 있습니다.

```powershell
ncloud vserver getServerImageList --regionCode KR --output json
ncloud vserver getServerSpecList --regionCode KR --zoneCode KR-1 --serverImageNo 104630229 --output json
ncloud vserver getServerSpecDetail --regionCode KR --serverSpecCode c2-g3a --output json
```

이미지 이름/OS/아키텍처/하이퍼바이저와 이미지에 맞는 KR-1 사양을 함께 확인한 뒤 `server_image_number`, `server_spec_code`를 수정합니다. 확인할 수 없다면 다른 값을 추측해서 넣지 마세요.

공식 근거: [서버 Provider 4.0.7](https://github.com/NaverCloudPlatform/terraform-provider-ncloud/blob/v4.0.7/docs/resources/server.md), [KR-1·이미지별 사양 조회](https://api.ncloud-docs.com/docs/compute-vserver-server-common-getserverspeclist), [서버 종류와 제한](https://guide.ncloud-docs.com/docs/server-spec-vpc).

## 기존 자원과 State

Backend의 기존 버킷 `finsh-tfstate-1com4soft`, key `core/terraform.tfstate`, `kr-standard` 리전과 한국 엔드포인트를 유지합니다. 이 구성은 버킷을 생성하지 않습니다.

기존 주소 `ncloud_vpc.lab`, `ncloud_subnet.public_kr1`, `ncloud_access_control_group.bastion`, `ncloud_access_control_group.db`를 유지했습니다. 주소를 옮기지 않았으므로 `moved` 블록은 필요하지 않습니다.

이전 코드와 비교하면 VPC·Subnet CIDR이 `10.20.*`에서 `10.0.*`로 바뀌고 자원 이름의 `core` 부분이 제거됩니다. 기존 State에 배포 이력이 있으면 CIDR 변경에 따른 VPC/Subnet 교체와 연결 자원의 교체가 발생할 수 있습니다. 제외한 Subnet 4개(`nat_kr2`, `lb_kr1`, `private_kr1`, `private_kr2`)와 ACG 2개(`web`, `backend`)가 해당 State에 있으면 삭제 대상이 될 수 있습니다. Plan의 교체·삭제 대상과 이유를 반드시 확인하세요.

`finsh-test-d-*`나 다른 팀원의 자원은 수정·Import·삭제하지 않습니다. 같은 이름의 `finsh-vpc`, `finsh-sub`, 두 ACG/NIC/서버, `finsh-key`가 State 밖에 이미 있으면 Apply하지 말고 충돌을 먼저 확인하세요. 2026-10-09 읽기 전용 조회에서는 이 목표 이름과 같은 자원을 찾지 못했지만, Apply 전에 다시 확인해야 합니다.

기존 `use_lockfile = true`를 유지했습니다. NCP 공식 Backend 안내에서 조건부 쓰기와 S3 잠금 지원을 확인했습니다. 저장소 Backend를 임의로 변경하거나 State를 이동/삭제하지 마세요. 잠금을 사용할 수 없어 끄게 되는 경우에는 팀에서 동시에 Apply하지 않도록 해야 합니다. 검증 목적의 `-lock=false`를 일반 Apply에 사용하지 마세요.

근거: [NCP Backend 안내](https://github.com/NaverCloudPlatform/terraform-provider-ncloud/blob/v4.0.7/docs/guides/Configure%20Remote%20State%20Backend%20for%20Ncloud.md), [Terraform S3 Backend](https://developer.hashicorp.com/terraform/language/backend/s3).

## PowerShell 실행 순서

저장소 루트 `finsh`에서 시작합니다. 모든 명령은 같은 PowerShell 터미널에서 실행하세요.

### 1. 입력값 준비

```powershell
Set-Location .\infra\core
if (-not (Test-Path -LiteralPath .\terraform.tfvars)) {
    Copy-Item -LiteralPath .\terraform.tfvars.example -Destination .\terraform.tfvars
}
notepad .\terraform.tfvars
```

`team_ips = []`로 두면 Bastion 인바운드 규칙이 0개인 상태로 서버 생성을 진행할 수 있습니다. 외부 SSH 접속은 차단되며, DB는 Bastion ACG 출발지만 허용합니다. 나중에 실제 팀원 공인 IPv4 /32 목록을 넣고 Plan을 확인한 뒤 다시 Apply하면 해당 IP에서 Bastion으로 SSH 접속할 수 있습니다. 목록을 다시 비우면 관리 중인 Bastion 인바운드 규칙도 제거됩니다. `203.0.113.10/32`는 문서용 주소이며 실제 접속에 사용하지 않습니다. 잘못된 CIDR, IPv6, /32 이외의 입력과 `0.0.0.0/0`은 계속 거부합니다. 인증키를 tfvars에 넣지 마세요.

### 2. Provider와 Backend 인증

```powershell
.\load-env.ps1
```

Terraform 자체는 `.env`를 자동으로 읽지 않습니다. 이 스크립트는 저장소 루트 `.env`의 두 키만 읽고 현재 PowerShell 프로세스에 다음과 같이 설정합니다. 비밀값을 출력하거나 파일로 복사하지 않습니다.

| 인증 목적 | 환경 변수 |
|---|---|
| NCP Provider | `NCLOUD_ACCESS_KEY`, `NCLOUD_SECRET_KEY` |
| Object Storage Backend | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` |

기본적으로 같은 NCP 키를 두 인증에 사용하므로 해당 키에 Provider 작업 권한과 Object Storage 접근 권한이 모두 필요합니다. 별도 Backend 키를 사용하는 경우 로더 실행 후 `AWS_*` 환경변수만 별도 보안 수단으로 설정하세요. Backend에 Access Key/Secret Key를 적지 않습니다. 인증 정보를 Terraform 입력 변수로 받지 않으며, 추후 그런 변수를 추가하면 `sensitive = true`로 선언해야 합니다.

### 3~6. 초기화, 형식, 검증, Plan

```powershell
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=core.tfplan
```

잠금 오류나 Backend 접근 오류가 발생하면 State를 지우거나 다른 key로 우회하지 마세요. `terraform validate`의 성공은 API 권한·서버 가용성·실제 배포 성공을 의미하지 않습니다. Plan 파일에도 민감 정보가 담길 수 있으므로 Git에 올리지 않습니다.

### 7~8. 사용자가 Plan 검토 후 Apply와 Output 확인

```powershell
terraform show core.tfplan
# 교체/삭제와 이름 충돌을 검토한 뒤에만 직접 실행합니다.
terraform apply core.tfplan
terraform output
```

일반 `terraform output`에서 private key는 숨겨집니다. SSH용 OS 계정이나 공개키 등록은 이번 코드가 수행하지 않습니다. NCP 로그인 키는 관리자 비밀번호 복호화용 키이며, 이것만으로 OS SSH 공개키 등록이 완료된 것은 아닙니다.

### 9. 로그인 private key를 BOM 없는 PEM으로 저장

Windows PowerShell 5.1과 PowerShell 7의 리다이렉션 기본 인코딩 차이를 피하기 위해 `>` 또는 기본 `Out-File`을 사용하지 않습니다.

```powershell
& {
    $keyLines = terraform output -raw login_private_key
    if ($LASTEXITCODE -ne 0) { throw 'Could not read the login private key.' }
    $keyText = ($keyLines -join "`n").TrimEnd() + "`n"
    $keyPath = Join-Path (Get-Location) 'finsh-key.pem'
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($keyPath, $keyText, $utf8NoBom)
}
```

키를 화면에 출력하지 않고 UTF-8 BOM 없이 LF 줄바꿈으로 저장합니다. 생성된 PEM은 Git에서 제외됩니다. `sensitive` Output이어도 private key는 State에 저장되므로 비공개 버킷과 State/Plan/PEM 접근 권한을 관리해야 합니다. [로그인 키 Provider 문서](https://github.com/NaverCloudPlatform/terraform-provider-ncloud/blob/v4.0.7/docs/resources/login_key.md)

## 로컬 검증

```powershell
terraform fmt -check -recursive
terraform validate
terraform test
```

`tests/security.tftest.hcl`은 mock Provider와 Plan만 사용하며 실제 클라우드 자원을 생성하지 않습니다. 정상 팀원 목록의 인바운드 범위·DB 출발지·NIC 연결과 잘못된 입력 거부를 검증합니다. 임시 디렉터리에서 기존 Backend를 제외한 구성으로 테스트 7개가 통과했고, 원본 구성의 fmt/validate와 Git 제외 검사도 통과했습니다.

2026-10-10 요구사항을 변경하여 빈 `team_ips`도 허용합니다. 테스트에서는 빈 목록일 때 Bastion 인바운드 규칙이 0개이고 두 서버가 계속 Plan에 포함되는지 확인합니다. 실제 자원의 교체·삭제 여부는 적용 직전의 Plan에서 확인해야 합니다.
