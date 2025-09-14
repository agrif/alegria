import amaranth as am
import amaranth.lib.data
import amaranth.lib.fifo
import amaranth.lib.stream
import amaranth.lib.wiring
import amaranth.utils

from . import DataWithError, Framed

__all__ = ['Decoder', 'Encoder']

class Decoder(am.lib.wiring.Component):
    def __init__(self, data_width=8, max_block_size=None, error=am.unsigned(1)):
        if max_block_size is None:
            max_block_size = 2 ** data_width - 1

        if max_block_size > 2 ** data_width - 1:
            raise ValueError(f'max_block_size must be <= 2 ** data_width - 1')

        self.data_width = data_width
        self.max_block_size = max_block_size
        self.error = error
        self._frame_word = 0

        super().__init__({
            'i_data_with_error': am.lib.wiring.In(DataWithError(
                data_width, error=error)),
            'i_valid': am.lib.wiring.In(1),
            'i_ready': am.lib.wiring.Out(1),
            'o_data': am.lib.wiring.Out(Framed(data_width)),
            'o_valid': am.lib.wiring.Out(1),
            'o_ready': am.lib.wiring.In(1),
        })

    @property
    def i_data(self):
        return self.i_data_with_error.data

    @property
    def i_error(self):
        return self.i_data_with_error.error

    @property
    def i_stream_with_error(self):
        stream = am.lib.stream.Signature(self.i_data_with_error.shape()).flip().create()
        stream.payload = self.i_data_with_error
        stream.valid = self.i_valid
        stream.ready = self.i_ready
        return stream

    # does not work, am.lib.wiring.connect expects signals not slices
    #@property
    #def i_stream(self):
    #    stream = am.lib.stream.Signature(self.i_data.shape()).flip().create()
    #    stream.payload = self.i_data
    #    stream.valid = self.i_valid
    #    stream.ready = self.i_ready
    #    return stream

    @property
    def o_stream(self):
        stream = am.lib.stream.Signature(self.o_data.shape()).create()
        stream.payload = self.o_data
        stream.valid = self.o_valid
        stream.ready = self.o_ready
        return stream

    def elaborate(self, platform):
        m = am.Module()

        found_frame = am.Signal(1)
        insert_word = am.Signal(1)
        counter = am.Signal(range(self.max_block_size + 1))

        # always move data from in to out unless overwritten
        m.d.comb += self.o_data.data.eq(self.i_data)

        # counter always decrements on input word unless overwritten
        with m.If(self.i_ready):
            m.d.sync += counter.eq(counter - 1)

        with m.If(self.i_valid & self.i_error.any()):
            # input is valid, but has an error, reset and skip
            m.d.sync += found_frame.eq(0)
            m.d.comb += self.i_ready.eq(1)

        with m.Elif(self.i_valid & (self.i_data == self._frame_word)):
            # this is a new frame word, start over
            # push out a frame indicator
            m.d.comb += [
                self.o_data.frame.eq(1),
                self.o_valid.eq(1),
                self.i_ready.eq(self.o_ready),
            ]
            # if this is accepted, move on into the frame
            with m.If(self.o_ready):
                m.d.sync += [
                    found_frame.eq(1),
                    insert_word.eq(0),
                    counter.eq(0),
                ]

        with m.Elif(self.i_valid & found_frame):
            with m.If(counter > 0):
                # normal data word, push it out
                m.d.comb += [
                    self.o_valid.eq(1),
                    self.i_ready.eq(self.o_ready),
                ]

            with m.Else():
                # stuffed word
                with m.If(self.i_data > self.max_block_size):
                    # bad block size, we've lost the frame
                    m.d.sync += found_frame.eq(0)
                    # skip this word
                    m.d.comb += self.i_ready.eq(1)
                with m.Else():
                    # good block size, set counter when this word is consumed
                    with m.If(self.i_ready):
                        m.d.sync += [
                            insert_word.eq(self.i_data != self.max_block_size),
                            # -1 because the current word counts also
                            counter.eq(self.i_data - 1),
                        ]
                    # output a frame word here if requested
                    with m.If(insert_word):
                        m.d.comb += [
                            self.o_data.data.eq(self._frame_word),
                            self.o_valid.eq(1),
                            self.i_ready.eq(self.o_ready),
                        ]
                    with m.Else():
                        # no frame word needed, skip this word
                        m.d.comb += self.i_ready.eq(1)

        with m.Elif(self.i_valid):
            # outside of frames, skip it
            m.d.comb += self.i_ready.eq(1)

        return m

class Encoder(am.lib.wiring.Component):
    def __init__(self, data_width=8, max_block_size=None, frame_fifo_depth=4):
        if max_block_size is None:
            max_block_size = 2 ** data_width - 1

        if max_block_size > 2 ** data_width - 1:
            raise ValueError(f'max_block_size must be <= 2 ** data_width - 1')

        self.data_width = data_width
        self.max_block_size = max_block_size
        self.frame_fifo_depth = frame_fifo_depth
        self._frame_word = 0

        super().__init__({
            'i_data': am.lib.wiring.In(Framed(data_width)),
            'i_valid': am.lib.wiring.In(1),
            'i_ready': am.lib.wiring.Out(1),
            'o_data': am.lib.wiring.Out(data_width),
            'o_valid': am.lib.wiring.Out(1),
            'o_ready': am.lib.wiring.In(1),
        })

    @property
    def i_stream(self):
        stream = am.lib.stream.Signature(self.i_data.shape()).flip().create()
        stream.payload = self.i_data
        stream.valid = self.i_valid
        stream.ready = self.i_ready
        return stream

    @property
    def o_stream(self):
        stream = am.lib.stream.Signature(self.o_data.shape()).create()
        stream.payload = self.o_data
        stream.valid = self.o_valid
        stream.ready = self.o_ready
        return stream

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.data_fifo = data_fifo = am.lib.fifo.SyncFIFOBuffered(
            width=self.data_width, depth=self.max_block_size - 1)
        m.submodules.frame_fifo = frame_fifo = am.lib.fifo.SyncFIFOBuffered(
            width=am.utils.bits_for(self.max_block_size),
            depth=self.frame_fifo_depth)

        gather = am.Signal(range(self.max_block_size + 1))
        add_frame_word = am.Signal()
        last_chunk_max = am.Signal()
        drain = am.Signal(range(self.max_block_size + 1))

        # sane data connection defaults
        m.d.comb += [
            frame_fifo.w_data.eq(gather),
            data_fifo.w_data.eq(self.i_data.data),
            self.o_data.eq(data_fifo.r_data),
        ]

        with m.If(add_frame_word):
            # output a frame word, keep input
            m.d.comb += [
                frame_fifo.w_data.eq(self._frame_word),
                frame_fifo.w_en.eq(1),
            ]
            with m.If(frame_fifo.w_rdy):
                m.d.sync += [
                    gather.eq(0),
                    add_frame_word.eq(0),
                ]
        with m.Elif(self.i_valid):
            # gather words from input
            # common signal for gather + 1
            next_gather = gather + 1

            with m.If(self.i_data.frame | (self.i_data.data == self._frame_word)):
                # output a frame with size gather, consume input
                m.d.comb += [
                    frame_fifo.w_data.eq(gather),
                    frame_fifo.w_en.eq(1),
                    self.i_ready.eq(frame_fifo.w_rdy),
                ]
                # special case frame bit immediately after max chunk
                with m.If((gather == 1) & last_chunk_max & self.i_data.frame):
                    m.d.comb += frame_fifo.w_data.eq(self._frame_word)
                with m.If(self.i_ready):
                    m.d.sync += [
                        gather.eq(1),
                        add_frame_word.eq(self.i_data.frame & (frame_fifo.w_data != 0)),
                        last_chunk_max.eq(self.i_data.frame & last_chunk_max),
                    ]
            with m.Elif(next_gather == self.max_block_size):
                # output a frame with size max_block_size
                # push word into data_fifo
                both_ready = frame_fifo.w_rdy & data_fifo.w_rdy
                m.d.comb += [
                    frame_fifo.w_data.eq(self.max_block_size),
                    frame_fifo.w_en.eq(both_ready),
                    data_fifo.w_data.eq(self.i_data.data),
                    data_fifo.w_en.eq(both_ready),
                    self.i_ready.eq(both_ready),
                ]
                with m.If(both_ready):
                    m.d.sync += [
                        gather.eq(1),
                        last_chunk_max.eq(1),
                    ]
            with m.Else():
                # push a word into data_fifo, consume input
                m.d.comb += [
                    data_fifo.w_data.eq(self.i_data.data),
                    data_fifo.w_en.eq(1),
                    self.i_ready.eq(data_fifo.w_rdy),
                ]
                with m.If(self.i_ready):
                    m.d.sync += gather.eq(next_gather)

        # drain the frame fifo
        with m.If((drain == 0) & frame_fifo.r_rdy):
            # write the stuffed word
            m.d.comb += [
                self.o_data.eq(frame_fifo.r_data),
                self.o_valid.eq(1),
                frame_fifo.r_en.eq(self.o_ready),
            ]
            # drain (stuffed_word - 1) words from data_fifo
            with m.If(self.o_ready & (frame_fifo.r_data != self._frame_word)):
                m.d.sync += drain.eq(frame_fifo.r_data - 1)

        # drain the data fifo
        with m.If((drain > 0) & data_fifo.r_rdy):
            # output the data word
            m.d.comb += [
                self.o_data.eq(data_fifo.r_data),
                self.o_valid.eq(1),
                data_fifo.r_en.eq(self.o_ready),
            ]
            # on output, decrement drain
            with m.If(self.o_ready):
                m.d.sync += drain.eq(drain - 1)

        return m

if __name__ == '__main__':
    import click
    import alegria.cli

    cli = alegria.cli.CliBuilder(generate='generate')

    @click.option('--data-width', type=alegria.cli.BasedInt(), default=8,
                  show_default=True)
    @click.option('--max-block-size', type=alegria.cli.BasedInt())
    @click.option('--error', type=alegria.cli.BasedInt(), default=1)
    @cli.generate()
    def decoder(**kwargs):
        return Decoder(**kwargs)

    @click.option('--data-width', type=alegria.cli.BasedInt(), default=8,
                  show_default=True)
    @click.option('--max-block-size', type=alegria.cli.BasedInt())
    @click.option('--frame-fifo-depth', type=alegria.cli.BasedInt(), default=2)
    @cli.generate()
    def encoder(**kwargs):
        return Encoder(**kwargs)

    cli.run()
