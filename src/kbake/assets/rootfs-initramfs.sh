#!/bin/bash
set -euo pipefail

: "${ROOTFS_INITRAMFS_NAME:?}"

WORK=$(mktemp -d)
ROOTFS="${WORK}/rootfs"

cleanup() {
    rm -rf "${WORK}"
}
trap cleanup EXIT

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
cat > "${ROOTFS}/init" << 'INIT_EOF'
#!/bin/sh

mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts devpts /dev/pts
mount -t tmpfs tmpfs /tmp
mount -t tmpfs tmpfs /run

hostname kernel-test
echo "kernel-test" > /etc/hostname

ip link set lo up 2>/dev/null || true

echo
echo "============================================"
echo "  Minimal initramfs booted OK"
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
(cd "${ROOTFS}" && find . | cpio -o -H newc --quiet | gzip -9) > "/out/${ROOTFS_INITRAMFS_NAME}"

SIZE=$(du -h "/out/${ROOTFS_INITRAMFS_NAME}" | cut -f1)
echo "==> Done: ${ROOTFS_INITRAMFS_NAME} (${SIZE})"
