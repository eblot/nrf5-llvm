#!/bin/sh

# Show usage information
usage() {
    NAME=$(basename $0)
    cat <<EOT
$NAME [-l] <sdkdir>

  Apply the nRF5 SDK patches to enable LLVM/Clang toolchain build.

    -h       Print this help message
    -l       Do not revert to Windows EOL (CRLF) after applying patch

    sdkdir   Path to the top-level nRF5 SDK directory.
EOT
}

# Die with an error message
die() {
    echo "" >&2
    echo "$*" >&2
    exit 1
}

# Parse command line arguments
SDKDIR=""
UNIX2DOS=1
while [ $# -gt 0 ]; do
    case $1 in
        -h)
            usage
            exit 0
            ;;
        -l)
            UNIX2DOS=0
            ;;
        -*)
            die "Unknown option $1"
            ;;
        *)
            [ -z "${SDKDIR}" ] && SDKDIR=$1
            [ -d "${SDKDIR}" ] || die "Invalid SDK directory"
            ;;
    esac
    shift
done

# test for SDK directory
[ -z "${SDKDIR}" ] && die "Missing SDK directory"

# test for required tools
[ -z "$(which patch 2>/dev/null)" ] && die "Missing patch tool"
[ -z "$(which dos2unix 2>/dev/null)" ] && die "Missing dos2unix tool"
[ ${UNIX2DOS} -ne 0 ] && [ -z "$(which unix2dos 2>/dev/null)" ] && \
    die "Missing unix2dos tool"

PDIR="$(cd $(dirname $0) && pwd)"
for pch in $(cd "${PDIR}" && ls -1 *.patch); do
    echo "Applying patch $pch"
    srcs=`grep '^+++' ""${PDIR}"/${pch}" | cut -d' ' -f2 | cut -c3-`
    (cd "${SDKDIR}"; dos2unix -q ${srcs})
    (cd "${SDKDIR}"; patch --no-backup-if-mismatch -p1 < "${PDIR}/${pch}");
    RC=$?
    [ ${UNIX2DOS} -ne 0 ] && (cd "${SDKDIR}"; unix2dos -q ${srcs})
    [ ${RC} -ne 0 ] && die ""
done
