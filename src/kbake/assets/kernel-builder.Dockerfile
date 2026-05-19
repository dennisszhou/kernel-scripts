FROM fedora:latest

LABEL maintainer="kernel-builder"
LABEL description="Minimal Fedora image for Linux kernel builds"

RUN dnf install -y \
        make \
        gcc \
        bc \
        bison \
        flex \
        elfutils-libelf-devel \
        openssl-devel \
        findutils \
        diffutils \
        hostname \
        perl \
        ncurses-devel \
        dwarves \
        rsync \
        cpio \
        xz \
        e2fsprogs \
        btrfs-progs \
        busybox \
    && dnf clean all \
    && rm -rf /var/cache/dnf

WORKDIR /src

CMD ["/bin/bash"]
