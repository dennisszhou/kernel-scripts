#!/usr/bin/env bash
#
# mk-rootfs.sh — generate a minimal arm64 initramfs (cpio+gz) for
#                boot-testing kernels under QEMU.
#
# Runs inside the kernel-builder container (which has busybox installed).
#
# Usage:
#   ./mk-rootfs.sh              # produces rootfs.cpio.gz in current dir
#   ./mk-rootfs.sh /path/out    # produces /path/out/rootfs.cpio.gz

set -euo pipefail

IMAGE_NAME="kernel-builder"
OUTDIR="${1:-.}"
mkdir -p "${OUTDIR}"
OUTDIR_ABS="$(cd "${OUTDIR}" && pwd)"

exec docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "${OUTDIR_ABS}:/out" \
    -e HOME=/tmp \
    "${IMAGE_NAME}" \
    bash -c '
set -euo pipefail

WORK=$(mktemp -d)
ROOTFS="${WORK}/rootfs"

echo "==> Creating rootfs skeleton"
mkdir -p "${ROOTFS}"/{bin,sbin,etc,proc,sys,dev,tmp,run,mnt,root}
mkdir -p "${ROOTFS}"/etc/init.d
mkdir -p "${ROOTFS}"/usr/{bin,sbin}

echo "==> Installing busybox"
cp "$(command -v busybox)" "${ROOTFS}/bin/busybox"
chmod +x "${ROOTFS}/bin/busybox"

echo "==> Creating symlinks"
for applet in $("${ROOTFS}/bin/busybox" --list); do
    ln -sf busybox "${ROOTFS}/bin/${applet}" 2>/dev/null || true
done

echo "==> Writing /init"
cat > "${ROOTFS}/init" << '\''INIT_EOF'\''
#!/bin/sh

mount -t proc    proc    /proc
mount -t sysfs   sysfs   /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts  devpts  /dev/pts
mount -t tmpfs   tmpfs   /tmp
mount -t tmpfs   tmpfs   /run

hostname kernel-test
echo "kernel-test" > /etc/hostname

ip link set lo up 2>/dev/null || true

echo
echo "============================================"
echo "  Minimal arm64 initramfs booted OK"
echo "  Kernel: $(uname -sr)"
echo "  Machine: $(uname -m)"
echo "  $(date)"
echo "============================================"
echo
echo "For networking:  ip link set eth0 up && udhcpc -i eth0"
echo "To exit QEMU:    poweroff -f"
echo

exec /bin/sh
INIT_EOF
chmod +x "${ROOTFS}/init"

echo "==> Packing initramfs"
(cd "${ROOTFS}" && find . | cpio -o -H newc --quiet | gzip -9) > /out/rootfs.cpio.gz

SIZE=$(du -h /out/rootfs.cpio.gz | cut -f1)
echo "==> Done: rootfs.cpio.gz (${SIZE})"
'
