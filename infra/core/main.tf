resource "ncloud_login_key" "lab" {
  key_name = "${var.name_prefix}-key"
}

resource "ncloud_network_interface" "bastion" {
  name                  = "${var.name_prefix}-bastion-nic"
  subnet_no             = ncloud_subnet.public_kr1.id
  access_control_groups = [ncloud_access_control_group.bastion.id]

  # Install the intended firewall rules before a server can use this NIC.
  depends_on = [ncloud_access_control_group_rule.bastion]
}

resource "ncloud_network_interface" "db" {
  name                  = "${var.name_prefix}-db-nic"
  subnet_no             = ncloud_subnet.public_kr1.id
  access_control_groups = [ncloud_access_control_group.db.id]

  depends_on = [ncloud_access_control_group_rule.db]
}

resource "ncloud_server" "bastion" {
  name                = "${var.name_prefix}-bastion"
  subnet_no           = ncloud_subnet.public_kr1.id
  zone                = var.zone_kr1
  server_image_number = var.server_image_number
  server_spec_code    = var.server_spec_code
  login_key_name      = ncloud_login_key.lab.key_name

  network_interface {
    network_interface_no = ncloud_network_interface.bastion.id
    order                = 0
  }
}

resource "ncloud_server" "db" {
  name                = "${var.name_prefix}-db"
  subnet_no           = ncloud_subnet.public_kr1.id
  zone                = var.zone_kr1
  server_image_number = var.server_image_number
  server_spec_code    = var.server_spec_code
  login_key_name      = ncloud_login_key.lab.key_name

  network_interface {
    network_interface_no = ncloud_network_interface.db.id
    order                = 0
  }
}

# ncloud_public_ip has no name argument in the installed Provider.
resource "ncloud_public_ip" "bastion" {
  server_instance_no = ncloud_server.bastion.id
  description        = "${var.name_prefix}-bastion public IP"
}

resource "ncloud_public_ip" "db" {
  server_instance_no = ncloud_server.db.id
  description        = "${var.name_prefix}-db public IP for outbound package installation"
}
