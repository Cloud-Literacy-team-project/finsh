output "bastion_public_ip" {
  description = "Bastion public IPv4 address"
  value       = ncloud_public_ip.bastion.public_ip
}

output "db_private_ip" {
  description = "DB private IPv4 address in the shared subnet"
  value       = ncloud_network_interface.db.private_ip
}

output "db_public_ip" {
  description = "DB public IPv4 address; direct internet ingress is not permitted by its ACG"
  value       = ncloud_public_ip.db.public_ip
}

output "vpc_id" {
  value = ncloud_vpc.lab.id
}

output "subnet_id" {
  value = ncloud_subnet.public_kr1.id
}

output "login_key_name" {
  value = ncloud_login_key.lab.key_name
}

output "login_private_key" {
  description = "NCP login private key for administrator-password decryption; stored in State"
  value       = ncloud_login_key.lab.private_key
  sensitive   = true
}

# Retain the existing network output for callers.
output "network_info" {
  description = "Core VPC and shared public subnet"
  value = {
    vpc = {
      name = ncloud_vpc.lab.name
      no   = ncloud_vpc.lab.id
      cidr = var.vpc_cidr
    }
    public_kr1 = {
      name = ncloud_subnet.public_kr1.name
      no   = ncloud_subnet.public_kr1.id
      cidr = var.subnet_cidr
    }
  }
}
