import amaranth as am
import amaranth.lib.wiring

def bitwise_any(*signals):
    if not all(s.shape() == signals[0].shape() for s in signals):
        raise ValueError('all inputs must be the same shape')

    bits = [[s[i] for s in signals] for i in range(len(signals[0]))]

    return am.Cat(*[am.Cat(*b).any() for b in bits])

class RcMemoryBus(am.lib.wiring.Signature):
    def __init__(self, addr_width=16, data_width=8):
        self._addr_width = addr_width
        self._data_width = data_width
        super().__init__({
            'wait': am.lib.wiring.In(1),
            'mreq': am.lib.wiring.Out(1),
            'iorq': am.lib.wiring.Out(1),
            'rd': am.lib.wiring.Out(1),
            'wr': am.lib.wiring.Out(1),
            'addr': am.lib.wiring.Out(addr_width),
            'data_rd': am.lib.wiring.In(data_width),
            'data_rd_valid': am.lib.wiring.In(1),
            'data_wr': am.lib.wiring.Out(data_width),
        })

    @property
    def addr_width(self):
        return self._addr_width

    @property
    def data_width(self):
        return self._data_width

    def __eq__(self, other):
        return isinstance(other, RcMemoryBus) and self.addr_width == other.addr_width and self.data_width == other.data_width

    def __repr__(self):
        return f'RcMemoryBus(addr_width={self.addr_width}, data_width={self.data_width})'

class RcBus(am.lib.wiring.Signature):
    def __init__(self, addr_width=16, data_width=8):
        self._addr_width = addr_width
        self._data_width = data_width
        super().__init__({
            'm1': am.lib.wiring.Out(1),
            'rfsh': am.lib.wiring.Out(1),
            'halt': am.lib.wiring.Out(1),
            'int': am.lib.wiring.In(1),
            'nmi': am.lib.wiring.In(1),
            'busreq': am.lib.wiring.In(1),
            'busack': am.lib.wiring.Out(1),

            'memory': am.lib.wiring.Out(RcMemoryBus(addr_width=addr_width, data_width=data_width)),
            'memory_busreq': am.lib.wiring.In(RcMemoryBus(addr_width=addr_width, data_width=data_width)),
        })

    @property
    def addr_width(self):
        return self._addr_width

    @property
    def data_width(self):
        return self._data_width

    def __eq__(self, other):
        return isinstance(other, RcBus) and self.addr_width == other.addr_width and self.data_width == other.data_width

    def __repr__(self):
        return f'RcBus(addr_width={self.addr_width}, data_width={self.data_width})'

    def create(self, *, path=None, src_loc_at=0):
        return RcBusInterface(self, path=path, src_loc_at=1 + src_loc_at)

class RcBusInterface(am.lib.wiring.PureInterface):
    pass

class RcBusMultiplexer(am.lib.wiring.Component):
    def __init__(self, addr_width=16, data_width=8):
        self.devices = []
        super().__init__({
            'bus': am.lib.wiring.In(RcBus(addr_width=addr_width, data_width=data_width))
        })

    def add(self, device):
        if not isinstance(device.signature.flip(), RcBus):
            raise ValueError('devices added to bus must be In(RcBus(...))')
        if not device in self.devices:
            self.devices.append(device)

    def elaborate(self, platform):
        m = am.Module()

        if not self.devices:
            return m

        # gather device signals
        all_signals = {}
        mem_signals = {}
        for device in self.devices:
            for (path, flow, sig) in self.bus.signature.flatten(device):
                if path[0].startswith('memory'):
                    # only keep memory outputs
                    if flow.flow == am.lib.wiring.Out:
                        mem_signals.setdefault(path[1:], []).append(sig)
                
                all_signals.setdefault(path, []).append(sig)

        # add bus controller memory lines to mem_signals
        # flipped because we're inside elaborate
        for (path, flow, sig) in self.bus.signature.flip().flatten(self.bus):
            if path[0].startswith('memory'):
                if flow.flow == am.lib.wiring.Out:
                    mem_signals.setdefault(path[1:], []).append(sig)

        # bitwise-any together the memory signals
        mem_signals = {k: bitwise_any(*v) for k, v in mem_signals.items()}

        # flip signature because we're inside elaborate
        for (path, flow, sig) in self.bus.signature.flip().flatten(self.bus):
            if path[0].startswith('memory'):
                if flow.flow == am.lib.wiring.Out:
                    # memory outputs here is input on device
                    m.d.comb += [dsig.eq(mem_signals[path[1:]]) for dsig in all_signals[path]]
                else:
                    # memory inputs here is output on device
                    m.d.comb += sig.eq(mem_signals[path[1:]])
            else:
                # cpu signals
                if flow.flow == am.lib.wiring.Out:
                    # cpu outputs get copied to devices
                    m.d.comb += [dsig.eq(sig) for dsig in all_signals[path]]
                else:
                    # cpu inputs get or'd together
                    m.d.comb += sig.eq(bitwise_any(*all_signals[path]))

        return m
