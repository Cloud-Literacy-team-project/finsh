resource "ncloud_access_control_group" "bastion" {
  name        = "${var.name_prefix}-acg-bastion"
  description = "SSH from team public IPv4 addresses only"
  vpc_no      = ncloud_vpc.lab.id
}

resource "ncloud_access_control_group" "db" {
  name        = "${var.name_prefix}-acg-db"
  description = "SSH and MySQL ports from the Bastion ACG only"
  vpc_no      = ncloud_vpc.lab.id
}

resource "ncloud_access_control_group_rule" "bastion" {
  access_control_group_no = ncloud_access_control_group.bastion.id

  # Explicit [] also removes previously managed SSH ingress when the list is cleared.
  inbound = [for ip in toset(var.team_ips) : {
    protocol                       = "TCP"
    ip_block                       = ip
    source_access_control_group_no = null
    port_range                     = "22"
    description                    = "Team SSH"
  }]

  outbound {
    protocol    = "TCP"
    ip_block    = "0.0.0.0/0"
    port_range  = "1-65535"
    description = "Outbound TCP for package installation"
  }

  outbound {
    protocol    = "UDP"
    ip_block    = "0.0.0.0/0"
    port_range  = "1-65535"
    description = "Outbound UDP for package installation"
  }
}

resource "ncloud_access_control_group_rule" "db" {
  access_control_group_no = ncloud_access_control_group.db.id

  inbound {
    protocol                       = "TCP"
    source_access_control_group_no = ncloud_access_control_group.bastion.id
    port_range                     = "22"
    description                    = "SSH from Bastion ACG"
  }

  inbound {
    protocol                       = "TCP"
    source_access_control_group_no = ncloud_access_control_group.bastion.id
    port_range                     = "3306"
    description                    = "MySQL port from Bastion ACG"
  }

  outbound {
    protocol    = "TCP"
    ip_block    = "0.0.0.0/0"
    port_range  = "1-65535"
    description = "Outbound TCP for package installation"
  }

  outbound {
    protocol    = "UDP"
    ip_block    = "0.0.0.0/0"
    port_range  = "1-65535"
    description = "Outbound UDP for package installation"
  }
}
