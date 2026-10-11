# NCP backend options: https://github.com/NaverCloudPlatform/terraform-provider-ncloud/blob/main/docs/guides/Configure%20Remote%20State%20Backend%20for%20Ncloud.md
terraform {
  backend "s3" {
    bucket = "finsh-tfstate-1com4soft"
    key    = "core/terraform.tfstate"
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

    # Run ./load-env.ps1 to set Provider and Backend credentials in this terminal.
    # Use NCP Object Storage credentials; never store them in this backend block.
  }
}
