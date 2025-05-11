# Neuro Shift

Reflects the neuro-inspired nature of AI models and a shift in how they are evaluated

# Terraform

Use to automate infrastructure deployment for each evaluation test that is triggered from [Paradigm Shift AI](https://paradigm-shift.ai/deployment).

## Install Terraform

[Installation Instruction](https://developer.hashicorp.com/terraform/tutorials/gcp-get-started/infrastructure-as-code)

```bash
sudo apt-get update && sudo apt-get install -y gnupg software-properties-common
```

Install Hashicorp

```bash
wget -O- https://apt.releases.hashicorp.com/gpg | \
gpg --dearmor | \
sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
```

Download Packages
```bash 
sudo apt update
```

Install Terraform

```bash
sudo apt-get install terraform
```
