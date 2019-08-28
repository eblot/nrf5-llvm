# nrf5-llvm

Tools &amp; patches to build nRF5 SDK with LLVM/Clang toolchain

## Overview

This repository contains some tools and patches so that the Nordic Semi
[nRF5 SDK](https://www.nordicsemi.com/eng/Products/Bluetooth-low-energy/nRF5-SDK)
can be build with [Clang/LLVM](https://llvm.org) toolchain.

It has been succesfully tested (real product) with nRF5 SDK v14.2, SDK v15.3,
with SoftDevice S132 v5, v6 and v7 series.

It is used from LLVM 6.0 series and up to 8.0.0 for arm-none-eabi Cortex-M4
targets, i.e. with nRF52 SoCs. nRF51 has never been tested.

Thw whole toolchain, including the Clang compiler, the integrated assembler and
the LLVM linker `ld.lld` is used to build nRF52 executable.

Your mileage may vary!

## Important notice

The software is provided "as is", without warranty of any kind. Please read
the MIT license.

It is not affiliated in any way with Nordic Semiconductor, and obviously NOT
supported by Nordic Semiconductor. Be sure not to report issues that might be
introduced by the use of these tools to Nordic Semi.

The patches only tweak the files for the GCC toolchain, and try to be
conservative, *i.e.* patched files should execute in the exact same way when
GCC is used.

The patched SVC calls are only activated when Clang is actually used to build,
while some other fixes are also enabled when GCC is used.

In any case, it is strongly advised to backup your original SDK files before
applying these scripts. A source control system such as Git can help to check
which and how files have been modified.

Please also note that while these scripts enable building nRF52-based
applications, they may not be enough to build - all - applications. The author
has used them to build a BLE 4.x peripheral application with S132 SoftDevice
on a nRF52832 SoC. Patches are warmly welcomed!

## Requirements

* LLVM/Clang toolchain
  * v7+ is recommended, v8 is the preferred version.
* Python 3.5+ to run the scripts.
* `patch` and EOL-converter tool such as `dos2unix`
* Shell and common unix tools
* nRF5 SDK v14 or greater

## Tools

### `nrfsvc.py`

This tool patches some Nordic Semi header files to:

  * Declare SVCALL macro as a static inline function
  * Rewrite all SVCALLs to properly declare to the compiler which ARM registers
    are used with SVC calls.

        python3 nrfsvc.py -h

        usage: nrfsvc.py [-h] [-u] -k {svc,wrap} [-d] dir

        nRF5 service call adapter for CLANG/LLVM toolchain

        positional arguments:
          dir                   top directory to seek for header files

        optional arguments:
          -h, --help            show this help message and exit
          -u, --update          update source file
          -k {svc,wrap}, --kind {svc,wrap}
                                Action to perform: "svc": Patch CALLs, "wrap": Patch
                                SVCALL macros
          -d, --debug           enable debug mode

This script should be invoked twice:

* once to tweak the SVCALL macro definition for Clang (`wrap`)
* once to actually patch all the header files that declare SVC calls (`svc`).

The script walks through the specified SDK directory to detect header files
that need to be patched. It is not recommended to specify the top-level
directory of the SDK distribution archive as the start directory, as the script
would uselessly skim through the numerous examples files and third-party
libraries.

A good start point for patching SVC calls is to use the top-level SoftDevice
directory, *i.e.* `components/softdevice`.

### `nrfpatch.sh`

To successfully use the patch command, you may need to first convert the
original source file to Unix EOL using `dos2unix` file, apply the patch, then
optionally revert back to Windows format using `unix2dos` utility. The patch
utility has trouble working with the Windows EOL. Better: do not use Windows.

This script wraps up the patch files to apply them w/o dealing with EOL issues.

## Patches

The following patches need to be applied with the `patch` command.

Note that Nordic Semi distributes its SDK as Windows file: they use CRLF
line ending, and even source files may be defined as executable due to the
use of barely appropriate ZIP container.

* `vmsr.patch` this patch is a generic patch for modern GCCs and Clang for
  CMSIS header file. It is not specific to this SDK
* `isr_vector.patch` is used to declare the `isr_vector` section as executable.
  ISR vector is an array of addresses, *i.e* pure data, which is used by the
  Cortex-M4 as a jump table to exception routines. It is stored within the
  `.text`, *i.e.* executable code section. LLVM `ld.lld` does not accept
  mixed-style sections, *i.e.* executable and code within the same section
  declaration. It is right to do so, but this breaks most of the linker script
  designed for Cortex-M series. This patch declares the isr_vector jump table
  as executable as a workaround - the clean solution would be to rewrite all
  the LD linker scripts.
  Note that LLVM `ld.lld` may not safely detect this issue: depending on the
  content and order of all object files it is given to link as the final
  executable, various and hard-to-debug error messages may be raised, or even
  worse: the final executable may be invalid, LLVM LD failing to compute the
  LMA addressed for the `.data` section. Failing to fixing the isr_vector
  definition may result in quite difficult issues to track and debug. YMMV.
* `stack_ptr.h` fixes the retrieval of the current stack pointer value. Note
  that this patch lacks extensive testing.
* `error_handler.patch` fixes an ASM routine used to call the application
  error handler call. The original code generates a pseudo assembly instruction
  such as `ldr r0,=#1234`, but the LLVM integrated assembler does not accept
  the `=#` syntax as an immediate value. The instruction is replaced with two
  ARM `mov` instructions.
