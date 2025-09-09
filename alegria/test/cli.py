import os.path
import sys
import unittest
import warnings

from ._parallel import ParallelTextTestRunner

__all__ = [
    'TestProgram', 'main',
]

class TestProgram(unittest.TestProgram):
    def __init__(
            self,
            testRunner=None,
            parallel_level=ParallelTextTestRunner.Level.CASE,
            parallel_jobs=None,
            parallel_batch=1,
            vcd_directory=None,
            **kwargs):

        if testRunner is None:
            testRunner = ParallelTextTestRunner

        class TestRunnerInjector(testRunner):
            def __init__(runner_self, **kwargs):
                if self.vcd_directory is not None:
                    # something of a hack, keep in sync with _simulation.py
                    os.environ['ALEGRIA_VCD'] = self.vcd_directory

                super().__init__(
                    level=self.parallel_level,
                    processes=self.parallel_jobs,
                    chunksize=self.parallel_batch,
                    **kwargs,
                )

        self.parallel_level = parallel_level
        self.parallel_jobs = parallel_jobs
        self.parallel_batch = parallel_batch
        self.vcd_directory = vcd_directory
        super().__init__(
            testRunner=TestRunnerInjector,
            **kwargs,
        )

    def _getParentArgParser(self):
        parser = super()._getParentArgParser()

        choices = tuple(str(l) for l in ParallelTextTestRunner.Level)
        parser.add_argument('--parallel-level', dest='parallel_level',
                            metavar='LEVEL', choices=choices,
                            default=self.parallel_level,
                            help=f'Hierarchy level to parallelize at {choices!r}')
        parser.add_argument('-j', '--parallel-jobs', dest='parallel_jobs',
                            metavar='N', type=int, default=self.parallel_jobs,
                            help='Use N cores to do tests (default: all)')
        parser.add_argument('--parallel-batch', dest='parallel_batch',
                            metavar='N', type=int, default=self.parallel_batch,
                            help='Batch tests up N at a time')
        parser.add_argument('--write-vcds', dest='vcd_directory',
                            metavar='DIR', default=self.vcd_directory,
                            help='Write VCD waveforms to DIR')

        return parser

def main(replace_main=None, **kwargs):
    if replace_main:
        # dance to improve help text that unittest also does
        if sys.argv[0].endswith('__main__.py'):
            executable = os.path.basename(sys.executable)
            sys.argv[0] = executable + ' -m ' + replace_main

    TestProgram(**kwargs)
