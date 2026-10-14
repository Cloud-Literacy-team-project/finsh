# Terraform 보호 시연용 서버

기존 core VPC와 서브넷을 재사용한다. 새 VPC·공인 IP는 만들지 않는다.
시연 자원은 ACG, ACG 규칙, NIC, `finsh-test-tf-web` 서버 총 4개다.
상태 저장 key는 반드시 `test/terraform.tfstate`이며 core key를 사용하지 않는다.

PowerShell에서 실행:

```powershell
cd infra/test
../core/load-env.ps1
Copy-Item terraform.tfvars.example terraform.tfvars
# terraform.tfvars의 vpc_no/subnet_no를 기존 core 번호로 채운다.
terraform init
terraform fmt -check
terraform validate
terraform plan
# 생성 비용과 4개 신규 자원을 확인한 다음에만 terraform apply를 실행한다.
```

plan에 기존 core 자원의 변경·삭제가 있으면 적용하지 않는다.
apply 후 서버를 콘솔에서 정지하고 `terraform_nos()`에 서버 번호가 포함되는지 확인한다.
스캔 후 `lsattr`에서 영구 보호를 확인하며 `kill`과 `chattr -i`가 거부돼야 한다.
정리할 때는 이 폴더의 Terraform으로 삭제한다.

원본 tfstate, tfvars, plan, 인증키는 Git에 올리지 않는다.
Provider 공식 문서: https://registry.terraform.io/providers/NaverCloudPlatform/ncloud/latest/docs/resources/server
