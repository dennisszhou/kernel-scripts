#!/usr/bin/env bash
#
# mk-diskimg.sh — generate a 4GB ext4 disk image with busybox for
#                 boot-testing kernels under QEMU.
#
# Runs inside the kernel-builder container (needs loop devices, so
# we use --privileged).
#
# Usage:
#   ./mk-diskimg.sh              # produces rootfs.img in current dir
#   ./mk-diskimg.sh /path/out    # produces /path/out/rootfs.img

set -euo pipefail

IMAGE_NAME="kernel-builder"
OUTDIR="${1:-.}"
mkdir -p "${OUTDIR}"
OUTDIR_ABS="$(cd "${OUTDIR}" && pwd)"

# Write the inner script to a temp file to avoid nested quoting issues
INNER_SCRIPT=$(mktemp)
trap 'rm -f "${INNER_SCRIPT}"' EXIT

cat > "${INNER_SCRIPT}" << 'OUTER_EOF'
#!/bin/bash
set -euo pipefail

IMG="/out/rootfs.img"
SIZE_MB=4096
WORK=$(mktemp -d)
MNT="${WORK}/mnt"

echo "==> Creating ${SIZE_MB}MB sparse image"
dd if=/dev/zero of="${IMG}" bs=1M count=0 seek=${SIZE_MB} 2>/dev/null

echo "==> Formatting as ext4"
mkfs.ext4 -q -L rootfs "${IMG}"

echo "==> Mounting"
mkdir -p "${MNT}"
mount -o loop "${IMG}" "${MNT}"

echo "==> Creating rootfs skeleton"
mkdir -p "${MNT}"/{bin,sbin,etc,proc,sys,dev,tmp,run,mnt,root,var/log,home}
mkdir -p "${MNT}"/etc/init.d
mkdir -p "${MNT}"/usr/{bin,sbin,lib,share/udhcpc}

echo "==> Installing busybox"
cp "$(command -v busybox)" "${MNT}/bin/busybox"
chmod +x "${MNT}/bin/busybox"

echo "==> Creating symlinks"
for applet in $("${MNT}/bin/busybox" --list); do
    ln -sf busybox "${MNT}/bin/${applet}" 2>/dev/null || true
done

echo "==> Writing udhcpc default script"
cat > "${MNT}/usr/share/udhcpc/default.script" << 'DHCP_EOF'
#!/bin/sh
case "$1" in
    bound|renew)
        ip addr flush dev "$interface"
        ip addr add "$ip/${mask:-24}" dev "$interface"
        if [ -n "$router" ]; then
            ip route add default via "$router" dev "$interface"
        fi
        if [ -n "$dns" ]; then
            : > /etc/resolv.conf
            for d in $dns; do
                echo "nameserver $d" >> /etc/resolv.conf
            done
        fi
        ;;
    deconfig)
        ip addr flush dev "$interface"
        ip link set "$interface" up
        ;;
esac
DHCP_EOF
chmod +x "${MNT}/usr/share/udhcpc/default.script"

echo "==> Writing /sbin/init"
cat > "${MNT}/sbin/init" << 'INIT_EOF'
#!/bin/sh

mount -t proc    proc    /proc
mount -t sysfs   sysfs   /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts
mount -t devpts  devpts  /dev/pts
mount -t tmpfs   tmpfs   /tmp
mount -t tmpfs   tmpfs   /run

# Remount root read-write
mount -o remount,rw /

hostname kernel-test
echo "kernel-test" > /etc/hostname

ip link set lo up 2>/dev/null || true

# Seed /etc files if missing
[ -f /etc/passwd ] || echo "root:x:0:0:root:/root:/bin/sh" > /etc/passwd
[ -f /etc/group ]  || echo "root:x:0:" > /etc/group

# Auto-configure networking
if [ -e /sys/class/net/eth0 ]; then
    echo "Bringing up eth0..."
    ip link set eth0 up
    udhcpc -i eth0 -q -s /usr/share/udhcpc/default.script 2>/dev/null
fi

echo
echo "============================================"
echo "  Minimal arm64 disk image booted OK"
echo "  Kernel: $(uname -sr)"
echo "  Machine: $(uname -m)"
echo "  $(date)"
echo "============================================"
echo
ip -4 addr show eth0 2>/dev/null | grep inet && echo
echo "To exit QEMU:  poweroff -f"
echo

# Set up a proper TTY so the shell gets job control and terminal size
if [ -e /dev/ttyAMA0 ]; then
    exec setsid cttyhack sh -c '
        if command -v resize >/dev/null 2>&1; then
            eval $(resize)
        fi
        exec /bin/sh
    '
else
    exec /bin/sh
fi
INIT_EOF
chmod +x "${MNT}/sbin/init"

echo "==> Cleaning up"
umount "${MNT}"
rm -rf "${WORK}"

SIZE=$(du -h "${IMG}" | cut -f1)
echo "==> Done: rootfs.img (${SIZE} on disk, ${SIZE_MB}MB total)"
OUTER_EOF

exec docker run --rm \
    --privileged \
    -v "${OUTDIR_ABS}:/out" \
    -v "${INNER_SCRIPT}:/tmp/build.sh:ro" \
    -e HOME=/tmp \
    "${IMAGE_NAME}" \
    bash /tmp/build.sh
