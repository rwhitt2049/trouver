import numpy as np
from functools import lru_cache, wraps

# from memory_profiler import profile


def lazyproperty(func):
    name = '_lazy_' + func.__name__

    @property
    @wraps(func)
    def lazy(self):
        if hasattr(self, name):
            return getattr(self, name)
        else:
            value = func(self)
            setattr(self, name, value)
            return value
    return lazy


class Events(object):
    def __init__(self, condition, sample_rate=1,
                 entry_debounce=0, exit_debounce=0,
                 min_event_length=0, max_event_length=None,
                 start_offset=0, stop_offset=0):

        self.condition = condition
        self.sample_rate = sample_rate  # Assumes univariate time series
        self._entry_debounce = entry_debounce
        self._exit_debounce = exit_debounce
        self._min_event_length = min_event_length
        self._max_event_length = max_event_length
        self._start_offset = start_offset
        self._stop_offset = stop_offset

        # TODO - work out strategy for multivariate data. Pass index
        # TODO - promote private methods to public, allow events to be created step by step
        # TODO - parameter datatypes might become an issue
    @property
    def entry_debounce(self):
        return np.ceil(self._entry_debounce * self.sample_rate)

    @property
    def exit_debounce(self):
        return np.ceil(self._exit_debounce * self.sample_rate)

    @property
    def min_event_length(self):
        return np.ceil(self._min_event_length * self.sample_rate)

    @property
    def max_event_length(self):
        try:
            return np.floor(self._max_event_length * self.sample_rate)
        except TypeError:
            return None

    @property
    def start_offset(self):
        if self._start_offset > 0:
            raise ValueError('Currently only negative '
                             'start offsets are supported')
        else:
            return np.ceil(self._start_offset * self.sample_rate).astype('int32')

    @property
    def stop_offset(self):
        if self._stop_offset < 0:
            raise ValueError('Currently only negative start offsets are supported')
        else:
            return np.ceil(self._stop_offset * self.sample_rate).astype('int32')

    @property
    def size(self):
        """Return the number of events found."""
        return self.starts.size
        
    @lazyproperty
    def starts(self):
        """Return a numpy.array() of start indexes."""
        starts, _ = self._apply_filters()
        return starts
        
    @lazyproperty
    def stops(self):
        """Return a numpy.array() of start indexes."""
        _, stops = self._apply_filters()
        return stops

    @lru_cache(10)
    def as_array(self, false_values=0, true_values=1, dtype='float'):
        """
        Return the found events as a numpy array of 0's and 1'sample_rate
        """
        try:
            from nimble.cyfunc.as_array import as_array
        except ImportError:
            from nimble.as_array import as_array

        output = np.ones(self.condition.size) * false_values
        output = as_array(self.starts, self.stops, output, true_values)
        return output.astype(dtype)

    @lru_cache(1)
    def _apply_filters(self):
        starts, stops = self._apply_condition_filter()

        if starts.size > 0 and (self.entry_debounce or self.exit_debounce):
            starts, stops = self._apply_debounce_filter(starts, stops)

        if starts.size > 0 and (self.min_event_length or self.max_event_length):
            starts, stops = self._apply_event_length_filter(starts, stops)

        if starts.size > 0 and (self.start_offset or self.stop_offset):
            starts, stops = self._apply_offsets(starts, stops)

        return starts, stops

    def _apply_condition_filter(self):
        """
        Apply initial masking conditions
        """
        mask = (self.condition > 0).view('i1')
        slice_index = np.arange(mask.size + 1, dtype='int32')

        if mask[0] == 0:
            to_begin = np.array([0], dtype='i1')
        else:
            to_begin = np.array([1], dtype='i1')

        if mask[-1] == 0:
            to_end = np.array([0], dtype='i1')
        else:
            to_end = np.array([-1], dtype='i1')

        deltas = np.ediff1d(mask, to_begin=to_begin, to_end=to_end)

        starts = np.ma.masked_where(deltas < 1, slice_index).compressed()
        stops = np.ma.masked_where(deltas > -1, slice_index).compressed()

        return starts, stops

    def _apply_debounce_filter(self, starts, stops):
        """ Apply debounce parameters"""
        try:
            from nimble.cyfunc.debounce import debounce
        except ImportError:
            from nimble.debounce import debounce

        starts, stops = debounce(starts, stops,
                                 self.entry_debounce, self.exit_debounce)
        return starts, stops

    def _apply_event_length_filter(self, starts, stops):
        event_lengths = stops - starts

        if not self.max_event_length:
            condition = (event_lengths < self.min_event_length)
        elif self.min_event_length >= 0 and self.max_event_length > 0:
            condition = ((event_lengths < self.min_event_length) |
                         (event_lengths > self.max_event_length))
        else:
            raise ValueError

        starts = np.ma.masked_where(condition, starts).compressed()
        stops = np.ma.masked_where(condition, stops).compressed()

        return starts, stops

    def _apply_offsets(self, starts, stops):
        min_index = 0
        max_index = self.condition.size

        starts += self.start_offset
        stops += self.stop_offset

        np.clip(starts, min_index, max_index, out=starts)
        np.clip(stops, min_index, max_index, out=stops)

        return starts, stops


def main():
    np.random.seed(15)
    mask = np.random.random_integers(0, 1, 1000000)
    events = Events(mask > 0,
                    entry_debounce=2,
                    min_event_length=3,
                    start_offset=-1)
    starts = events.starts

if __name__ == '__main__':
    import sys
    sys.exit(main())
