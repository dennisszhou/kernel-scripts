FROM fedora:latest

LABEL maintainer="kernel-builder"
LABEL description="Minimal Fedora image for Linux kernel builds"

# Install the minimum set of packages needed to build the kernel
RUN dnf install -y \
        # Core build tools
        make \
        gcc \
        bc \
        bison \
        flex \
        # Headers & libs
        elfutils-libelf-devel \
        openssl-devel \
        # Utilities used by kbuild
        findutils \
        diffutils \
        hostname \
        perl \
        # Optional but commonly needed
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

# Default working directory — the kernel source gets mounted here
WORKDIR /src

# Default to an interactive shell
CMD ["/bin/bash"]
