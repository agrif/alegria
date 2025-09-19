import functools
import io
import struct
import subprocess
import sys
import time

import click
import cobs.cobs
from elftools.elf.elffile import ELFFile
import serial

import alegria.cli
import alegria.soc

__all__ = ['Bridge', 'SerialBridge', 'ProcessBridge']

class Bridge:
    Command = alegria.soc.UartBridge.Command

    def __init__(self, debug=False):
        self._received = b''
        self._debug = debug
        self._read_size = 0x100
        self._write_size = 0xff
        self.word_size = 4
        self.word_bits = 32

    def close(self):
        raise NotImplementedError

    def read_raw(self):
        raise NotImplementedError

    def write_raw(self, data):
        raise NotImplementedError

    def __enter__(self):
        return self

    def __exit__(self, typ, value, traceback):
        self.close()

    def trace(self, msg, **kwargs):
        if self._debug:
            print(msg, file=sys.stderr, **kwargs)

    def read_frame(self):
        while True:
            if len(self._received) >= 2:
                if self._received[0] == 0  and 0 in self._received[1:]:
                    frame, self._received = self._received[1:].split(b'\x00', 1)
                    if frame:
                        decoded = cobs.cobs.decode(frame)
                        self.trace(f'<<< {decoded}')
                        if decoded and decoded[0] == self.Command.ERROR:
                            # error
                            raise RuntimeError('bridge reported error')
                        return decoded

            # no frame found, gather data
            self._received += self.read_raw()

            # discard any data before the first 0
            first = self._received.find(0)
            if first < 0:
                self._received = b''
            else:
                self._received = self._received[first:]

    def write_frame(self, frame):
        self.trace(f'>>> {frame}')
        self.write_raw(b'\x00' + cobs.cobs.encode(frame) + b'\x00')

    def read_struct(self, fmt):
        return struct.unpack('<' + fmt, self.read_frame())

    def write_struct(self, fmt, *args):
        self.write_frame(struct.pack('<' + fmt, *args))

    def call(self, command, r_fmt, w_fmt, *args):
        cval = getattr(command, 'value', command)
        try:
            self.write_struct('B' + w_fmt, cval, *args)
        except struct.error:
            raise RuntimeError(f'bad arguments to {command}')
        try:
            (rcmd, *rest) = self.read_struct('B' + r_fmt)
        except struct.error:
            raise RuntimeError(f'bad response to {command}')
        if rcmd != cval:
            raise RuntimeError(f'bad response to {command}')
        return rest

    def ping(self):
        self.call(self.Command.PING, '', '')

    def reset(self, value):
        value = 1 if value else 0
        rval, = self.call(self.Command.RESET, 'B', 'B', value)
        if rval != value:
            raise RuntimeError(f'bad response to {self.Command.RESET}')

    def read_words(self, address, amount):
        words = []
        for chunk in self.read_words_in_chunks(address, amount):
            words += chunk
        return words

    def read_words_in_chunks(self, address, amount):
        if not address % self.word_size == 0:
            raise ValueError(f'address must be aligned to {self.word_bits} bits')

        while amount > 0:
            size = min(amount, self._read_size)
            size_bytes = size * self.word_size
            raddr, *chunk = self.call(
                self.Command.READ, f'I{size}I', 'IB', address, size - 1)
            if raddr != address or len(chunk) != size:
                raise RuntimeError(f'bad response to {self.Command.READ}')

            address += size_bytes
            amount -= size
            yield chunk

    def read_bytes(self, address, amount):
        data = b''
        for chunk in self.read_bytes_in_chunks(address, amount):
            data += chunk
        return data

    def read_bytes_in_chunks(self, address, amount):
        if not address % self.word_size == 0:
            raise ValueError(f'address must be aligned to {self.word_bits} bits')
        if not amount % self.word_size == 0:
            raise ValueError(f'must read a multiple of {self.word_size} bytes')
        amount = amount // self.word_size

        while amount > 0:
            size = min(amount, self._read_size)
            size_bytes = size * self.word_size
            raddr, chunk = self.call(
                self.Command.READ, f'I{size_bytes}s', 'IB', address, size - 1)
            if raddr != address or len(chunk) != size_bytes:
                raise RuntimeError(f'bad response to {self.Command.READ}')

            address += size_bytes
            amount -= size
            yield chunk

    def write_words(self, address, words):
        self.write_words_in_chunks(address, [words])

    def write_words_in_chunks(self, address, word_chunks):
        if not address % self.word_size == 0:
            raise ValueError(f'address must be aligned to {self.word_bits} bits')

        for words in word_chunks:
            while words:
                chunk, words = words[:self._write_size], words[self._write_size:]
                waddr, amt = self.call(
                    self.Command.WRITE, 'IB', f'I{len(chunk)}I', address, *chunk)
                if waddr != address or amt != len(chunk) % 0x100:
                    raise RuntimeError(f'bad response to {self.Command.WRITE}')

                address += len(chunk) * self.word_size

    def write_bytes(self, address, data):
        if not len(data) % self.word_size == 0:
            raise ValueError(f'must write a multiple of {self.word_size} bytes')

        self.write_bytes_in_chunks(address, [data])

    # note: will pad end with zeros to make it work
    def write_bytes_in_chunks(self, address, data_chunks):
        if not address % self.word_size == 0:
            raise ValueError(f'address must be aligned to {self.word_bits} bits')

        data = b''
        data_chunks = iter(data_chunks)
        while True:
            last = False
            try:
                data += bytes(next(data_chunks))
            except StopIteration:
                last = True
                # fill in end with zeros to word_size
                while len(data) % self.word_size != 0:
                    data += b'\x00'

            wanted_size = self.word_size * (1 if last else self._write_size)
            while len(data) >= wanted_size:
                in_words = min(self._write_size, len(data) // self.word_size)
                split = in_words * self.word_size
                chunk, data = data[:split], data[split:]
                waddr, amt = self.call(
                    self.Command.WRITE, 'IB', f'I{len(chunk)}s', address, chunk)
                if waddr != address or amt != in_words % 0x100:
                    raise RuntimeError(f'bad response to {self.Command.WRITE}')

                address += len(chunk)

            if last:
                assert len(data) == 0
                break

class SerialBridge(Bridge):
    def __init__(self, port, baud=1_000_000, debug=False):
        self._port = serial.Serial(port, baud, timeout=0)
        super().__init__(debug=debug)

    def close(self):
        self._port.close()

    def read_raw(self):
        data = self._port.read(256)
        # anti busy-loop
        if len(data) == 0:
            time.sleep(0.1)
        return data

    def write_raw(self, data):
        self._port.write(data)

class ProcessBridge(Bridge):
    def __init__(self, args, debug=False):
        self._proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        super().__init__(debug=debug)

    def close(self):
        self._proc.terminate()
        self._proc.wait()

    def read_raw(self):
        # FIXME more efficient reads, maybe
        return self._proc.stdout.read(1)

    def write_raw(self, data):
        self._proc.stdin.write(data)
        self._proc.stdin.flush()

def hexdump(data, start=0, linesize=16, file=None, end=True):
    for i in range(0, len(data), linesize):
        chunk = data[i:i + linesize]
        addr = start + i
        print(f'{addr:08x} ', end='', file=file)
        sanitized = ''
        chunk = list(chunk)
        chunk += [None] * (linesize - len(chunk))
        for j, val in enumerate(chunk):
            if val is not None:
                print(f' {val:02x}', end='', file=file)
            else:
                print('   ', end='', file=file)
            if j == (linesize // 2) - 1:
                print(' ', end='', file=file)

            if val is not None:
                if val >= 33 and val < 127:
                    sanitized += chr(val)
                else:
                    sanitized += '.'

        print(f'  |{sanitized}|', file=file)
    if end:
        print(f'{start + len(data):08x}', file=file)

@click.group()
@click.argument('path')
@click.option('--sim', is_flag=True)
@click.option('--cycles', type=alegria.cli.BasedInt(), default=None)
@click.option('--vcd', default=None)
@click.option('-b', '--baud', type=int, default=1_000_000, show_default=True)
@click.option('-d', '--debug', is_flag=True)
@click.pass_context
def cli(ctx, path, sim, cycles, vcd, baud, debug):
    if sim:
        args = [path]
        if cycles is not None:
            args += ['-c', str(cycles)]
        if vcd is not None:
            args += ['-v', vcd]
        bridge = ProcessBridge(args, debug=debug)
    else:
        bridge = SerialBridge(path, baud=baud, debug=debug)

    ctx.obj = ctx.with_resource(bridge)
    bridge.ping()

pass_bridge = click.make_pass_decorator(Bridge)

@cli.command()
@click.option('--hold', is_flag=True)
@pass_bridge
def reset(bridge, hold):
    bridge.reset(True)
    if not hold:
        bridge.reset(False)

@cli.command()
@click.argument('start', type=alegria.cli.BasedInt())
@click.argument('end', type=alegria.cli.BasedInt(), required=False)
@click.option('-n', '--length', type=alegria.cli.BasedInt(), default=None)
@click.option('--hex', is_flag=True)
@click.option('-o', '--output', type=click.File('wb'), default='-')
@pass_bridge
def read(bridge, start, end, length, hex, output):
    if length is None:
        length = bridge.word_size
    if end is None:
        end = start + length
    length = end - start

    hex = hex or output.isatty()
    if hex:
        output = io.TextIOWrapper(output, encoding='ascii')

    addr = start
    for chunk in bridge.read_bytes_in_chunks(start, length):
        if hex:
            hexdump(chunk, start=addr, file=output, end=False)
        else:
            output.write(chunk)
        addr += len(chunk)

    if hex:
        hexdump(b'', start=addr, file=output)

@cli.command()
@click.argument('start', type=alegria.cli.BasedInt())
@click.argument('input', type=click.File('rb'), required=False, default='-')
@click.option('-r', '--reset', is_flag=True)
@pass_bridge
def write(bridge, start, input, reset):
    if reset:
        bridge.reset(True)

    def chunks():
        while True:
            d = input.read(1024)
            if d:
                yield d
            else:
                return

    try:
        bridge.write_bytes_in_chunks(start, chunks())
    finally:
        if reset:
            bridge.reset(False)

@cli.command()
@click.argument('start', type=alegria.cli.BasedInt())
@click.argument('end', type=alegria.cli.BasedInt(), required=False)
@click.option('-n', '--length', type=alegria.cli.BasedInt(), default=1)
@pass_bridge
def peek(bridge, start, end, length):
    if end is None:
        end = start + length * bridge.word_size
    length = end - start

    # round up to nearest whole word, why not. peek is nbd.
    length = (length + bridge.word_size - 1) // bridge.word_size

    addr = start
    for chunk in bridge.read_words_in_chunks(start, length):
        for word in chunk:
            print(f'{addr:08x}: 0x{word:08x}')
            addr += bridge.word_size

@cli.command()
@click.argument('start', type=alegria.cli.BasedInt())
@click.argument('words', type=alegria.cli.BasedInt(), nargs=-1)
@pass_bridge
def poke(bridge, start, words):
    bridge.write_words(start, words)

@cli.command()
@click.argument('elf', type=click.File('rb'))
@pass_bridge
def program(bridge, elf):
    elf = ELFFile(elf)

    bridge.reset(True)

    try:
        for seg in elf.iter_segments():
            if seg['p_type'] != 'PT_LOAD':
                continue

            data = seg.data()
            start = seg['p_paddr']

            print(f'0x{start:08x} - 0x{start + len(data):08x} ...')
            bridge.write_bytes(start, data)
    finally:
        bridge.reset(False)

if __name__ == '__main__':
    cli()
