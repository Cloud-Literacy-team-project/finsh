# Keep existing Terraform addresses for the retained network resources.
resource "ncloud_vpc" "lab" {
  name            = "${var.name_prefix}-vpc"
  ipv4_cidr_block = var.vpc_cidr
}

resource "ncloud_subnet" "public_kr1" {
  name           = "${var.name_prefix}-sub"
  vpc_no         = ncloud_vpc.lab.id
  subnet         = var.subnet_cidr
  zone           = var.zone_kr1
  network_acl_no = ncloud_vpc.lab.default_network_acl_no
  subnet_type    = "PUBLIC"
  usage_type     = "GEN"
}
