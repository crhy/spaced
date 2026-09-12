SHELL := /bin/bash
.SHELLFLAGS := -eu -o pipefail -c
.ONESHELL:
MAKEFLAGS += --no-builtin-rules

VERSION := $(shell cat VERSION)
ARCH := amd64
ISO_NAME := spaced-linux-$(VERSION)-$(ARCH).iso
BUILD_DIR := build
ISO_DIR := $(BUILD_DIR)/iso
LB_DIR := $(BUILD_DIR)/live-build
CACHE_DIR := $(BUILD_DIR)/cache/live-build
EXTERNAL_CACHE_DIR := $(BUILD_DIR)/cache/external-artifacts
LOCAL_PACKAGE_DIR := $(BUILD_DIR)/local-packages
EXTERNAL_STAGE_DIR := $(BUILD_DIR)/external-artifacts

# Verified local overrides for independently released components. These are
# passed explicitly because IDE builds may cross the Flatpak host boundary.
SPACED_EXTERNAL_ARTIFACT_CONFIG ?=
SPACED_WELCOME_VERSION ?=
SPACED_WELCOME_RELEASE_TAG ?=
SPACED_WELCOME_URL ?=
SPACED_WELCOME_DEB ?=
SPACED_WELCOME_SHA256 ?=
SPACED_GITHUB_REMOTE_DESCRIPTOR_URL ?=
SPACED_GITHUB_REMOTE_FILE ?=
SPACED_GITHUB_REMOTE_SHA256 ?=
SPACED_GITHUB_GPG_FINGERPRINT ?=

# Codex/IDE terminals run inside a Flatpak. On a regular shell this is empty.
HOST_RUN ?= $(shell command -v flatpak-spawn >/dev/null 2>&1 && printf 'flatpak-spawn --host')
ROOT_RUN ?= $(shell command -v flatpak-spawn >/dev/null 2>&1 && printf 'flatpak-spawn --host pkexec' || printf 'sudo')
VM_SSH_PORT ?= 2222
VBOX_SSH_PORT ?= 2223
ISO_SMOKE_TIMEOUT ?= 240
VM_XRES ?= 1440
VM_YRES ?= 900
SAFE_XRES ?= 1920
SAFE_YRES ?= 1080
VM_RUN := $(HOST_RUN) env SPACED_VM_SSH_PORT=$(VM_SSH_PORT) SPACED_VM_XRES=$(VM_XRES) SPACED_VM_YRES=$(VM_YRES)
ISO_SMOKE_RUN := $(HOST_RUN) env SPACED_ISO_SMOKE_TIMEOUT=$(ISO_SMOKE_TIMEOUT)
VBOX_RUN := $(ISO_SMOKE_RUN) SPACED_VBOX_SSH_PORT=$(VBOX_SSH_PORT)

.PHONY: help check deps clean cache-clean marco prepare lb-config lb-build iso-build iso-test iso-smoke iso-smoke-kvm iso-smoke-kvm-efi iso-smoke-kvm-4k iso-smoke-virtualbox iso-smoke-virtualbox-efi iso-test-safe iso-test-safe-1024 iso-test-safe-1080 vm-create vm-install vm-start vm-stop release-preflight release apt-repo apt-repo-publish

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

deps: ## Install host build and test dependencies
	$(ROOT_RUN) apt-get update
	$(ROOT_RUN) apt-get install -y \
		live-build debootstrap xorriso squashfs-tools grub-common \
		qemu-system-x86 qemu-utils ovmf rsync curl gnupg sshpass \
		python3-yaml desktop-file-utils apt-utils python3-gi gir1.2-gtk-3.0 xvfb bubblewrap

check: ## Validate configuration, scripts, themes, and desktop entries
	$(HOST_RUN) scripts/tests/test-testing-upgrade.sh
	$(HOST_RUN) scripts/check.sh
	$(HOST_RUN) env PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
	$(HOST_RUN) env PYTHONDONTWRITEBYTECODE=1 xvfb-run -a python3 tests/gtk_desktop.py

clean: ## Remove generated build data for the current release
	$(ROOT_RUN) rm -rf "$(abspath $(LB_DIR))" "$(abspath $(LOCAL_PACKAGE_DIR))" \
		"$(abspath $(EXTERNAL_STAGE_DIR))"
	rm -f $(ISO_DIR)/$(ISO_NAME) $(ISO_DIR)/$(ISO_NAME).sha256

cache-clean: ## Remove cached live-build packages and bootstrap data
	$(ROOT_RUN) rm -rf "$(abspath $(CACHE_DIR))" "$(abspath $(EXTERNAL_CACHE_DIR))"

marco: ## Build the upstream Marco fixes in an isolated Devuan chroot
	if ! $(HOST_RUN) scripts/iso/stage-marco.sh --check; then
		$(ROOT_RUN) bash "$(abspath scripts/iso/build-marco-chroot.sh)"
	fi

prepare: marco ## Stage authored live-build configuration
	mkdir -p $(BUILD_DIR)/cache
	if [[ -d "$(LB_DIR)/cache" && ! -L "$(LB_DIR)/cache" && ! -e "$(CACHE_DIR)" ]]; then
		$(ROOT_RUN) mv "$(abspath $(LB_DIR)/cache)" "$(abspath $(CACHE_DIR))"
	fi
	$(ROOT_RUN) rm -rf "$(abspath $(LB_DIR))"
	mkdir -p $(LB_DIR)/auto $(CACHE_DIR) $(ISO_DIR)
	# A bootstrap cache copied or created outside the privileged build can retain
	# the invoking user's ownership for core image paths. Package postinst scripts
	# correctly reject that unsafe state, so discard only the bootstrap cache and
	# retain the much larger downloaded package cache.
	unsafe_bootstrap=
	if [[ -d "$(CACHE_DIR)/bootstrap" ]]; then
		for path in '' etc usr usr/bin usr/sbin; do
			owner=$$(stat -c '%u:%g' "$(CACHE_DIR)/bootstrap$${path:+/$$path}")
			if [[ "$$owner" != 0:0 ]]; then
				unsafe_bootstrap=1
				break
			fi
		done
	fi
	if [[ -n "$$unsafe_bootstrap" ]]; then
		echo "Discarding unsafe live-build bootstrap cache (core paths are not root-owned)"
		$(ROOT_RUN) rm -rf "$(abspath $(CACHE_DIR))/bootstrap"
	fi
	ln -s ../cache/live-build $(LB_DIR)/cache
	cp live-build/auto/config $(LB_DIR)/auto/config
	chmod +x $(LB_DIR)/auto/config
	cd $(LB_DIR)
	$(HOST_RUN) env SPACED_DEVUAN_KEYRING="$(abspath config/keyrings/devuan-archive-keyring.pgp)" lb config
	cd ../..
	mkdir -p \
		$(LB_DIR)/config/package-lists \
		$(LB_DIR)/config/packages.chroot \
		$(LB_DIR)/config/includes.chroot \
		$(LB_DIR)/config/hooks/live \
		$(LB_DIR)/config/bootloaders
	cp -a overlays/. $(LB_DIR)/config/includes.chroot/
	cp -a live-build/config/bootloaders/. $(LB_DIR)/config/bootloaders/
	$(HOST_RUN) install -Dm644 /usr/share/grub/unicode.pf2 $(LB_DIR)/config/bootloaders/grub-pc/fonts/unicode.pf2
	$(HOST_RUN) scripts/iso/package-list.sh > \
		$(LB_DIR)/config/package-lists/spaced.list.chroot
	cp scripts/iso/01-configure.chroot \
		$(LB_DIR)/config/hooks/live/01-configure.chroot
	chmod +x $(LB_DIR)/config/hooks/live/01-configure.chroot
	$(HOST_RUN) env \
		SPACED_TARGET_ARCH="$(ARCH)" \
		SPACED_IMAGE_ROOT="$(abspath $(LB_DIR)/config/includes.chroot)" \
		SPACED_EXTERNAL_ARTIFACT_CONFIG="$(SPACED_EXTERNAL_ARTIFACT_CONFIG)" \
		SPACED_WELCOME_VERSION="$(SPACED_WELCOME_VERSION)" \
		SPACED_WELCOME_RELEASE_TAG="$(SPACED_WELCOME_RELEASE_TAG)" \
		SPACED_WELCOME_URL="$(SPACED_WELCOME_URL)" \
		SPACED_WELCOME_DEB="$(SPACED_WELCOME_DEB)" \
		SPACED_WELCOME_SHA256="$(SPACED_WELCOME_SHA256)" \
		SPACED_GITHUB_REMOTE_DESCRIPTOR_URL="$(SPACED_GITHUB_REMOTE_DESCRIPTOR_URL)" \
		SPACED_GITHUB_REMOTE_FILE="$(SPACED_GITHUB_REMOTE_FILE)" \
		SPACED_GITHUB_REMOTE_SHA256="$(SPACED_GITHUB_REMOTE_SHA256)" \
		SPACED_GITHUB_GPG_FINGERPRINT="$(SPACED_GITHUB_GPG_FINGERPRINT)" \
		scripts/iso/stage-external-artifacts.sh
	$(HOST_RUN) scripts/iso/build-local-packages.sh
	# live-build copies this tree with ownership preserved. Make every image
	# path root-owned so security-sensitive package scripts (notably OpenSSH)
	# do not reject /usr or /usr/bin as an unsafe ownership transition.
	$(ROOT_RUN) chown -R 0:0 "$(abspath $(LB_DIR)/config/includes.chroot)"
	cp $(LOCAL_PACKAGE_DIR)/*.deb $(LB_DIR)/config/packages.chroot/

lb-config: prepare ## Generate the complete live-build tree

lb-build: prepare ## Build the live ISO (requires sudo)
	$(ROOT_RUN) sh -lc 'cd "$(abspath $(LB_DIR))" && exec lb build'
	iso=$$(find $(LB_DIR) -maxdepth 1 -type f -name '*.iso' -print -quit)
	test -n "$$iso"
	rm -f $(ISO_DIR)/$(ISO_NAME) $(ISO_DIR)/$(ISO_NAME).sha256
	cp "$$iso" $(ISO_DIR)/$(ISO_NAME)
	cd $(ISO_DIR)
	sha256sum $(ISO_NAME) > $(ISO_NAME).sha256
	@echo "Built $(ISO_DIR)/$(ISO_NAME)"

iso-build: lb-build ## Build the live ISO

iso-test: ## Boot the current release ISO in KVM
	test -f $(ISO_DIR)/$(ISO_NAME) || { echo "Missing $(ISO_DIR)/$(ISO_NAME)"; exit 1; }
	$(VM_RUN) scripts/vm/qemu/test-iso.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

iso-smoke: iso-smoke-kvm iso-smoke-kvm-efi iso-smoke-virtualbox iso-smoke-virtualbox-efi ## Smoke-test the ISO in KVM and VirtualBox BIOS/EFI

iso-smoke-kvm: ## Headlessly boot the ISO in KVM and wait for live SSH
	test -f $(ISO_DIR)/$(ISO_NAME) || { echo "Missing $(ISO_DIR)/$(ISO_NAME)"; exit 1; }
	$(ISO_SMOKE_RUN) SPACED_VM_SSH_PORT=$(VM_SSH_PORT) SPACED_QEMU_ARTIFACT_DIR="$(abspath $(BUILD_DIR)/test-artifacts/qemu-bios)" scripts/vm/qemu/smoke-iso.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

iso-smoke-kvm-efi: ## Boot and validate the UEFI live desktop in QEMU
	test -f $(ISO_DIR)/$(ISO_NAME)
	$(ISO_SMOKE_RUN) SPACED_VM_SSH_PORT=$(VM_SSH_PORT) SPACED_QEMU_FIRMWARE=uefi SPACED_QEMU_ARTIFACT_DIR="$(abspath $(BUILD_DIR)/test-artifacts/qemu-uefi)" scripts/vm/qemu/smoke-iso.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

iso-smoke-kvm-4k: ## Exercise a 3840x2160 virtual display (not physical GPU certification)
	test -f $(ISO_DIR)/$(ISO_NAME)
	$(ISO_SMOKE_RUN) SPACED_VM_SSH_PORT=$(VM_SSH_PORT) SPACED_QEMU_XRES=3840 SPACED_QEMU_YRES=2160 SPACED_QEMU_ARTIFACT_DIR="$(abspath $(BUILD_DIR)/test-artifacts/qemu-4k)" scripts/vm/qemu/smoke-iso.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

iso-smoke-virtualbox: ## Headlessly boot the ISO in VirtualBox BIOS mode
	test -f $(ISO_DIR)/$(ISO_NAME) || { echo "Missing $(ISO_DIR)/$(ISO_NAME)"; exit 1; }
	$(VBOX_RUN) SPACED_VBOX_FIRMWARE=bios scripts/vm/virtualbox/smoke-iso.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

iso-smoke-virtualbox-efi: ## Headlessly boot the ISO in VirtualBox EFI mode
	test -f $(ISO_DIR)/$(ISO_NAME) || { echo "Missing $(ISO_DIR)/$(ISO_NAME)"; exit 1; }
	$(VBOX_RUN) SPACED_VBOX_FIRMWARE=efi scripts/vm/virtualbox/smoke-iso.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

iso-test-safe: ## Boot ISO with safe 2D graphics at the selected resolution
	test -f $(ISO_DIR)/$(ISO_NAME)
	$(HOST_RUN) qemu-system-x86_64 \
		-enable-kvm \
		-cpu host \
		-smp 4 \
		-m 4096 \
		-device qemu-xhci,id=xhci \
		-device usb-kbd,bus=xhci.0 \
		-device usb-tablet,bus=xhci.0 \
		-vga std \
		-cdrom $(ISO_DIR)/$(ISO_NAME) \
		-boot d \
		-display gtk

iso-test-safe-1024: ## Boot safe graphics at 1024x768
	$(MAKE) iso-test-safe SAFE_XRES=1024 SAFE_YRES=768

iso-test-safe-1080: ## Boot safe graphics at 1920x1080
	$(MAKE) iso-test-safe SAFE_XRES=1920 SAFE_YRES=1080

vm-create: ## Create the reusable 25 GB KVM test disk
	$(VM_RUN) scripts/vm/qemu/create.sh

vm-install: ## Boot the ISO with the reusable KVM test disk
	$(VM_RUN) scripts/vm/qemu/install.sh $(abspath $(ISO_DIR)/$(ISO_NAME))

vm-start: ## Boot the installed KVM test disk
	$(VM_RUN) scripts/vm/qemu/start.sh

vm-stop: ## Stop a headless KVM test instance
	$(VM_RUN) scripts/vm/qemu/stop.sh

release-preflight: check ## Run tests and reject unpublished release inputs
	$(HOST_RUN) env \
		SPACED_EXTERNAL_ARTIFACT_CONFIG="$(SPACED_EXTERNAL_ARTIFACT_CONFIG)" \
		SPACED_WELCOME_VERSION="$(SPACED_WELCOME_VERSION)" \
		SPACED_WELCOME_RELEASE_TAG="$(SPACED_WELCOME_RELEASE_TAG)" \
		SPACED_WELCOME_SHA256="$(SPACED_WELCOME_SHA256)" \
		SPACED_GITHUB_REMOTE_SHA256="$(SPACED_GITHUB_REMOTE_SHA256)" \
		SPACED_GITHUB_GPG_FINGERPRINT="$(SPACED_GITHUB_GPG_FINGERPRINT)" \
		scripts/release-preflight.sh

release: release-preflight ## Test and clean-build the current Spaced Linux ISO
	$(MAKE) clean
	$(MAKE) lb-build

APT_REPO_DIR := spaced-apt

apt-repo: marco ## Rebuild the update repository into ./spaced-apt (from crhy/spaced-apt)
	@if [ ! -d "$(APT_REPO_DIR)/.git" ]; then \
		rm -rf "$(APT_REPO_DIR)"; \
		gh repo clone crhy/spaced-apt "$(APT_REPO_DIR)"; \
	fi
	$(HOST_RUN) scripts/build-apt-repo.sh "$(abspath $(APT_REPO_DIR))"
	$(HOST_RUN) scripts/tests/test-release-package-payload.sh "$(abspath $(APT_REPO_DIR))"
	$(HOST_RUN) scripts/tests/test-apt-trust.sh "$(abspath $(APT_REPO_DIR))"

apt-repo-publish: apt-repo ## Rebuild and publish the update repository to crhy/spaced-apt
	cd "$(APT_REPO_DIR)" && \
		git add -A && \
		git -c user.name="Spaced Linux Release" \
		   -c user.email="release@spaced" \
			commit -m "Spaced Linux $(VERSION) repository update" && \
		git push
