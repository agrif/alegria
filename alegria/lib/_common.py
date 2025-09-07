import amaranth as am
import amaranth.lib.data

__all__ = ['DataWithError']

# assumption: error.any() indicates an error is set
class DataWithError(am.lib.data.StructLayout):
    def __init__(self, bits=am.unsigned(8), error=am.unsigned(1)):
        super().__init__({
            'data': bits,
            'error': error,
        })
