import contextlib
import os
import sys
import unittest

import amaranth as am
import amaranth.sim

__all__ = ['SimulatorTestCase']

class SimulatorTestCase(unittest.TestCase):
    @contextlib.contextmanager
    def simulate(self, module, *, deadline=None, traces=[], use_default_traces=True):
        sim = am.sim.Simulator(module)
        yield sim

        def run():
            if deadline is None:
                sim.run()
            else:
                sim.run_until(deadline)

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
                run()
        else:
            run()

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
