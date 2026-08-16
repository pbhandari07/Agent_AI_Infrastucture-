terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azuerm"
      version = "4.80.0"
    }
  }
}
provider "azurerm" {
  features {}
}
variable "resources" {
  type    = string
  default = "humana-rg"
}
variable "lock" {
  type    = string
  default = "eastus"
}
resource "azurm_resource_group" "rgs" {
  name     = "humana-rg"
  location = "eastus"
}