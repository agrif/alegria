import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import alegria.platforms

__all__ = ['FormalTestCase']

class FormalTestCase(unittest.TestCase):
    def assertFormal(self, spec, **kwargs):
        platform = alegria.platforms.SymbiYosysPlatform(**kwargs)

        with tempfile.TemporaryDirectory(prefix='alegria.') as tmpdir:
            # do this somewhat manually so we can run quietly
            plan = platform.build(spec, do_build=False)
            build_dir = plan.extract(root=tmpdir)

            if sys.platform.startswith('win32'):
                args = ['cmd', '/c', f'call {plan.script}.bat']
            else:
                args = ['sh', f'{plan.script}.sh']

            with subprocess.Popen(args,
                                  cwd=build_dir, universal_newlines=True,
                                  stdout=subprocess.PIPE) as proc:
                stdout, _ = proc.communicate()
                if proc.returncode != 0:
                    msg = f'Formal verification failed:\n{stdout}'

                    # this may also be set in cli.py, with --write-vcds=...
                    vcd = os.getenv('ALEGRIA_VCD')
                    trace = build_dir / 'sby' / 'engine_0' / 'trace.vcd'
                    if trace.exists() and vcd:
                        name = self.id()
                        os.makedirs(vcd, exist_ok=True)
                        vcd_path = os.path.join(vcd, name + '.vcd')
                        shutil.copy(trace, vcd_path)
                        msg += f'\nTrace written to: {vcd_path}'

                    self.fail(msg)
