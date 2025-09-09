import contextlib
import os
import sys
import unittest

import amaranth as am
import amaranth.sim

__all__ = ['SimulatorTestCase']

# cheeky way to sneak extra functionality in to test as needed
class Simulator(am.sim.Simulator):
    def __init__(self, *args, **kwargs):
        self._deadline_ignore = False
        super().__init__(*args, **kwargs)

    def reset_deadline(self) -> None:
        self._deadline_ignore = True

class SimulatorTestCase(unittest.TestCase):
    @contextlib.contextmanager
    def simulate(
            self, module, *,
            deadline=1000,
            deadline_domain='sync',
            traces=[],
            use_default_traces=True,
    ):
        if not isinstance(deadline, (am.Period, int)):
            raise TypeError('deadline must be a amaranth.Period or int')

        sim = Simulator(module)

        @sim.add_process
        async def deadline_checker(ctx):
            while True:
                # it would be nice to reset this wait whenever
                # reset_deadline() is called, but this is ok
                if isinstance(deadline, am.Period):
                    await ctx.delay(deadline)
                else:
                    await ctx.tick().repeat(deadline)
                if sim._deadline_ignore:
                    sim._deadline_ignore = False
                else:
                    self.fail('simulation deadline reached')

        yield sim

        if use_default_traces:
            traces = [
                am.Signal(name='top.clk'),
            ] + traces

        vcd = os.getenv('ALEGRIA_VCD')
        if vcd:
            name = self.id()
            os.makedirs(vcd, exist_ok=True)
            vcd_file = os.path.join(vcd, name + '.vcd')
            gtkw_file = os.path.join(vcd, name + '.gtkw')

            with sim.write_vcd(vcd_file, gtkw_file, traces=[] + traces):
                sim.run()
        else:
            sim.run()

    # from amaranth docs, helpers for streams
    @staticmethod
    async def stream_get(ctx, stream):
        ctx.set(stream.ready, 1)
        payload, = await ctx.tick().sample(stream.payload).until(stream.valid)
        ctx.set(stream.ready, 0)
        return payload

    @staticmethod
    async def stream_put(ctx, stream, payload):
        ctx.set(stream.valid, 1)
        ctx.set(stream.payload, payload)
        await ctx.tick().until(stream.ready)
        ctx.set(stream.valid, 0)
