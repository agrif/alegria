class TruthTable:
    class Many:
        def __init__(self, iterable):
            self._iterable = iterable

        def __repr__(self):
            return 'TruthTable.Many({!r})'.format(self._iterable)

        def __iter__(self):
            return iter(self._iterable)

        def __len__(self):
            return len(self._iterable)

    class Group:
        def __init__(self, name, iterable):
            self._name = name
            self._iterable = iterable

        def __repr__(self):
            return 'TruthTable.Group({!r}, {!r})'.format(self._name, self._iterable)

        def __iter__(self):
            return iter(self._iterable)

        def __len__(self):
            return len(self._iterable)

        @property
        def name(self):
            return self._name

    class Row:
        def __init__(self, *args, **data):
            if not ((len(args) == 1 and len(data) == 0) or len(args) == 0):
                    raise TypeError('TruthTable.Roww() takes either 1 positional argument or only keyword arguments')

            if args:
                self._data = args[0]
            else:
                self._data = data

        def __repr__(self):
            if all(isinstance(k, str) for k in self._data):
                inner = ', '.join('{}={!r}'.format(k, v) for k, v in self._data.items())
            else:
                inner = repr(self._data)
            return 'TruthTable.Row({})'.format(inner)

        def __getitem__(self, k):
            return self._data[k]

        def __getattr__(self, k):
            try:
                return self._data[k]
            except KeyError:
                raise AttributeError("'{}' object has no attribute {!r}".format(self.__class__.__name__, k))

        def __iter__(self):
            return iter(self._data)

        def __len__(self):
            return len(self._data)

        def __eq__(self, other):
            if isinstance(other, TruthTable.Row):
                return self._data == other._data
            return self._data == other

        def get(self, k, default=None):
            return self._data.get(k, default)

        def items(self):
            return self._data.items()

        def keys(self):
            return self._data.keys()

        def values(self):
            return self._data.values()

    def __init__(self, column_names, *rows):
        self._column_names = column_names
        self._rows = rows

    @classmethod
    def _iterable(cls, it):
        if isinstance(it, str):
            # not really what we mean here
            return False
        try:
            iter(it)
            return True
        except TypeError:
            return False

    @classmethod
    def _expand_row(cls, row):
        for i, col in enumerate(row):
            if isinstance(col, cls.Many):
                for x in col:
                    new_row = list(row)
                    new_row[i] = x
                    for expanded_new_row in cls._expand_row(new_row):
                        yield from cls._expand_row(expanded_new_row)
                break
            elif cls._iterable(col):
                for x in cls._expand_row(col):
                    for rest in cls._expand_row(row[i + 1:]):
                        new_row = list(row)
                        new_row[i] = x
                        new_row[i + 1:] = rest
                        yield new_row
                break
            else:
                continue
        else:
            yield row

    @classmethod
    def _expand_rows(cls, rows):
        for row in rows:
            yield from cls._expand_row(row)

    @classmethod
    def _apply_names(cls, names, data):
        if len(names) != len(data):
            raise RuntimeError('length mismatch: {!r} vs {!r}'.format(names, data))
        for name, x in zip(names, data):
            if cls._iterable(name) or cls._iterable(x):
                if not cls._iterable(name) or not cls._iterable(x):
                    raise RuntimeError('structure mismatch: {!r} vs {!r}'.format(name, x))

            if isinstance(name, cls.Group):
                yield (name.name, cls.Row(dict(cls._apply_names(name, x))))
            elif cls._iterable(name) and cls._iterable(x):
                yield from cls._apply_names(name, x)
            else:
                yield (name, x)

    def __iter__(self):
        for row in self._expand_rows(self._rows):
            yield self.Row(dict(self._apply_names(self._column_names, row)))
