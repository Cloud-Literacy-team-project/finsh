provider "ncloud" {
  support_vpc = true
  region      = var.region
  # Credentials come from NCLOUD_ACCESS_KEY and NCLOUD_SECRET_KEY.
  # No credential input variables or literal keys are used.
}
