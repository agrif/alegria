import amaranth as am
import amaranth.build
import amaranth.lib.enum
import amaranth.lib.wiring
import amaranth.utils
import amaranth_soc as amsoc
import amaranth_soc.wishbone

from .. import lib
from ..lib import cobs
from ..lib import uart

__all__ = ['UartBridge']

class UartBridge(am.lib.wiring.Component):
    class _State(am.lib.enum.Enum):
        WAIT_START = am.lib.enum.auto()
        WAIT_END = am.lib.enum.auto()
        COMMAND = am.lib.enum.auto()

        RESET_SET = am.lib.enum.auto()

        READ_ADDRESS = am.lib.enum.auto()
        READ_LENGTH = am.lib.enum.auto()
        READ_LOAD = am.lib.enum.auto()
        READ_OUTPUT = am.lib.enum.auto()

        WRITE_ADDRESS = am.lib.enum.auto()
        WRITE_DATA = am.lib.enum.auto()
        WRITE_STORE = am.lib.enum.auto()
        WRITE_OUTPUT = am.lib.enum.auto()

    class Command(am.lib.enum.Enum):
        PING = 0
        ERROR = 1
        RESET = 2
        READ = 3
        WRITE = 4

    def __init__(self, *, addr_width, data_width, granularity=None,
                 features=frozenset(), fifo_depth=16, divisor=None,
                 stop_bits=uart.StopBits.STOP_1, parity=uart.Parity.NONE):

        if granularity is None:
            granularity = data_width

        self._addr_width = addr_width
        self._data_width = data_width
        self._features = frozenset(amsoc.wishbone.Feature(f) for f in features)
        self._fifo_depth = fifo_depth
        self._divisor = divisor
        self._stop_bits = stop_bits
        self._parity = parity

        # how many bits granularity occupies
        self._addr_align = am.utils.exact_log2(data_width // granularity)

        super().__init__({
            'bus': am.lib.wiring.Out(amsoc.wishbone.Signature(
                addr_width=addr_width, data_width=data_width,
                granularity=granularity, features=features)),
            'reset': am.lib.wiring.Out(1),
            'rx': am.lib.wiring.In(1),
            'tx': am.lib.wiring.Out(1),
        })

    def elaborate(self, platform):
        m = am.Module()

        # calculate a divisor for 115200 baud in the default case
        # (does not work if we're not running on default clock!)
        divisor = self._divisor
        if divisor is None:
            if isinstance(platform, am.build.Platform):
                divisor = int(round(platform.default_clk_period.hertz / 115200))

        if divisor is None:
            raise ValueError('could not guess divisor for uart')

        # uarts
        m.submodules.rx = rx = uart.Rx(max_divisor=divisor)
        m.submodules.tx = tx = uart.Tx(max_divisor=divisor)

        m.d.comb += [
            # forward rx/tx lines
            rx.rx.eq(self.rx),
            self.tx.eq(tx.tx),
            # configuration
            rx.divisor.eq(divisor),
            tx.divisor.eq(divisor),
            rx.data_bits.eq(8),
            tx.data_bits.eq(8),
            rx.stop_bits.eq(self._stop_bits),
            tx.stop_bits.eq(self._stop_bits),
            rx.parity.eq(self._parity),
            tx.parity.eq(self._parity),
        ]

        # cobs framing
        m.submodules.rxcobs = rxcobs = cobs.Decoder(error=uart.RxError)
        m.submodules.txcobs = txcobs = cobs.Encoder()

        # uart to cobs
        am.lib.wiring.connect(
            m, rx.stream_with_error, rxcobs.i_stream_with_error)
        am.lib.wiring.connect(m, txcobs.o_stream, tx.stream)

        # fifos
        m.submodules.rxfifo = rxfifo = am.lib.fifo.SyncFIFOBuffered(
            width=lib.Framed(8).size, depth=self._fifo_depth)
        m.submodules.txfifo = txfifo = am.lib.fifo.SyncFIFOBuffered(
            width=lib.Framed(8).size, depth=self._fifo_depth)

        # cobs to fifos
        am.lib.wiring.connect(m, rxcobs.o_stream, rxfifo.w_stream)
        am.lib.wiring.connect(m, txfifo.r_stream, txcobs.i_stream)

        # initial state
        state = am.Signal(self._State, init=self._State.WAIT_START)

        # address read in
        address = am.Signal(self._addr_width)
        address_byte = am.Signal(self._addr_align)

        # length read in, actually this is length - 1
        length = am.Signal(8)

        # data read in / storage
        data = am.Signal(self._data_width)
        data_byte = am.Signal(am.utils.exact_log2(self._data_width // 8))

        # aliases for incoming / outgoing streams
        i_data_framed = lib.Framed(8)(rxfifo.r_data)
        i_data = i_data_framed.data
        i_frame = i_data_framed.frame
        i_valid = rxfifo.r_stream.valid
        i_ready = rxfifo.r_stream.ready

        o_data_framed = lib.Framed(8)(txfifo.w_data)
        o_data = o_data_framed.data
        o_frame = o_data_framed.frame
        o_valid = txfifo.w_stream.valid
        o_ready = txfifo.w_stream.ready

        # reasonable defaults overridden below
        m.d.comb += [
            # we often copy data from i_data to o_data
            o_data.eq(i_data),
            # bus access are usually full-width, done at address
            self.bus.sel.eq(-1),
            self.bus.adr.eq(address),
            # when we write data it's from here
            self.bus.dat_w.eq(data),
        ]

        with m.Switch(state):
            with m.Case(self._State.WAIT_START):
                # eat input bytes until we find a frame start
                m.d.comb += i_ready.eq(1)
                with m.If(i_valid & i_frame):
                    # start output frame and transition to COMMAND on ready
                    m.d.comb += [
                        o_frame.eq(1),
                        o_valid.eq(1),
                        i_ready.eq(o_ready),
                    ]
                    with m.If(o_ready):
                        m.d.sync += state.eq(self._State.COMMAND)

            with m.Case(self._State.WAIT_END):
                # eat input bytes until we find a frame end
                m.d.comb += i_ready.eq(1)
                # frame end is handled in catch-all below

            with m.Case(self._State.COMMAND):
                # eat an input byte into command
                with m.If(i_valid & ~i_frame):
                    # figure out a response, case by case, and send it on ready
                    # then transition to next state
                    response = am.Signal(self.Command, init=self.Command.ERROR)
                    next_state = am.Signal(
                        self._State, init=self._State.WAIT_END)

                    m.d.comb += [
                        o_data.eq(response),
                        o_valid.eq(1),
                        i_ready.eq(o_ready),
                    ]
                    with m.If(o_ready):
                        m.d.sync += [
                            state.eq(next_state),
                            address_byte.eq(0),
                        ]

                    # case by case response
                    with m.Switch(i_data):
                        with m.Case(self.Command.PING):
                            m.d.comb += [
                                response.eq(self.Command.PING),
                                next_state.eq(self._State.WAIT_END),
                            ]
                        with m.Case(self.Command.RESET):
                            m.d.comb += [
                                response.eq(self.Command.RESET),
                                next_state.eq(self._State.RESET_SET),
                            ]
                        with m.Case(self.Command.READ):
                            m.d.comb += [
                                response.eq(self.Command.READ),
                                next_state.eq(self._State.READ_ADDRESS),
                            ]
                        with m.Case(self.Command.WRITE):
                            m.d.comb += [
                                response.eq(self.Command.WRITE),
                                next_state.eq(self._State.WRITE_ADDRESS),
                            ]

            with m.Case(self._State.RESET_SET):
                # copy flag out, set reset when ready
                with m.If(i_valid & ~i_frame):
                    m.d.comb += [
                        o_data.eq(i_data.any()),
                        o_valid.eq(1),
                        i_ready.eq(o_ready),
                    ]
                    with m.If(o_ready):
                        m.d.sync += [
                            self.reset.eq(i_data.any()),
                            state.eq(self._State.WAIT_END),
                        ]

            # double up, these states do basically the same thing
            with m.Case(self._State.READ_ADDRESS, self._State.WRITE_ADDRESS):
                # copy bytes out and read into address when ready
                with m.If(i_valid & ~i_frame):
                    m.d.comb += [
                        o_data.eq(i_data),
                        o_valid.eq(1),
                        i_ready.eq(o_ready),
                    ]
                    # if this is the first address byte, mask align bits
                    # in reply
                    with m.If(address_byte == 0):
                        m.d.comb += o_data[:self._addr_align].eq(0)
                    with m.If(o_ready):
                        m.d.sync += [
                            address_byte.eq(address_byte + 1),
                            address.eq(address >> 8),
                            address[-8:].eq(i_data),
                        ]
                        # if this is the last address byte, move on
                        with m.If(address_byte.all()):
                            with m.If(state.matches(self._State.READ_ADDRESS)):
                                m.d.sync += state.eq(self._State.READ_LENGTH)
                            with m.Else(): # WRITE_ADDRESS
                                m.d.sync += [
                                    state.eq(self._State.WRITE_DATA),
                                    length.eq(0),
                                    data_byte.eq(0),
                                ]

            with m.Case(self._State.READ_LENGTH):
                # read into length, do not copy out
                m.d.comb += i_ready.eq(1)
                with m.If(i_valid & ~i_frame):
                    m.d.sync += [
                        length.eq(i_data),
                        state.eq(self._State.READ_LOAD),
                    ]

            with m.Case(self._State.READ_LOAD):
                # read some data, continue on ack
                m.d.comb += [
                    self.bus.cyc.eq(1),
                    self.bus.stb.eq(1),
                    self.bus.we.eq(0),
                    self.bus.sel.eq(-1),
                    self.bus.adr.eq(address),
                ]
                with m.If(self.bus.ack):
                    m.d.sync += [
                        data.eq(self.bus.dat_r),
                        data_byte.eq(0),
                        state.eq(self._State.READ_OUTPUT),
                    ]

            with m.Case(self._State.READ_OUTPUT):
                # write a byte of data out and advance when ready
                m.d.comb += [
                    o_data.eq(data[:8]),
                    o_valid.eq(1),
                ]
                with m.If(o_ready):
                    m.d.sync += [
                        data.eq(data >> 8),
                        data_byte.eq(data_byte + 1),
                    ]
                    # if we're at the end, read another
                    with m.If(data_byte.all()):
                        m.d.sync += [
                            state.eq(self._State.READ_LOAD),
                            address.eq(address + 1),
                            length.eq(length - 1),
                        ]
                        # if no more addresses, end command
                        with m.If(length == 0):
                            m.d.sync += state.eq(self._State.WAIT_END)

            with m.Case(self._State.WRITE_DATA):
                # read into data, do not copy out
                with m.If(i_valid & i_frame):
                    # no more data, jump to end
                    m.d.sync += state.eq(self._State.WRITE_OUTPUT)
                # still more data
                with m.If(i_valid & ~i_frame):
                    m.d.comb += i_ready.eq(1)
                    m.d.sync += [
                        data_byte.eq(data_byte + 1),
                        data.eq(data >> 8),
                        data[-8:].eq(i_data),
                    ]
                    # if this is the last data byte, move on
                    with m.If(data_byte.all()):
                        m.d.sync += state.eq(self._State.WRITE_STORE)

            with m.Case(self._State.WRITE_STORE):
                # write some data, continue on ack
                m.d.comb += [
                    self.bus.cyc.eq(1),
                    self.bus.stb.eq(1),
                    self.bus.we.eq(1),
                    self.bus.sel.eq(-1),
                    self.bus.adr.eq(address),
                    self.bus.dat_w.eq(data),
                ]
                with m.If(self.bus.ack):
                    m.d.sync += [
                        state.eq(self._State.WRITE_DATA),
                        address.eq(address + 1),
                        length.eq(length + 1),
                    ]

            with m.Case(self._State.WRITE_OUTPUT):
                # write the amount written to output
                m.d.comb += [
                    o_data.eq(length),
                    o_valid.eq(1),
                ]
                with m.If(o_ready):
                    m.d.sync += state.eq(self._State.WAIT_END)

        # catch all frame boundaries in states that read from i_data
        # except WAIT_START and WRITE_DATA which both handle themselves
        with m.If(state.matches(
                self._State.WAIT_END, self._State.COMMAND,
                self._State.RESET_SET, self._State.READ_ADDRESS,
                self._State.READ_LENGTH, self._State.WRITE_ADDRESS)):

            with m.If(i_valid & i_frame):
                # end output frame and transition to WAIT_START on ready
                m.d.comb += [
                    o_frame.eq(1),
                    o_valid.eq(1),
                    i_ready.eq(o_ready),
                ]
                with m.If(o_ready):
                    m.d.sync += state.eq(self._State.WAIT_START)

        return m
