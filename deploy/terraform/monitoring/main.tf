terraform {
  required_version = ">= 1.4.0"
  required_providers {
    vmworkstation = {
      source  = "elsudano/vmworkstation"
      version = "2.0.1"
    }
  }
}
provider "vmworkstation" {
  endpoint = var.vmrest_endpoint
  username = var.vmrest_username
  password = var.vmrest_password
  https    = false
  debug    = "NONE"
}
variable "vmrest_endpoint" { type = string }
variable "vmrest_username" { type = string }
variable "vmrest_password" {
  type      = string
  sensitive = true
}
variable "vm_directory" {
  type    = string
  default = "C:\\Users\\Playdata\\Documents\\Virtual Machines"
}
variable "base_vm_name" {
  type    = string
  default = "ubuntu24-base"
}
variable "power_state" {
  type    = string
  default = "off"
  validation {
    condition     = contains(["on", "off"], var.power_state)
    error_message = "power_state must be on or off."
  }
}
locals {
  servers = {
    prometheus = "192.168.0.198"
    loki       = "192.168.0.199"
    grafana    = "192.168.0.200"
  }
}
data "vmworkstation_virtual_machine" "base" {
  denomination = var.base_vm_name
}
resource "vmworkstation_virtual_machine" "monitoring" {
  for_each     = local.servers
  sourceid     = data.vmworkstation_virtual_machine.base.id
  denomination = "ubuntu24-${each.key}"
  description  = "Ubuntu 24.04 base template for Terraform"
  path         = "${var.vm_directory}\\ubuntu24-${each.key}\\ubuntu24-${each.key}.vmx"
  processors   = 2
  memory       = 2048
  state        = var.power_state
}
resource "terraform_data" "bootstrap" {
  for_each         = local.servers
  triggers_replace = [vmworkstation_virtual_machine.monitoring[each.key].id]
  provisioner "local-exec" {
    command = "bash '${path.module}/bootstrap-guest.sh'"
    environment = {
      VMX_WIN = vmworkstation_virtual_machine.monitoring[each.key].path
      VM_ID   = vmworkstation_virtual_machine.monitoring[each.key].id
      VM_IP   = each.value
      VM_NAME = each.key
    }
  }
}
output "monitoring_ips" { value = local.servers }
