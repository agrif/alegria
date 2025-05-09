import amaranth as am
import amaranth.vendor

import amaranth_boards.tang_nano_9k

class GowinPlatform(am.vendor.GowinPlatform):
    def __init__(self, *args, **kwargs):
        # alas, the open source toolchain can't really handle this
        if not 'toolchain' in kwargs:
            kwargs['toolchain'] = 'Gowin'

        super().__init__(*args, **kwargs)

    class _Pll_GW1NR_9C_C6I5(am.lib.wiring.Component):
        lock: am.lib.wiring.Out(1)

        def __init__(self, in_period, out_period, domain):
            self.in_period = in_period
            self.out_period = out_period
            self.domain = domain

            if abs(self.in_period.megahertz - 27) > 0.001:
                raise NotImplementedError('input frequency must be 27 MHz')
            if abs(self.out_period.megahertz - 7.375) > 0.005:
                raise NotImplementedError('output frequency must be 7.375 MHz')

            super().__init__()

        def elaborate(self, platform):
            assert platform.family == 'GW1NR-9C'
            assert platform.part.endswith('C6/I5')

            # https://juj.github.io/gowin_fpga_code_generators/pll_calculator.html
            # FCLKIN = 27 MHz
            # PFD = 3 MHz
            # CLKOUT = 177 MHz
            # VCO = 708 MHz
            # CLKOUTD = 7.375 MHz

            return am.Instance(
                'rPLL',
                p_FCLKIN="27",
                p_IDIV_SEL=8,
                p_FBDIV_SEL=58,
                p_DYN_SDIV_SEL=24,
                p_ODIV_SEL=4,
                i_CLKIN=am.ClockSignal(),
                o_CLKOUTD=am.ClockSignal(self.domain),
                o_LOCK=self.lock,
            )

    def generate_pll(self, in_period, out_period, domain):
        PLLMAP = {
            ('GW1NR-9C', 'C6/I5'): self._Pll_GW1NR_9C_C6I5,
        }

        for (family, part_end), Pll in PLLMAP.items():
            if self.family == family and self.part.endswith(part_end):
                return Pll(in_period, out_period, domain)

        raise NotImplementedError('no PLL found for {}'.format(self.part))

class TangNano9kPlatform(amaranth_boards.tang_nano_9k.TangNano9kPlatform, GowinPlatform):
    pass
