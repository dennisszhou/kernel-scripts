#!/usr/bin/env bash
#
# kvm-boot.sh — boot an arm64 kernel under QEMU
#
# Usage:
#   ./kvm-boot.sh                                    # auto-detect rootfs
#   ./kvm-boot.sh -k path/to/Image                   # custom kernel
#   ./kvm-boot.sh -d rootfs.img                       # boot from disk image
#   ./kvm-boot.sh -i rootfs.cpio.gz                   # boot from initramfs
#   MEMORY=2G CPUS=4 ./kvm-boot.sh                    # override defaults
#   KERNEL_APPEND="debug" ./kvm-boot.sh               # extra cmdline
#
# On macOS Apple Silicon this uses Hypervisor.framework (-accel hvf)
# for near-native speed. On Linux aarch64 it uses KVM.

set -euo pipefail

KERNEL="$HOME/workplace/percpu/arch/arm64/boot/Image"
DISK=""
INITRD=""
MEMORY="${MEMORY:-2G}"
CPUS="${CPUS:-4}"
EXTRA_APPEND="${KERNEL_APPEND:-}"

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        -k|--kernel) KERNEL="$2"; shift 2 ;;
        -d|--disk)   DISK="$2";   shift 2 ;;
        -i|--initrd) INITRD="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# Auto-detect root filesystem if neither specified
if [[ -z "${DISK}" && -z "${INITRD}" ]]; then
    if [[ -f rootfs.img ]]; then
        DISK="rootfs.img"
    elif [[ -f rootfs.cpio.gz ]]; then
        INITRD="rootfs.cpio.gz"
    else
        echo "Error: no rootfs found. Provide -d rootfs.img or -i rootfs.cpio.gz"
        echo "  Build one with: ./mk-diskimg.sh  or  ./mk-rootfs.sh"
        exit 1
    fi
fi

if [[ ! -f "${KERNEL}" ]]; then
    echo "Error: kernel image not found: ${KERNEL}"
    echo "  kbuild ARCH=arm64 -j\$(nproc)"
    exit 1
fi

# Pick the right accelerator
ACCEL_ARGS=()
case "$(uname -s)" in
    Darwin)
        ACCEL_ARGS=(-accel hvf)
        echo "Accelerator: macOS Hypervisor.framework (hvf)"
        ;;
    Linux)
        if [[ -e /dev/kvm ]]; then
            ACCEL_ARGS=(-accel kvm)
            echo "Accelerator: KVM"
        else
            ACCEL_ARGS=(-accel tcg)
            echo "Accelerator: TCG (software — no /dev/kvm)"
        fi
        ;;
    *)
        ACCEL_ARGS=(-accel tcg)
        echo "Accelerator: TCG (software)"
        ;;
esac

# Build QEMU args
QEMU_ARGS=(
    -M virt
    -cpu host
    "${ACCEL_ARGS[@]}"
    -kernel "${KERNEL}"
    -m "${MEMORY}"
    -smp "${CPUS}"
    -nographic
    -no-reboot
    -net nic,model=virtio
    -net user
)

if [[ -n "${DISK}" ]]; then
    if [[ ! -f "${DISK}" ]]; then
        echo "Error: disk image not found: ${DISK}"
        exit 1
    fi
    QEMU_ARGS+=(
        -drive file="${DISK}",format=raw,if=virtio
    )
    APPEND="console=ttyAMA0 earlycon=pl011,0x09000000 root=/dev/vda rw panic=1 ${EXTRA_APPEND}"
    echo "Root: disk image (${DISK})"
else
    if [[ ! -f "${INITRD}" ]]; then
        echo "Error: initramfs not found: ${INITRD}"
        exit 1
    fi
    QEMU_ARGS+=(
        -initrd "${INITRD}"
    )
    APPEND="console=ttyAMA0 earlycon=pl011,0x09000000 panic=1 ${EXTRA_APPEND}"
    echo "Root: initramfs (${INITRD})"
fi

QEMU_ARGS+=(-append "${APPEND}")

echo "Booting:"
echo "  Kernel:  ${KERNEL}"
echo "  Memory:  ${MEMORY}"
echo "  CPUs:    ${CPUS}"
echo

exec qemu-system-aarch64 "${QEMU_ARGS[@]}"
