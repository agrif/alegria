import amaranth as am
import amaranth.lib.data

__all__ = ['DataWithError', 'Framed']

# assumption: error.any() indicates an error is set
class DataWithError(am.lib.data.StructLayout):
    def __init__(self, data=am.unsigned(8), error=am.unsigned(1)):
        super().__init__({
            'data': data,
            'error': error,
        })

class Framed(am.lib.data.StructLayout):
    def __init__(self, data=8):
        super().__init__({
            'data': data,
            'frame': 1,
        })
