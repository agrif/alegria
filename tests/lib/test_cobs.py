import amaranth as am
import cobs.cobs
from parameterized import parameterized, parameterized_class

from alegria.lib import DataWithError
from alegria.lib.cobs import *
from alegria.test import SimulatorTestCase

# cobs helpers
class CobsTestCase(SimulatorTestCase):
    TEST_PARAMS = [
        {'data_width': bits, 'max_block_size': block, 'write_delay': wd, 'read_delay': rd, 'header': h}
        for bits in [4, 8, 9]
        for block in [2**bits - 1, 2**bits // 2]
        for wd in [0, 10]
        for rd in [0, 10]
        for h in [0, 4]
    ]

    @classmethod
    def parameterized_class(cls, f):
        def name(cls, num, params_dict):
            return '_'.join([
                cls.__name__,
                str(num),
                'd' + parameterized.to_safe_name(params_dict['data_width']),
                'b' + parameterized.to_safe_name(params_dict['max_block_size']),
                'wd' + parameterized.to_safe_name(params_dict['write_delay']),
                'rd' + parameterized.to_safe_name(params_dict['read_delay']),
                'h' + parameterized.to_safe_name(params_dict['header']),
            ])
        return parameterized_class(cls.TEST_PARAMS, class_name_func=name)(f)

    def encoded_decoded(self, frames, header=None):
        if header is None:
            header = self.header

        header_words = []
        encoded = []
        decoded = []

        max_word = 2 ** self.data_width

        # turn frames into valid words
        for frame in frames:
            decoded.append([b % max_word for b in frame])

        # add a header with no zero bytes
        v = 0
        for _ in range(header):
            if v == 0:
                v += 1
            header_words.append(v)
            v += 1

        encoded += header_words

        # encode each frame
        for frame in decoded:
            encoded.append(0)

            try:
                next_stuff = min(frame.index(0), self.max_block_size - 1)
            except ValueError:
                next_stuff = self.max_block_size - 1
            next_stuff = min(next_stuff, len(frame))
            emit_zero = (next_stuff != self.max_block_size - 1)
            encoded.append(next_stuff + 1)

            i = 0
            while i < len(frame):
                b = frame[i]
                if i == next_stuff:
                    old_emit_zero = emit_zero
                    ahead = i + emit_zero
                    try:
                        next_stuff = min(frame[ahead:].index(0), self.max_block_size - 1)
                    except ValueError:
                        next_stuff = self.max_block_size - 1
                    next_stuff = min(next_stuff, len(frame[ahead:]))
                    emit_zero = (next_stuff != self.max_block_size - 1)
                    encoded.append(next_stuff + 1)
                    next_stuff += ahead

                    if old_emit_zero:
                        assert b == 0
                    else:
                        continue
                else:
                    encoded.append(b)

                i += 1

            encoded.append(0)

        # sanity check gainst cobs package
        if self.data_width == 8 and self.max_block_size == 255:
            ref_encoded = bytes(header_words)
            for frame in frames:
                ref_encoded += b'\x00' + cobs.cobs.encode(frame) + b'\x00'
            self.assertEqual(ref_encoded, bytes(encoded))

        return (encoded, decoded)

    async def frame_read(self, ctx, stream):
        frame = []
        in_frame = False
        while True:
            if self.read_delay:
                await ctx.tick().repeat(self.read_delay)
            v = await self.stream_get(ctx, stream)
            if not in_frame and v.frame:
                in_frame = True
                continue
            elif in_frame and v.frame:
                return frame
            else:
                frame.append(v.data)

    async def frame_write(self, ctx, stream, frame):
        if self.write_delay:
            await ctx.tick().repeat(self.write_delay)
        await self.stream_put(ctx, stream, {'data': 0, 'frame': 1})

        for v in frame:
            if self.write_delay:
                await ctx.tick().repeat(self.write_delay)
            await self.stream_put(ctx, stream, {'data': v, 'frame': 0})

        if self.write_delay:
            await ctx.tick().repeat(self.write_delay)
        await self.stream_put(ctx, stream, {'data': 0, 'frame': 1})

    def set_up_decoder(self, **kwargs):
        return Decoder(data_width=self.data_width, max_block_size=self.max_block_size, **kwargs)

    def set_up_encoder(self, **kwargs):
        return Encoder(data_width=self.data_width, max_block_size=self.max_block_size, **kwargs)

    def decoder_traces(self, dec):
        return [
            dec.i_stream,
            dec.o_stream,
        ]

    def encoder_traces(self, enc):
        return [
            enc.i_stream,
            enc.o_stream,
        ]

    def run_decoder_on(self, frames):
        dut = self.set_up_decoder()
        enc, dec = self.encoded_decoded(frames)
        with self.simulate(dut, traces=self.decoder_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=1_000_000))

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for b in enc:
                    if self.write_delay:
                        await ctx.tick().repeat(self.write_delay)
                    await self.stream_put(ctx, dut.i_stream, {'data': b, 'error': 0})

            @sim.add_testbench
            async def read(ctx):
                for frame in dec:
                    value = await self.frame_read(ctx, dut.o_stream)
                    self.assertEqual(value, frame)

    def run_encoder_on(self, frames):
        dut = self.set_up_encoder()
        enc, dec = self.encoded_decoded(frames, header=0)
        with self.simulate(dut, traces=self.encoder_traces(dut)) as sim:
            sim.add_clock(am.Period(Hz=1_000_000))

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for frame in dec:
                    await self.frame_write(ctx, dut.i_stream, frame)

            @sim.add_testbench
            async def read(ctx):
                for b in enc:
                    if self.read_delay:
                        await ctx.tick().repeat(self.read_delay)
                    value = await self.stream_get(ctx, dut.o_stream)
                    self.assertEqual(value, b)

    def run_encoder_decoder_on(self, frames):
        dut = am.Module()
        dut.submodules.encoder = dut_enc = self.set_up_encoder()
        dut.submodules.decoder = dut_dec = self.set_up_decoder(error=0)
        am.lib.wiring.connect(dut, dut_enc.o_stream, dut_dec.i_stream)
        enc, dec = self.encoded_decoded(frames, header=0)
        traces = self.encoder_traces(dut_enc) + self.decoder_traces(dut_dec)
        with self.simulate(dut, traces=traces) as sim:
            sim.add_clock(am.Period(Hz=1_000_000))

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for frame in dec:
                    await self.frame_write(ctx, dut_enc.i_stream, frame)

            @sim.add_testbench
            async def read(ctx):
                for frame in dec:
                    value = await self.frame_read(ctx, dut_dec.o_stream)
                    self.assertEqual(value, frame)

    def run_decoder_encoder_on(self, frames):
        dut = am.Module()
        dut.submodules.encoder = dut_enc = self.set_up_encoder()
        dut.submodules.decoder = dut_dec = self.set_up_decoder()
        am.lib.wiring.connect(dut, dut_dec.o_stream, dut_enc.i_stream)
        enc, dec = self.encoded_decoded(frames)
        traces = self.decoder_traces(dut_dec) + self.encoder_traces(dut_enc)
        with self.simulate(dut, traces=traces) as sim:
            sim.add_clock(am.Period(Hz=1_000_000))

            @sim.add_testbench
            async def write(ctx):
                await ctx.tick().repeat(3)

                for b in enc:
                    if self.write_delay:
                        await ctx.tick().repeat(self.write_delay)
                    await self.stream_put(ctx, dut_dec.i_stream, {'data': b, 'error': 0})

            @sim.add_testbench
            async def read(ctx):
                for b in enc[self.header:]:
                    if self.read_delay:
                        await ctx.tick().repeat(self.read_delay)
                    value = await self.stream_get(ctx, dut_enc.o_stream)
                    self.assertEqual(value, b)

@CobsTestCase.parameterized_class
class TestCobs(CobsTestCase):
    def test_decoder(self):
        self.run_decoder_on([b'Hello'])

    def test_encoder(self):
        self.run_encoder_on([b'Hello'])

    def test_decoder_zero(self):
        self.run_decoder_on([b'Hel\x00lo'])

    def test_encoder_zero(self):
        self.run_encoder_on([b'Hel\x00lo'])

    def test_decoder_all_zero(self):
        self.run_decoder_on([b'\x00' * 5])

    def test_encoder_all_zero(self):
        self.run_encoder_on([b'\x00' * 5])

    def test_decoder_many(self):
        self.run_decoder_on([b'Hello', b'Wo\x00rld', b'\x00\x00\x00'])

    def test_encoder_many(self):
        self.run_encoder_on([b'Hello', b'Wo\x00rld', b'\x00\x00\x00'])

    def test_decoder_max(self):
        self.run_decoder_on([b'a' * (self.max_block_size - 1)])

    def test_encoder_max(self):
        self.run_encoder_on([b'a' * (self.max_block_size - 1)])

    def test_decoder_max_zero(self):
        self.run_decoder_on([b'a' * (self.max_block_size - 1) + b'\x00'])

    def test_encoder_max_zero(self):
        self.run_encoder_on([b'a' * (self.max_block_size - 1) + b'\x00'])

    def test_decoder_max_zero_extra(self):
        self.run_decoder_on([b'a' * (self.max_block_size - 1) + b'\x00bb'])

    def test_encoder_max_zero_extra(self):
        self.run_encoder_on([b'a' * (self.max_block_size - 1) + b'\x00bb'])

    def test_decoder_long(self):
        self.run_decoder_on([b'a' * (self.max_block_size + 10)])

    def test_encoder_long(self):
        self.run_encoder_on([b'a' * (self.max_block_size + 10)])

    def test_decoder_long_zero(self):
        self.run_decoder_on([b'a' * (self.max_block_size - 1) + b'bbb\x00c'])

    def test_encoder_long_zero(self):
        self.run_encoder_on([b'a' * (self.max_block_size - 1) + b'bbb\x00c'])

    def test_encoder_decoder(self):
        self.run_encoder_decoder_on([
            b'Hello',
            b'Wo\00rld',
            b'a' * (self.max_block_size - 1),
            b'a' * (self.max_block_size - 1) + b'\x00',
            b'a' * (self.max_block_size - 1) + b'\x00bb',
            b'a' * (self.max_block_size - 1) + b'bbb\x00c',
        ])

    def test_decoder_encoder(self):
        self.run_decoder_encoder_on([
            b'Hello',
            b'Wo\00rld',
            b'a' * (self.max_block_size - 1),
            b'a' * (self.max_block_size - 1) + b'\x00',
            b'a' * (self.max_block_size - 1) + b'\x00bb',
            b'a' * (self.max_block_size - 1) + b'bbb\x00c',
        ])
