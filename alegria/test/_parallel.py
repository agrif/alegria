import enum
import functools
import multiprocessing
import sys
import time
import unittest
import warnings

# used only to silence UnusedElaboratable
import amaranth as am

__all__ = [
    'ParallelTextTestResult', 'ParallelTextTestRunner',
]

# unfortunately, locks must be passed through during process creation
# to use them in a pool, we need a global
_mp_stream_lock = None
def _initialize_pool(lock, install_handler):
    global _mp_stream_lock, _mp_stream
    _mp_stream_lock = lock
    if install_handler:
        unittest.installHandler()

def _make_lock_before_io(cls, io_functions=None, extra=[]):
    members = {}

    if io_functions is None:
        io_functions = [
            'printErrors',
            'printErrorList',
            'startTest',
            'startTestRun',
            'stopTest',
            'stopTestRun',
            'addError',
            'addFailure',
            'addSubTest',
            'addSuccess',
            'addSkip',
            'addExpectedFailure',
            'addUnexpectedSuccess',
        ] + extra

    for func in io_functions:
        # need to make sure func doesn't keep changing in this loop
        def _make_inner(func):
            @functools.wraps(getattr(cls, func))
            def _inner(self, *args, **kwargs):
                global _mp_stream_lock
                original = getattr(cls, func)
                if _mp_stream_lock is None:
                    original(self, *args, **kwargs)
                else:
                    with _mp_stream_lock:
                        original(self, *args, **kwargs)
            return _inner
        members[func] = _make_inner(func)

    return type(cls.__name__, (cls,), members)

# to avoid using internal unittest classes
class _WritelnDecorator:
    """Used to decorate file-like objects with a handy 'writeln' method"""
    def __init__(self,stream):
        self.stream = stream

    def __getattr__(self, attr):
        if attr in ('stream', '__getstate__'):
            raise AttributeError(attr)
        return getattr(self.stream,attr)

    def writeln(self, arg=None):
        if arg:
            self.write(arg)
        self.write('\n') # text-mode streams translate to \r\n if needed

@_make_lock_before_io
class ParallelTextTestResult(unittest.TextTestResult):
    def __getstate__(self):
        # these attributes, in general, are unpickleable
        try:
            orig_stream = self.stream.stream
        except AttributeError:
            orig_stream = self.stream

        assert orig_stream is sys.stderr

        state = self.__dict__.copy()
        del state['stream']
        del state['_original_stdout']
        del state['_original_stderr']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)

        # restore unpickleable attributes
        self.stream = _WritelnDecorator(sys.stderr)
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

    def _combine(self, other):
        self.failures += other.failures
        self.errors += other.errors
        self.testsRun += other.testsRun
        self.skipped += other.skipped
        self.expectedFailures += other.expectedFailures
        self.unexpectedSuccesses += other.unexpectedSuccesses
        self.collectedDurations += other.collectedDurations
        self.shouldStop |= other.shouldStop

class ParallelTextTestRunner(unittest.TextTestRunner):
    resultclass = ParallelTextTestResult

    class Level(enum.StrEnum):
        CASE = enum.auto()
        SUITE = enum.auto()
        MODULE = enum.auto()

        def iter_tests(self, test):
            if self == self.CASE:
                if isinstance(test, unittest.TestCase):
                    yield test
                else:
                    for subtest in test:
                        yield from self.iter_tests(subtest)
            elif self == self.SUITE:
                has_cases = any(isinstance(subtest, unittest.TestCase) for subtest in test)
                if has_cases:
                    yield test
                else:
                    for subtest in test:
                        yield from self.iter_tests(subtest)
            elif self == self.MODULE:
                for subtest in test:
                    if subtest.countTestCases():
                        yield subtest
            else:
                raise NotImplementedError(self)

    def __init__(self, level=Level.CASE, processes=None, chunksize=1, **kwargs):
        self._level = self.Level(level)
        self._processes = processes
        self._mp_context = multiprocessing.get_context(method='spawn')
        self._chunksize = chunksize
        super().__init__(**kwargs)

    def run(self, test):
        "Run the given test case or test suite."
        result = self._makeResult()
        unittest.registerResult(result)
        result.failfast = self.failfast
        result.buffer = self.buffer
        result.tb_locals = self.tb_locals

        startTime = time.perf_counter()
        mp_lock = self._mp_context.RLock()
        # this is internal, but also by far the easiest place to read this
        install_handler = unittest.signals._interrupt_handler is not None
        with self._mp_context.Pool(
                processes=self._processes,
                initializer=_initialize_pool,
                initargs=(mp_lock, install_handler),
        ) as pool:
            subtests = self._level.iter_tests(test)
            subresults = pool.imap_unordered(
                self._run_one,
                (self._run_one_args(subtest) for subtest in subtests),
                chunksize=self._chunksize,
            )
            for subresult in subresults:
                result._combine(subresult)
                if result.shouldStop:
                    break
        stopTime = time.perf_counter()

        return self._run_summary(result, stopTime - startTime)

    def _run_one_args(self, test):
        result = self._makeResult()
        result.failfast = self.failfast
        result.buffer = self.buffer
        result.tb_locals = self.tb_locals

        return {
            'result': result,
            'test': test,
            'warnings': self.warnings,
        }

    @staticmethod
    def _run_one(args):
        test = args['test']
        result = args['result']
        unittest.registerResult(result)

        with warnings.catch_warnings():
            if args['warnings']:
                warnings.simplefilter(args['warnings'])
                # our *one* amaranth-specific concession in this file
                warnings.simplefilter('ignore', category=am.UnusedElaboratable)
            startTestRun = getattr(result, 'startTestRun', None)
            if startTestRun is not None:
                startTestRun()
            try:
                test(result)
            finally:
                stopTestRun = getattr(result, 'stopTestRun', None)
                if stopTestRun is not None:
                    stopTestRun()

        return result

    def _run_summary(self, result, timeTaken):
        result.printErrors()
        if self.durations is not None:
            self._printDurations(result)

        if hasattr(result, 'separator2'):
            self.stream.writeln(result.separator2)

        run = result.testsRun
        self.stream.writeln("Ran %d test%s in %.3fs" %
                            (run, run != 1 and "s" or "", timeTaken))
        self.stream.writeln()

        expectedFails = unexpectedSuccesses = skipped = 0
        try:
            results = map(len, (result.expectedFailures,
                                result.unexpectedSuccesses,
                                result.skipped))
        except AttributeError:
            pass
        else:
            expectedFails, unexpectedSuccesses, skipped = results

        infos = []
        if not result.wasSuccessful():
            self.stream.write("FAILED")
            failed, errored = len(result.failures), len(result.errors)
            if failed:
                infos.append("failures=%d" % failed)
            if errored:
                infos.append("errors=%d" % errored)
        elif run == 0 and not skipped:
            self.stream.write("NO TESTS RAN")
        else:
            self.stream.write("OK")
        if skipped:
            infos.append("skipped=%d" % skipped)
        if expectedFails:
            infos.append("expected failures=%d" % expectedFails)
        if unexpectedSuccesses:
            infos.append("unexpected successes=%d" % unexpectedSuccesses)
        if infos:
            self.stream.writeln(" (%s)" % (", ".join(infos),))
        else:
            self.stream.write("\n")
        self.stream.flush()
        return result
