variable "region" {
  description = "Naver Cloud region for this core deployment"
  type        = string
  default     = "KR"

  validation {
    condition     = var.region == "KR"
    error_message = "This core deployment is configured for the KR region."
  }
}

variable "zone_kr1" {
  description = "Availability zone for both servers and their shared subnet"
  type        = string
  default     = "KR-1"

  validation {
    condition     = var.zone_kr1 == "KR-1"
    error_message = "Both servers and the shared subnet must use KR-1."
  }
}

variable "name_prefix" {
  description = "Prefix for the core resources"
  type        = string
  default     = "finsh"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,10}$", var.name_prefix))
    error_message = "name_prefix must contain 3-11 lowercase letters, numbers, or hyphens and start with a letter."
  }
}

variable "vpc_cidr" {
  description = "Core VPC IPv4 CIDR"
  type        = string
  default     = "10.0.0.0/16"

  validation {
    condition     = can(cidrnetmask(var.vpc_cidr))
    error_message = "vpc_cidr must be a valid IPv4 CIDR."
  }
}

variable "subnet_cidr" {
  description = "Shared public subnet IPv4 CIDR for Bastion and DB"
  type        = string
  default     = "10.0.1.0/24"

  validation {
    condition     = can(cidrnetmask(var.subnet_cidr))
    error_message = "subnet_cidr must be a valid IPv4 CIDR."
  }
}

variable "team_ips" {
  description = "Team public IPv4 /32 CIDRs permitted to SSH to Bastion; empty means no external SSH ingress"
  type        = list(string)
  default     = []
  nullable    = false

  validation {
    condition = alltrue([
      for ip in var.team_ips :
      can(cidrnetmask(ip)) && can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/32$", ip))
    ])
    error_message = "team_ips must contain valid IPv4 /32 CIDRs only, or be empty to disable external SSH; SSH from 0.0.0.0/0 is forbidden."
  }
}

variable "server_image_number" {
  description = "Ubuntu 24.04 x86_64 KVM image; recheck account availability before apply"
  type        = string
  default     = "104630229"

  validation {
    condition     = can(regex("^[0-9]+$", var.server_image_number))
    error_message = "server_image_number must be a verified numeric Ubuntu image number."
  }
}

variable "server_spec_code" {
  description = "Small reusable-NIC-compatible KVM spec verified for the image in KR-1"
  type        = string
  default     = "c2-g3a"

  validation {
    condition     = length(trimspace(var.server_spec_code)) > 0
    error_message = "server_spec_code must contain a verified compatible server specification code."
  }
}
