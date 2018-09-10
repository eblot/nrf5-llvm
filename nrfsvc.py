#!/usr/bin/env python3

"""nRF5 service call adapter for CLANG/LLVM toolchain
"""

from argparse import ArgumentParser
from collections import namedtuple, OrderedDict
from os import environ, rename, walk
from os.path import (basename, dirname, isdir, join as joinpath, normpath,
                     relpath)
from re import compile as recompile
from subprocess import Popen, TimeoutExpired, PIPE
from sys import modules, stderr
from tempfile import mkstemp
from traceback import format_exc


# pylint: disable-msg=broad-except,invalid-name,broad-except
# pylint: disable-msg=too-many-branches,too-many-locals,too-many-statements


class NrfSysCall:
    """Patch nRF5 SVC for Clang.

       Patches are not Clang-specific, but rather fix improper SVC calls that
       GCC tolerates.

       In the original code, the proper clobber information is not given to the
       compiler, and Clang optimizer re-uses registers that are not properly
       declared as used, while GCC does not.
    """

    UPGRADE_MARKER = 'NRF_CLANG_SUPPORT'

    SVCRE = recompile(r'^\s*SVCALL\((?P<num>[A-Z_]+),\s'
                      r'(?P<rtype>[a-z][a-z_0-9]+),\s'
                      r'(?P<name>[a-z][a-z_0-9]+)\s*'
                      r'\((?P<args>.*)\)\);')
    MKCRE = recompile(r'^\s*#define %s' % UPGRADE_MARKER)

    FUNC = namedtuple('Func', ('rtype', 'name', 'args', 'line'))

    def __init__(self):
        self._calls = OrderedDict()

    def parse(self, fp):
        for nl, line in enumerate(fp, start=1):
            line = line.strip()
            if self.MKCRE.match(line):
                # do not account for already upgraded files
                return 0
            mo = self.SVCRE.match(line)
            if mo:
                num = mo.group('num')
                if num in self._calls:
                    raise ValueError('Redefinition of %s @ line %d' %
                                     (num, nl))
                args = tuple(arg.strip()
                             for arg in mo.group('args').split(','))
                self._calls[num] = self.FUNC(mo.group('rtype'),
                                             mo.group('name'),
                                             args,
                                             nl)
        return len(self._calls)

    def generate(self, fp, **kwargs):
        self._generate_header(fp, **kwargs)
        for num, func in self._calls.items():
            print('static inline %s' % func.rtype, file=fp)
            print('%s(%s) {' % (func.name, ', '.join(func.args)), file=fp)
            argnames = [arg.split()[-1].strip('*') for arg in func.args]
            if argnames[-1] == 'void':
                argnames.pop()
            argcount = len(argnames)
            if argcount > 4:
                raise ValueError('SVC calls limited to scratch registers')
            if argcount:
                print('   _SYSCALL%d(%s, %s);' %
                      (argcount, num, ', '.join(argnames)), file=fp)
            else:
                print('   _SYSCALL%d(%s);' % (argcount, num), file=fp)
            print('}', file=fp)
            print('', file=fp)
        self._generate_footer(fp, **kwargs)

    def _generate_header(self, fp, **kwargs):
        values = dict(self.__class__.__dict__)
        values.update(kwargs)
        header = """
#ifdef __clang__

#ifndef %(hprot)s
#define %(hprot)s

#ifdef __cplusplus
extern "C" {
#endif

// prevent from upgrading nRF52 header files more than once
#define %(UPGRADE_MARKER)s 1

// define system call macros only once
#ifndef _SYSCALL_ARGS

#define _SYSCALL_ARGS(_SC_, ...) \\
   __asm__ __volatile__ ( \\
      "svc %%[SC]" \\
         : "=r"(r0) : [SC]"I" ((uint16_t)_SC_), ##__VA_ARGS__ : "memory"); \\
   return r0; \\

#define _SCC(X) ((long) (X))

#define _SYSCALL0(_SC_) \\
   register long r0 __asm__("r0"); \\
   _SYSCALL_ARGS(_SC_); \\

#define _SYSCALL1(_SC_, _a_) \\
   register long r0 __asm__("r0") = _SCC(_a_); \\
   _SYSCALL_ARGS(_SC_, "0"(r0)); \\

#define _SYSCALL2(_SC_, _a_, _b_) \\
   register long r0 __asm__("r0") = _SCC(_a_); \\
   register long r1 __asm__("r1") = _SCC(_b_); \\
   _SYSCALL_ARGS(_SC_, "0"(r0), "r"(r1)); \\

#define _SYSCALL3(_SC_, _a_, _b_, _c_) \\
   register long r0 __asm__("r0") = _SCC(_a_); \\
   register long r1 __asm__("r1") = _SCC(_b_); \\
   register long r2 __asm__("r2") = _SCC(_c_); \\
   _SYSCALL_ARGS(_SC_, "0"(r0), "r"(r1), "r"(r2)); \\

#define _SYSCALL4(_SC_, _a_, _b_, _c_, _d_) \\
   register long r0 __asm__("r0") = _SCC(_a_); \\
   register long r1 __asm__("r1") = _SCC(_b_); \\
   register long r2 __asm__("r2") = _SCC(_c_); \\
   register long r3 __asm__("r3") = _SCC(_d_); \\
   _SYSCALL_ARGS(_SC_, "0"(r0), "r"(r1), "r"(r2), "r"(r3)); \\

#endif // SYSCALL_CP
""" % values
        print(header, file=fp)

    def _generate_footer(self, fp, **kwargs):
        footer = """
#ifdef __cplusplus
}
#endif

#endif // %(hprot)s

#endif // __clang__
""" % kwargs
        print(footer, file=fp)


class NrfSvcDef:
    """Patch SVCALL macro so that a static inline function is declared when
       Clang is in use.
    """

    CLANGCRE = recompile(r'^\s*#elif defined\(__clang__\)\s*$')

    PATCH = r"""
--- a/nrf_svc.h (revision 4491)
+++ b/nrf_svc.h (working copy)
@@ -52,6 +52,9 @@
 #ifndef SVCALL
 #if defined (__CC_ARM)
 #define SVCALL(number, return_type, signature) return_type __svc(number) signature
+#elif defined(__clang__)
+#define SVCALL(number, return_type, signature) \
+   static inline return_type signature;
 #elif defined (__GNUC__)
 #ifdef __cplusplus
 #define GCC_CAST_CPP (uint16_t)
""".lstrip('\n')

    def parse(self, filename: str):
        with open(filename, 'rt') as fp:
            for line in fp:
                line = line.strip()
                if self.CLANGCRE.match(line):
                    # do not account for already upgraded files
                    return False
        return True

    def apply(self, filename: str, dryrun: bool =False):
        environment = dict(environ)
        environment['LC_ALL'] = 'C'
        cwd = dirname(filename)
        args = ['patch', '-p1', '--no-backup-if-mismatch', '--silent',
                '--reject-file', '/dev/null']
        if dryrun:
            args.append('--dry-run')
        proc = Popen(args, stdin=PIPE, stdout=PIPE, env=environment,
                     cwd=cwd, universal_newlines=True)
        try:
            out, _ = proc.communicate(input=self.PATCH, timeout=2.0)
            print(out)
        except TimeoutExpired:
            proc.kill()


def main():
    """Main routine.

       Ths script is usually invoked twice, once to tweak the SVCALL macro
       definition for Clang, once to actually patch all the header files that
       declare SVC calls.

       The script tries to detect if a file has already been patched for Clang
       and skip if it does. No alteration to the source files is performed
       unless the "--update" option switch is used, i.e. the script may be
       safely invoked in dry-run mode.

       Always backup your original files before using this script in update
       mode (using a version control system such aas Git or SVN)!
    """

    debug = False
    kinds = {'svc': 'Patch CALLs', 'wrap': 'Patch SVCALL macros'}
    try:
        argparser = ArgumentParser(description=modules[__name__].__doc__)
        argparser.add_argument('dir', nargs=1,
                               help='top directory to seek for header files')
        argparser.add_argument('-u', '--update', action='store_true',
                               help='update source file')
        argparser.add_argument('-k', '--kind', choices=kinds, required=True,
                               help='Action to perform: %s' % ', '.join([
                                   '"%s": %s' % it for it in kinds.items()]))
        argparser.add_argument('-d', '--debug', action='store_true',
                               help='enable debug mode')
        args = argparser.parse_args()
        debug = args.debug

        topdir = args.dir[0]
        if not isdir(topdir):
            argparser.error('Invalid source directory')
        if args.kind == 'svc':
            for dirpath, dirnames, filenames in walk(topdir):
                dirnames[:] = [dn for dn in dirnames if not dn.startswith('.')]
                for fn in filenames:
                    if not fn.endswith('.h'):
                        continue
                    filename = normpath(joinpath(dirpath, fn))
                    count = 0
                    nrf = NrfSysCall()
                    with open(filename, 'rt') as hfp:
                        try:
                            count = nrf.parse(hfp)
                        except Exception:
                            print('Cannot parse file %s' % filename,
                                  file=stderr)
                            raise
                    if not count:
                        continue
                    if args.update:
                        print("Upgrade %s: %d syscalls" %
                              (relpath(filename), count), file=stderr)
                        hprot = '_CLANG_%s_' % \
                            basename(filename).upper().replace('.', '_')
                        with open(filename, 'rt') as ifp:
                            content = ifp.read()
                        # use a temporary filename to ensure file is only
                        # updated if it can be properly generated
                        ofd, ofname = mkstemp()
                        with open(ofd, 'wt') as ofp:
                            ofp.write(content)
                            nrf.generate(ofp, hprot=hprot)
                            ofp.close()
                        rename(ofname, filename)
                    else:
                        print("%s needs upgrade: %d syscalls" %
                              (relpath(filename), count), file=stderr)
        if args.kind == 'wrap':
            for dirpath, dirnames, filenames in walk(topdir):
                for fn in filenames:
                    if fn != 'nrf_svc.h':
                        continue
                    filename = normpath(joinpath(dirpath, fn))
                    nrf = NrfSvcDef()
                    if nrf.parse(filename):
                        if args.update:
                            print('Patching %s' % filename)
                        else:
                            print('%s needs upgrade' % filename)
                        nrf.apply(filename, not args.update)

    except Exception as e:
        print('\nError: %s' % e, file=stderr)
        if debug:
            print(format_exc(chain=False), file=stderr)
        exit(1)
    except KeyboardInterrupt:
        exit(2)


if __name__ == '__main__':
    main()
