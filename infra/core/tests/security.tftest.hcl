# Documentation-only IPs; every run is a plan with a mocked Provider.
mock_provider "ncloud" {
  override_during = plan
}

override_resource {
  target          = ncloud_access_control_group.bastion
  override_during = plan
  values          = { id = "101" }
}

override_resource {
  target          = ncloud_access_control_group.db
  override_during = plan
  values          = { id = "102" }
}

override_resource {
  target          = ncloud_network_interface.bastion
  override_during = plan
  values          = { id = "201" }
}

override_resource {
  target          = ncloud_network_interface.db
  override_during = plan
  values          = { id = "202" }
}

variables {
  team_ips = ["203.0.113.10/32", "198.51.100.20/32"]
}

run "restricted_ingress_and_nic_attachment" {
  command = plan

  assert {
    condition = (
      length(ncloud_access_control_group_rule.bastion.inbound) == 2 &&
      toset([for rule in ncloud_access_control_group_rule.bastion.inbound : rule.ip_block]) == toset(var.team_ips) &&
      alltrue([for rule in ncloud_access_control_group_rule.bastion.inbound : rule.protocol == "TCP" && rule.port_range == "22"])
    )
    error_message = "Bastion must allow only TCP 22 from the requested team /32s."
  }

  assert {
    condition = (
      length(ncloud_access_control_group_rule.db.inbound) == 2 &&
      toset([for rule in ncloud_access_control_group_rule.db.inbound : rule.port_range]) == toset(["22", "3306"]) &&
      alltrue([for rule in ncloud_access_control_group_rule.db.inbound :
        rule.protocol == "TCP" && rule.source_access_control_group_no == ncloud_access_control_group.bastion.id &&
        (rule.ip_block == null || rule.ip_block == "")
      ])
    )
    error_message = "DB must accept TCP 22/3306 only from the Bastion ACG, with no IP-based ingress."
  }

  assert {
    condition = alltrue([
      for rules in [ncloud_access_control_group_rule.bastion.outbound, ncloud_access_control_group_rule.db.outbound] :
      length(rules) == 2 && toset([for rule in rules : rule.protocol]) == toset(["TCP", "UDP"]) &&
      alltrue([for rule in rules : rule.ip_block == "0.0.0.0/0" && rule.port_range == "1-65535"])
    ])
    error_message = "Both ACGs must permit the requested TCP/UDP package-installation egress."
  }

  assert {
    condition = (
      ncloud_network_interface.bastion.access_control_groups == toset([ncloud_access_control_group.bastion.id]) &&
      ncloud_network_interface.db.access_control_groups == toset([ncloud_access_control_group.db.id]) &&
      ncloud_server.bastion.network_interface[0].network_interface_no == ncloud_network_interface.bastion.id &&
      ncloud_server.db.network_interface[0].network_interface_no == ncloud_network_interface.db.id &&
      ncloud_server.bastion.network_interface[0].order == 0 && ncloud_server.db.network_interface[0].order == 0
    )
    error_message = "Each server must use its intended ACG through its primary NIC."
  }
}

run "empty_team_disables_external_ssh" {
  command = plan
  variables { team_ips = [] }

  assert {
    condition     = length(ncloud_access_control_group_rule.bastion.inbound) == 0
    error_message = "An empty team list must explicitly configure zero Bastion inbound rules."
  }

  assert {
    condition = (
      ncloud_server.bastion.name == "finsh-bastion" && ncloud_server.db.name == "finsh-db" &&
      length(ncloud_access_control_group_rule.db.inbound) == 2 &&
      alltrue([for rule in ncloud_access_control_group_rule.db.inbound :
        rule.source_access_control_group_no == ncloud_access_control_group.bastion.id &&
        (rule.ip_block == null || rule.ip_block == "")
      ])
    )
    error_message = "Both servers must still be planned, and DB ingress must remain restricted to the Bastion ACG."
  }
}

run "reject_invalid_ipv4" {
  command = plan
  variables { team_ips = ["999.1.2.3/32"] }
  expect_failures = [var.team_ips]
}

run "reject_malformed_cidr" {
  command = plan
  variables { team_ips = ["not-a-cidr"] }
  expect_failures = [var.team_ips]
}

run "reject_ipv6" {
  command = plan
  variables { team_ips = ["2001:db8::1/32"] }
  expect_failures = [var.team_ips]
}

run "reject_network_range" {
  command = plan
  variables { team_ips = ["203.0.113.0/24"] }
  expect_failures = [var.team_ips]
}

run "reject_world_ssh" {
  command = plan
  variables { team_ips = ["0.0.0.0/0"] }
  expect_failures = [var.team_ips]
}
