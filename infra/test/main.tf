# Reuse the core network: the account already reached its VPC quota.
variable "region" {
  type    = string
  default = "KR"
}

variable "vpc_no" {
  type        = string
  description = "Existing core VPC number (terraform -chdir=../core output -raw vpc_id)."
  validation {
    condition     = can(regex("^[0-9]+$", var.vpc_no))
    error_message = "vpc_no must be an existing numeric VPC ID."
  }
}

variable "subnet_no" {
  type        = string
  description = "Existing core subnet number (terraform -chdir=../core output -raw subnet_id)."
  validation {
    condition     = can(regex("^[0-9]+$", var.subnet_no))
    error_message = "subnet_no must be an existing numeric subnet ID."
  }
}

variable "login_key_name" {
  type        = string
  default     = "finsh-key"
  description = "Existing NCP login key name; no key contents are stored in this configuration."
}

variable "server_image_number" {
  type    = string
  default = "104630229"
}

variable "server_spec_code" {
  type    = string
  default = "s2-g3a"
}

resource "ncloud_access_control_group" "test" {
  name        = "finsh-test-tf-acg"
  description = "Terraform protection demo; no inbound SSH required"
  vpc_no      = var.vpc_no
}

resource "ncloud_access_control_group_rule" "test" {
  access_control_group_no = ncloud_access_control_group.test.id
  inbound                 = []
  outbound {
    protocol   = "TCP"
    ip_block   = "0.0.0.0/0"
    port_range = "1-65535"
  }
  outbound {
    protocol   = "UDP"
    ip_block   = "0.0.0.0/0"
    port_range = "1-65535"
  }
}

resource "ncloud_network_interface" "test" {
  name                  = "finsh-test-tf-nic"
  subnet_no             = var.subnet_no
  access_control_groups = [ncloud_access_control_group.test.id]
  depends_on            = [ncloud_access_control_group_rule.test]
}

resource "ncloud_server" "web" {
  name                = "finsh-test-tf-web"
  subnet_no           = var.subnet_no
  zone                = "KR-1"
  server_image_number = var.server_image_number
  server_spec_code    = var.server_spec_code
  login_key_name      = var.login_key_name
  network_interface {
    network_interface_no = ncloud_network_interface.test.id
    order                = 0
  }
}

output "web_server_no" {
  value       = ncloud_server.web.id
  description = "This resource must be rejected by finsh kill and chattr -i."
}
