# Keep test state separate from core; credentials are supplied in the terminal.
terraform {
  backend "s3" {
    bucket = "finsh-tfstate-1com4soft"
    key    = "test/terraform.tfstate"
    region = "kr-standard"
    endpoints = {
      s3 = "https://kr.object.ncloudstorage.com"
    }
    use_path_style              = true
    skip_region_validation      = true
    skip_requesting_account_id  = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    use_lockfile                = true
  }
}
