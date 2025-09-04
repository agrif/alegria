import amaranth as am
import amaranth.vendor

class GowinPlatform(am.vendor.GowinPlatform):
    def __init__(self, *args, **kwargs):
        # alas, the open source toolchain can't really handle this
        if not 'toolchain' in kwargs:
            kwargs['toolchain'] = 'Gowin'

        super().__init__(*args, **kwargs)

    class _Pll(am.lib.wiring.Component):
        # this is similar to apycula.gowin_pll but we also handle
        # the final clock divider
        # see also:
        # https://juj.github.io/gowin_fpga_code_generators/pll_calculator.html

        lock: am.lib.wiring.Out(1)

        PLL_INFO = {
            ('GW1NR-9C', 'C6/I5'): {
                'pll_name': 'rPLL',
                'pfd': (3, 400),
                'clkout': (3.125, 600),
                'vco': (400, 1200),
            },
            ('GW2A-18C', 'C8/I7'): {
                'pll_name': 'rPLL',
                'pfd': (3, 500),
                'clkout': (3.90625, 625),
                'vco': (500, 1250),
            },
        }

        def __init__(self, platform, in_period, out_period, domain, max_ppm):
            self.in_period = in_period
            self.out_period = out_period
            self.domain = domain
            self.max_ppm = max_ppm
            self.ppm = None

            self._calculate_params(platform)

            super().__init__()

        def _calculate_params(self, platform):
            key = (platform.family, platform.speed)
            try:
                info = self.PLL_INFO[key]
            except KeyError:
                raise NotImplementedError('PLL not implemented for {!r}'.format(key))

            fclkin = self.in_period.megahertz
            params = None
            diff = None

            names = ['IDIV_SEL', 'pfd', 'FBDIV_SEL', 'clkout', 'ODIV_SEL', 'vco', 'DYN_SDIV_SEL', 'clkoutd']
            valids = (
                {n: locals()[n] for n in names}

                for IDIV_SEL in range(64)
                if info['pfd'][0] <= (pfd := fclkin / (IDIV_SEL + 1)) <= info['pfd'][1]

                for FBDIV_SEL in range(64)
                if info['clkout'][0] < (clkout := pfd * (FBDIV_SEL + 1)) < info['clkout'][1]

                for ODIV_SEL in range(2, 130, 2)
                if info['vco'][0] < (vco := clkout * ODIV_SEL) < info['vco'][1]

                # 0 stands in for "use clkout not clkoutd"
                for DYN_SDIV_SEL in range(0, 130, 2)
                for clkoutd in [clkout / max(DYN_SDIV_SEL, 1)]
            )

            for v in valids:
                new_params = info.copy()
                new_params.update(v)
                new_params.update({
                    'output': v['clkoutd'],
                    'output_signal': 'CLKOUTD',
                    'fclkin': fclkin,
                    'FCLKIN': '{:.6f}'.format(fclkin),
                })

                if v['DYN_SDIV_SEL'] == 0:
                    new_params.update({
                        'output': v['clkout'],
                        'output_signal': 'CLKOUT',
                    })

                    del new_params['DYN_SDIV_SEL']
                    del new_params['clkoutd']

                new_diff = abs((new_params['output'] / self.out_period.megahertz) - 1)
                if params is None or diff > new_diff:
                    params = new_params
                    diff = new_diff

            ppm = diff * 1e6
            if ppm > self.max_ppm:
                raise RuntimeError('PLL settings not found: wanted {:.6f}, best is {:.6f} ({:.0f} ppm)'.format(self.out_period.megahertz, params['output'], ppm))

            self._params = params
            self.out_period = am.Period(MHz=params['output'])
            self.ppm = ppm

        def elaborate(self, platform):
            args = {}
            for k in ['FCLKIN', 'IDIV_SEL', 'FBDIV_SEL', 'ODIV_SEL', 'DYN_SDIV_SEL']:
                args['p_' + k] = self._params[k]

            args['i_CLKIN'] = am.ClockSignal()
            args['o_' + self._params['output_signal']] = am.ClockSignal(self.domain)
            args['o_LOCK'] = self.lock

            m = am.Module()

            m.submodules.pll_impl = am.Instance(
                self._params['pll_name'],
                **args,
            )

            clk_out = am.Signal(name=self.domain)
            m.d.comb += clk_out.eq(am.ClockSignal(self.domain))
            platform.add_clock_constraint(clk_out, period=self.out_period)

            return m

    def generate_pll(self, in_period, out_period, domain, max_ppm=500):
        return self._Pll(self, in_period, out_period, domain, max_ppm)

    @classmethod
    def upgrade_platform(cls, plat):
        return type(plat.__name__, (plat, cls), {})
