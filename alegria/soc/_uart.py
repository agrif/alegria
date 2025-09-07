import amaranth as am
import amaranth.lib.wiring
import amaranth_soc as amsoc
import amaranth_soc.csr

from .. import lib
from ..lib import uart

__all__ = ['Uart']

class Uart(am.lib.wiring.Component):
    class _Data(amsoc.csr.Register, access='rw'):
        read: amsoc.csr.Field(amsoc.csr.action.R, 8)
        write: amsoc.csr.Field(amsoc.csr.action.W, 8)

    class _Divisor(amsoc.csr.Register, access='rw'):
        value: amsoc.csr.Field(amsoc.csr.action.RW, 16)

    class _FifoLevel(amsoc.csr.Register, access='r'):
        current: amsoc.csr.Field(amsoc.csr.action.R, 8)

    class _FifoFlags(amsoc.csr.Register, access='r'):
        rx_ready: amsoc.csr.Field(amsoc.csr.action.R, 1)
        rx_empty: amsoc.csr.Field(amsoc.csr.action.R, 1)
        rx_half: amsoc.csr.Field(amsoc.csr.action.R, 1)
        rx_full: amsoc.csr.Field(amsoc.csr.action.R, 1)

        tx_ready: amsoc.csr.Field(amsoc.csr.action.R, 1)
        tx_empty: amsoc.csr.Field(amsoc.csr.action.R, 1)
        tx_half: amsoc.csr.Field(amsoc.csr.action.R, 1)
        tx_full: amsoc.csr.Field(amsoc.csr.action.R, 1)

    class _Format(amsoc.csr.Register, access='rw'):
        data_bits: amsoc.csr.Field(amsoc.csr.action.RW, 4, init=8)
        stop_bits: amsoc.csr.Field(amsoc.csr.action.RW, uart.StopBits,
                                   init=uart.StopBits.STOP_1)
        parity: amsoc.csr.Field(amsoc.csr.action.RW, uart.Parity,
                                init=uart.Parity.NONE)

    class _Error(amsoc.csr.Register, access='r'):
        framing: amsoc.csr.Field(amsoc.csr.action.R, 1)
        overrun: amsoc.csr.Field(amsoc.csr.action.R, 1)
        parity: amsoc.csr.Field(amsoc.csr.action.R, 1)

    def __init__(self, *, addr_width, data_width, fifo_depth=16):
        regs = amsoc.csr.Builder(addr_width=addr_width, data_width=data_width)

        if fifo_depth > 2 ** 8:
            raise ValueError(f'fifo_depth must be less than {2 ** 8}')

        self._max_bits = 8
        self._fifo_depth = fifo_depth

        self._data = regs.add('data', self._Data())
        self._divisor = regs.add('divisor', self._Divisor())
        self._rxlevel = regs.add('rxlevel', self._FifoLevel())
        self._txlevel = regs.add('txlevel', self._FifoLevel())
        self._fifo = regs.add('fifo', self._FifoFlags())
        self._format = regs.add('format', self._Format())
        self._error = regs.add('error', self._Error())

        super().__init__({
            'bus': am.lib.wiring.In(amsoc.csr.Signature(
                addr_width=addr_width, data_width=data_width)),
            'rx': am.lib.wiring.In(1),
            'tx': am.lib.wiring.Out(1),
        })

        self._bridge = amsoc.csr.Bridge(regs.as_memory_map())
        self.bus.memory_map = self._bridge.bus.memory_map

    def elaborate(self, platform):
        m = am.Module()

        m.submodules.bridge = self._bridge
        am.lib.wiring.connect(
            m, am.lib.wiring.flipped(self.bus), self._bridge.bus)

        # uart phys
        divisor_bits = len(self._divisor.f.value.data)
        m.submodules.rx = rx = uart.Rx(max_divisor=2 ** divisor_bits - 1)
        m.submodules.tx = tx = uart.Tx(max_divisor=2 ** divisor_bits - 1)

        m.d.comb += [
            # forward rx/tx lines
            rx.rx.eq(self.rx),
            self.tx.eq(tx.tx),

            # rts is true if rx fifo has space
            rx.rts.eq(~self._fifo.f.rx_full.r_data),

            # format
            rx.divisor.eq(self._divisor.f.value.data),
            rx.data_bits.eq(self._format.f.data_bits.data),
            rx.stop_bits.eq(self._format.f.stop_bits.data),
            rx.parity.eq(self._format.f.parity.data),

            tx.divisor.eq(self._divisor.f.value.data),
            tx.data_bits.eq(self._format.f.data_bits.data),
            tx.stop_bits.eq(self._format.f.stop_bits.data),
            tx.parity.eq(self._format.f.parity.data),
        ]

        # fifos
        m.submodules.rxfifo = rxfifo = am.lib.fifo.SyncFIFOBuffered(
            width=lib.DataWithError(self._max_bits, error=uart.RxError).size,
            depth=self._fifo_depth)
        m.submodules.txfifo = txfifo = am.lib.fifo.SyncFIFOBuffered(
            width=self._max_bits, depth=self._fifo_depth)

        # uart side
        am.lib.wiring.connect(m, rx.stream_with_error, rxfifo.w_stream)
        am.lib.wiring.connect(m, txfifo.r_stream, tx.stream)

        # register side
        m.d.comb += [
            self._rxlevel.f.current.r_data.eq(rxfifo.r_level),
            self._fifo.f.rx_ready.r_data.eq(rxfifo.r_rdy),
            self._fifo.f.rx_empty.r_data.eq(rxfifo.r_level == 0),
            self._fifo.f.rx_half.r_data.eq(
                rxfifo.r_level >= self._fifo_depth // 2),
            self._fifo.f.rx_full.r_data.eq(rxfifo.r_level == self._fifo_depth),

            self._txlevel.f.current.r_data.eq(txfifo.w_level),
            self._fifo.f.tx_ready.r_data.eq(txfifo.w_rdy),
            self._fifo.f.tx_empty.r_data.eq(txfifo.w_level == 0),
            self._fifo.f.tx_half.r_data.eq(
                txfifo.w_level >= self._fifo_depth // 2),
            self._fifo.f.tx_full.r_data.eq(txfifo.w_level == self._fifo_depth),
        ]

        # read register
        rxdata = lib.DataWithError(self._max_bits, error=uart.RxError)(
            rxfifo.r_data)
        m.d.comb += [
            rxfifo.r_en.eq(self._data.f.read.r_stb),
            self._data.f.read.r_data.eq(rxdata.data),
            self._error.f.framing.r_data.eq(
                rxfifo.r_rdy & rxdata.error.framing),
            self._error.f.overrun.r_data.eq(
                rxfifo.r_rdy & rxdata.error.overrun),
            self._error.f.parity.r_data.eq(
                rxfifo.r_rdy & rxdata.error.parity),
        ]

        # write register
        m.d.comb += [
            txfifo.w_data.eq(self._data.f.write.w_data),
            txfifo.w_en.eq(self._data.f.write.w_stb),
        ]

        return m
