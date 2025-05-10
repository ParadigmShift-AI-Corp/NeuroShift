terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "6.8.0"
    }
  }
}

provider "google" {
  project = "evaluation-deployment"
  region  = "us-central1"
  zone    = "us-central1-c"
}

# Create VPC Network
resource "google_compute_network" "vpc_network" {
  name = "terraform-network"
}

# Create Firewall Rule to Allow SSH
resource "google_compute_firewall" "allow-ssh" {
  name    = "allow-ssh"
  network = google_compute_network.vpc_network.self_link

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["0.0.0.0/0"]
}

# Create VM Instance
resource "google_compute_instance" "vm_instance" {
  name         = "playwright-vm"
  machine_type = "e2-medium"
  zone         = "us-central1-c"

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
    }
  }

  network_interface {
    network = google_compute_network.vpc_network.name

    access_config {
    }
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    sudo apt-get update
    sudo apt-get install -y wget unzip

    # Install Chrome
    wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    sudo apt-get install -y ./google-chrome-stable_current_amd64.deb

    # Install Node.js and Playwright
    curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
    sudo apt-get install -y nodejs
    npm install -g playwright

    # Run Playwright script
    cat << EOF > /home/ubuntu/playwright-script.js
    const { chromium } = require('playwright');
    (async () => {
        const browser = await chromium.launch({ headless: false });
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.goto('https://www.google.com');
        await page.fill('input[name="q"]', 'Netflix');
        await page.keyboard.press('Enter');
        await page.waitForSelector('h3');
        console.log("Search completed");
        await browser.close();
    })();
    EOF

    # Execute Playwright script
    node /home/ubuntu/playwright-script.js
  EOT
}

