#!/bin/sh
# Installed beside kernel-build/ and sysroots/ by the offline SDK bundle.
# Builds an external module only. Never installs/loads a module or updates config.
set -u
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 absolute-external-module-directory" >&2
    exit 2
fi
sdk_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P) || exit 2
module_root=$(realpath -e -- "$1") || exit 2
if [ ! -d "$module_root" ] || [ ! -f "$module_root/Makefile" ]; then
    echo "An existing external-module directory with Makefile is required" >&2
    exit 2
fi
case "$module_root" in
    *' '*|*'+'*|*'@'*|*'$'*) echo "Unsupported module path" >&2; exit 2 ;;
esac
cd "$sdk_root" || exit 2
sha256sum -c abi-inputs.sha256 >/dev/null || exit 1
cross="$sdk_root/sysroots/x86_64-pokysdk-linux/usr/bin/arm-poky-linux-gnueabi/arm-poky-linux-gnueabi-"
env -i HOME="${HOME:-/nonexistent}" LC_ALL=C \
    PATH="${cross%/*}:$sdk_root/sysroots/x86_64-pokysdk-linux/usr/bin:/usr/bin:/bin" \
    KCONFIG_NOSILENTUPDATE=1 \
    "$sdk_root/host-bin/make" -C "$sdk_root/kernel-build" \
    M="$module_root" ARCH=arm CROSS_COMPILE="$cross" HOSTCC=false HOSTCXX=false modules
result=$?
sha256sum -c abi-inputs.sha256 >/dev/null || exit 1
exit "$result"
