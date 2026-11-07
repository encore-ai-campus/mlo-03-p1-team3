terraform {
  required_version = ">= 1.4.0"
  required_providers {
    vmworkstation = {
      source  = "elsudano/vmworkstation"
      version = "2.0.1"
    }
  }
}
variable "vmrest_endpoint" { type = string }
variable "vmrest_username" { type = string }
variable "vmrest_password" {
  type      = string
  sensitive = true
}
variable "vm_directory" { type = string }
variable "base_vm_name" { type = string }
variable "vm_prefix" { type = string }
variable "gateway" { type = string }
variable "bridge_vnet" {
  type    = string
  default = "VMnet0"
}
variable "ssh_public_key_file" { type = string }
variable "power_state" {
  type    = string
  default = "off"
  validation {
    condition     = contains(["off", "on"], var.power_state)
    error_message = "power_state must be on or off."
  }
}
variable "vms" {
  type = map(object({ ip = string, processors = number, memory_mb = number }))
}
provider "vmworkstation" {
  endpoint = var.vmrest_endpoint
  username = var.vmrest_username
  password = var.vmrest_password
  https    = false
  debug    = "NONE"
}
data "vmworkstation_virtual_machine" "base" {
  denomination = var.base_vm_name
}
resource "vmworkstation_virtual_machine" "server" {
  for_each     = var.vms
  sourceid     = data.vmworkstation_virtual_machine.base.id
  denomination = "${var.vm_prefix}-${each.key}"
  description  = data.vmworkstation_virtual_machine.base.description
  path         = "${var.vm_directory}\\${var.vm_prefix}-${each.key}\\${var.vm_prefix}-${each.key}.vmx"
  processors   = each.value.processors
  memory       = each.value.memory_mb
  state        = var.power_state
  lifecycle { prevent_destroy = true }
}
resource "terraform_data" "network" {
  for_each         = var.vms
  triggers_replace = [vmworkstation_virtual_machine.server[each.key].id, each.value.ip, var.gateway, var.bridge_vnet, filesha256(var.ssh_public_key_file)]
  provisioner "local-exec" {
    command = "bash '${path.module}/bootstrap-guest.sh'"
    environment = {
      VMX_WIN           = vmworkstation_virtual_machine.server[each.key].path
      VM_ID             = vmworkstation_virtual_machine.server[each.key].id
      VM_NAME           = "${var.vm_prefix}-${each.key}"
      VM_IP             = each.value.ip
      VM_BRIDGE_VNET    = var.bridge_vnet
      VM_GATEWAY        = var.gateway
      VM_SSH_PUBLIC_KEY = var.ssh_public_key_file
    }
  }
}
output "addresses" { value = { for name, spec in var.vms : name => spec.ip } }
