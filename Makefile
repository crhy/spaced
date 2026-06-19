SHELL := /bin/bash
.ONESHELL:
MAKEFLAGS += --no-builtin-rules

VERSION := $(shell cat VERSION 2>/dev/null || echo "6.26-dev")
ARCH := amd64
ISO_NAME := spaced-linux-$(VERSION)-$(ARCH)
BUILD_DIR := build
ISO_DIR := $(BUILD_DIR)/iso
LB_DIR := $(BUILD_DIR)/live-build

.PHONY: help clean distclean deps init iso-build iso-test release

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-25s\033[0m %s\n", $$1, $$2}'

deps: ## Install build dependencies
	sudo apt update
	sudo apt install -y live-build xorriso squashfs-tools \
		calamares calamares-settings-debian \
		git rsync curl wget

init: ## Initialize build directories
	mkdir -p $(ISO_DIR) $(LB_DIR)

clean: ## Clean build artifacts
	rm -rf $(BUILD_DIR)/*

lb-config: init ## Generate live-build config
	rm -rf $(LB_DIR)/config
	cd $(LB_DIR) && lb config \
		--distribution ceres \
		--archive-areas "main contrib non-free" \
		--mirror-bootstrap "http://deb.devuan.org/merged" \
		--mirror-chroot "http://deb.devuan.org/merged" \
		--mirror-binary "http://deb.devuan.org/merged" \
		--apt-indices false \
		--apt-recommends false \
		--apt-secure false \
		--bootappend-live "boot=live config quiet username=user" \
		--bootappend-install "quiet" \
		--debian-installer false \
		--linux-flavours "amd64" \
		--memtest none \
		--mode debian \
		--parent-distribution Devuan \
		--parent-debian-installer-distribution ceres \
		--parent-mirror-bootstrap "http://deb.devuan.org/merged" \
		--parent-mirror-chroot "http://deb.devuan.org/merged" \
		--parent-mirror-binary "http://deb.devuan.org/merged" \
		--security false \
		--updates false \
		--systemd false \
		--zsync false

lb-packages: lb-config ## Add custom packages
	# Desktop
	echo "task-mate-desktop" > $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "mate-desktop-environment-extras" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "mate-terminal" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "mate-settings-daemon" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "mate-panel" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "brisk-menu" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "marco" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "caja" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Display manager
	echo "lightdm" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "lightdm-gtk-greeter" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Apps
	echo "gedit" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "eom" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "pluma" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "engrampa" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "atril" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "mate-calc" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "mate-screenshot" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Network
	echo "network-manager" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "network-manager-gnome" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Audio
	echo "pulseaudio" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "pavucontrol" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Themes & tools
	echo "papirus-icon-theme" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "flatpak" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "xdg-desktop-portal-gtk" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "sudo" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "xdotool" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "imagemagick" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "feh" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Installer
	echo "calamares" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "calamares-settings-debian" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	# Live
	echo "live-boot" >> $(LB_DIR)/config/package-lists/desktop.list.chroot
	echo "live-config" >> $(LB_DIR)/config/package-lists/desktop.list.chroot

lb-overlay: lb-packages ## Copy custom files into the live system
	mkdir -p $(LB_DIR)/config/includes.chroot
	cp -r overlays/* $(LB_DIR)/config/includes.chroot/

lb-hooks: lb-overlay ## Create hooks for live system configuration
	mkdir -p $(LB_DIR)/config/hooks/live
	cat > $(LB_DIR)/config/hooks/live/01-configure.chroot << 'HOOK'
#!/bin/bash
# Spaced Linux live system configuration

# Enable user autologin
mkdir -p /etc/lightdm/lightdm.conf.d
cat > /etc/lightdm/lightdm.conf.d/50-spaced.conf << 'LIGHTDM'
[Seat:*]
autologin-user=user
autologin-user-timeout=0
greeter-session=lightdm-gtk-greeter
user-session=mate
LIGHTDM

# Set default gsettings
cat > /usr/share/glib-2.0/schemas/90_spaced-linux.gschema.override << 'GSCHEMA'
[org.mate.interface]
gtk-theme='Spaced-Dark'
icon-theme='Papirus-Dark'

[org.gnome.desktop.interface]
gtk-theme='Spaced-Dark'

[org.mate.Marco.general]
theme='Spaced-Dark'

[org.mate.background]
show-desktop-icons=false
draw-background=true
picture-filename='/usr/share/backgrounds/spaced/SpacedBack.png'
picture-options='zoom'

[org.mate.panel]
default-layout=true
layout-name='spaced-linux'
GSCHEMA

glib-compile-schemas /usr/share/glib-2.0/schemas/

# Set default panel layout
mkdir -p /usr/share/mate-panel/layouts

# Create live user
useradd -m -s /bin/bash user
echo "user:1" | chpasswd
echo "root:spaced" | chpasswd
usermod -aG sudo user

# Flatpak
flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

# Cleanup
apt-get clean
HOOK
	chmod +x $(LB_DIR)/config/hooks/live/01-configure.chroot

lb-build: lb-hooks ## Build the live ISO
	cd $(LB_DIR) && sudo lb build 2>&1 | tee $(ISO_DIR)/build.log
	# Find and copy the resulting ISO
	find $(LB_DIR) -name "live-image-*.iso" -exec cp {} $(ISO_DIR)/$(ISO_NAME).iso \;
	@echo "=== ISO built: $(ISO_DIR)/$(ISO_NAME).iso ==="

iso-build: lb-build ## Full ISO build

iso-test: ## Quick boot test of ISO in QEMU
	iso=$$(ls -t $(ISO_DIR)/*.iso 2>/dev/null | head -1)
	if [ -z "$$iso" ]; then
		echo "No ISO found. Build one first: make iso-build"
		exit 1
	fi
	qemu-system-x86_64 -m 2048 -enable-kvm -cdrom "$$iso" -boot d

release: clean iso-build ## Build release ISO
	@echo "=== Spaced Linux $(VERSION) Release ==="
	ls -lh $(ISO_DIR)/*.iso
