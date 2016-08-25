import numpy as np
from functools import wraps
import pandas as pd
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


def skip_check(*dargs):
    """Decorator to determine if method can be skipped"""
    def wrapper(func):
        @wraps(func)
        def wrapped(self, *args):
            attrs = [getattr(self, darg) for darg in dargs]
            if any(attrs):
                func(self, *args)
        return wrapped
    return wrapper


class Events(object):
    """Search for events that satisfy the condition and apply filters.

    Return an iterable :Events: object that takes a condition and
    applies predefined filtering methods. This object can be used to
    describe the condition, segment arrays or dataframes, or create
    numpy.array or pandas.series representations of the condition and
    filters.

    Filtering methods are applied in the following order
    1. Events.debounce
    2. Events.filter_durations
    3. Events.offset

    Attributes
    ----------
        condition: array_like, shape (M, )
            Conditional mask of booleans derived from either numpy
            arrays or pandas series.
        period: float, units=seconds
            The sample period of the conditional array in seconds.
            Events.condition must be of a univariate sample_period.
            Default is None
        adeb (optional): float, units=seconds
            The time in seconds that the condition must be True in order
            to activate event identification. This will prevent events
            lasting less than activation_debounce from being identified
            as an event.
            Default is None
        ddeb (optional): float, units=seconds
            The time in seconds that the condition must be False in
            order to deactivate event identification. This will prevent
            events lasting less than activation_debounce from
            deactivating an identified event.
            Default is None
        mindur (optional): float, units=seconds
            The minimum time in seconds that the condition must be True
            to be identified as an event. Any event of a duration less
            than min_duration will be ignored.
            Default is None
        maxdur (optional): float, units=seconds
            The maximum time in seconds that the condition may be True
            to be identified as an event. Any event of a duration
            greater than max_duration will be ignored.
            Default is None
        startoffset (optional): float, units=seconds
            This will offset every identified event's start index back
            this many seconds. Must be a negative value.
            Default is None
        stopoffset (optional): float, units=seconds
            This will offset every identified event's stop index forward
            this many seconds. Must be a positive value.
            Default is None
        _starts: array_like, float
            After events are found, this will be a numpy array of the
            left slice bound for all events.
        _stops: array_like, float
            After events are found, this will be a numpy array of the
            right slice bound for all events.

    Examples
    --------
    >>> from nimble import Events
    >>> import numpy as np
    >>> np.random.seed(10)
    >>> x = np.random.random_integers(0, 1, 20)
    >>> y = np.random.random_integers(2, 4, 20)
    >>> events = Events(((x>0) & (y<=3)), period=1).find()
    >>> events.durations
    array([2, 2, 1, 1])
    >>> len(events)
    4
    >>> events.as_array()
    array([ 1.,  1.,  0.,  0.,  0.,  0.,  0.,  0.,  1.,  1.,  0.,  1.,  0.,
            0.,  0.,  1.,  0.,  0.,  0.,  0.])
    >>> events.as_series()
    0     1.0
    1     1.0
    2     0.0
    3     0.0
    4     0.0
    5     0.0
    6     0.0
    7     0.0
    8     1.0
    9     1.0
    10    0.0
    11    1.0
    12    0.0
    13    0.0
    14    0.0
    15    1.0
    16    0.0
    17    0.0
    18    0.0
    19    0.0
    Name: events, dtype: float64

    >>> print(events)
    Number of events: 4
    Min, Max, Mean Duration: 1.000s, 2.000s, 1.500s
    sample_period: 1s,
    activation_debounce: None, deactivation_debounce: None,
    min_duration: None, max_duration: None,
    start_offset: None, stop_offset: None

    >>> string = 'Event {} was {}s in duration'
    >>> for event in events:
    ...     print(string.format(event.i, event.iduration))
    Event 0 was 2s in duration
    Event 1 was 2s in duration
    Event 2 was 1s in duration
    Event 3 was 1s in duration

    >>> string = ('Event {}, first y val is {}, last is {} and'
    ... ' slice is {}')
    >>> for event in events:
    ...     print(string.format(event.i, y[event.istart],
    ...     y[event.istop], y[event.islice]))
    Event 0, first y val is 2, last is 2 and slice is [2 2]
    Event 1, first y val is 2, last is 2 and slice is [2 2]
    Event 2, first y val is 3, last is 3 and slice is [3]
    Event 3, first y val is 3, last is 3 and slice is [3]

    >>> events2 = Events(((x>0) & (y<=3)), period=1).find()
    >>> events2 == events
    True
    """
    def __init__(self, condition, period,
                 adeb=None, ddeb=None,
                 mindur=None, maxdur=None,
                 startoffset=None, stopoffset=None):

        self.activation_debounce = adeb
        self.deactivation_debounce = ddeb
        self.min_duration = mindur
        self.max_duration = maxdur
        self._starts = None
        self._stops = None

        if type(condition) is pd.core.series.Series:
            self.condition = condition.values
        else:
            self.condition = condition

        if not period or period <= 0:
            raise ValueError('Period must be a positive value '
                             'of the time in seconds between two samples')
        else:
            self.sample_period = period  # Assumes univariate time series

        if startoffset and startoffset > 0:
            raise ValueError('Start offset must be negative')
        else:
            self.start_offset = startoffset

        if stopoffset and stopoffset < 0:
            raise ValueError('Stop offset must be positive')
        else:
            self.stop_offset = stopoffset
        # TODO - work out strategy for multivariate data. Pass index?

    @property
    def _activation_debounce(self):
        """Convert activation_debounce to number of points"""
        try:
            return np.ceil(self.activation_debounce / self.sample_period)
        except TypeError:
            return 0

    @property
    def _deactivation_debounce(self):
        """Convert deactivation_debounce to number of points"""
        try:
            return np.ceil(self.deactivation_debounce / self.sample_period)
        except TypeError:
            return 0

    @property
    def _min_duration(self):
        """Convert min_duration to number of points"""
        try:
            return np.ceil(self.min_duration / self.sample_period)
        except TypeError:
            return 0

    @property
    def _max_duration(self):
        """Convert max_duration to number of points"""
        try:
            return np.floor(self.max_duration / self.sample_period)
        except TypeError:
            return self.condition.size

    @property
    def _start_offset(self):
        """Convert start_offset to number of points"""
        try:
            return np.ceil(self.start_offset / self.sample_period).astype('int32')
        except TypeError:
            return 0

    @property
    def _stop_offset(self):
        """Convert stop_offset to number of poitns"""
        try:
            return np.ceil(self.stop_offset / self.sample_period).astype('int32')
        except TypeError:
            return 0

    @lazyproperty
    def durations(self):
        """Return a numpy.array of event durations in seconds."""
        return (self._stops - self._starts)*self.sample_period

    def as_array(self, false_values=0, true_values=1, dtype='float'):
        """Returns a numpy.array that identifies events

        Useful for plotting or for creating a new mask.

        Parameters
        ----------
            false_values: float, optional
                Value of array where events are not active. Default 0
            true_values: float, optional
                Value of array where events are active. Default 1
            dtype: np.dtype, optional
                Datatype of returned array. Default is'float'

        Returns
        -------
        array: ndarray
            Array of specified values that identify where events were
            identified.

        """
        output = np.ones(self.condition.size, dtype=np.float) * false_values
        try:
            from nimble.cyfunc.as_array import as_array
        except ImportError:
            from nimble.as_array import as_array

        output = as_array(self._starts, self._stops, output, true_values)
        return output.astype(dtype)

    def as_series(self, false_values=0, true_values=1, name='events'):
        """Returns a pandas.series that identifies events

        Useful for plotting, for creating a new mask, or using for
        group_by functionality in dataframes

        Parameters
        ----------
            false_values: float, optional
                Value of array where events are not active. Default 0
            true_values: float, optional
                Value of array where events are active. Default 1
            name: str, optional
                The name of the event. Default is 'events'

        Returns
        -------
        series: series
            Series of specified values that identify where events were
            identified.
        """
        try:
            index = pd.RangeIndex(self.condition.size, step=self.sample_period)
        except AttributeError:
            index = np.arange(self.condition.size, step=self.sample_period)

        data = self.as_array(false_values=false_values, true_values=true_values)
        return pd.Series(data=data, index=index, name=name)

    def find(self):
        """Convenience function that applies all filters in order

        This method can be overridden when inherited from Events to
        apply a user specified order

        Order
        -----
        apply_condition()
        debounce()
        filter_durations()
        offset()
        """
        self.apply_condition()
        self.debounce()
        self.filter_durations()
        self.offset()

        return self

    def apply_condition(self):
        """Apply initial masking conditions"""
        mask = (self.condition > 0).view('i1')
        slice_index = np.arange(mask.size + 1, dtype='int32')

        # Determine if condition is active at array start, set to_begin accordingly
        if mask[0] == 0:
            to_begin = np.array([0], dtype='i1')
        else:
            to_begin = np.array([1], dtype='i1')

        # Determine if condition is active at array end, set to_end accordingly
        if mask[-1] == 0:
            to_end = np.array([0], dtype='i1')
        else:
            to_end = np.array([-1], dtype='i1')

        deltas = np.ediff1d(mask, to_begin=to_begin, to_end=to_end)

        self._starts = np.ma.masked_where(deltas < 1, slice_index).compressed()
        self._stops = np.ma.masked_where(deltas > -1, slice_index).compressed()

    @skip_check('_activation_debounce', '_deactivation_debounce')
    def debounce(self):
        """ Apply debounce parameters"""
        try:
            from nimble.cyfunc.debounce import debounce
        except ImportError:
            from nimble.debounce import debounce

        self._starts, self._stops = debounce(self._starts, self._stops,
                                             np.double(self._activation_debounce),
                                             np.double(self._deactivation_debounce))

    @skip_check('_min_duration', '_max_duration')
    def filter_durations(self):
        event_lengths = self._stops - self._starts
        condition = ((event_lengths < self._min_duration) |
                     (event_lengths > self._max_duration))

        self._starts = np.ma.masked_where(condition, self._starts).compressed()
        self._stops = np.ma.masked_where(condition, self._stops).compressed()

    @skip_check('_start_offset', '_stop_offset')
    def offset(self):
        """Applies offset parameters"""
        min_index = 0
        max_index = self.condition.size

        self._starts += self._start_offset
        self._stops += self._stop_offset

        np.clip(self._starts, min_index, max_index, out=self._starts)
        np.clip(self._stops, min_index, max_index, out=self._stops)

    def __iter__(self):
        self.i = -1
        return self

    def __next__(self):
        self.i += 1
        try:
            self.istart = self._starts[self.i]
            self.istop = self._stops[self.i]-1
            self.iduration = (self._stops[self.i] - self._starts[self.i])*self.sample_period
            self.islice = slice(self._starts[self.i], self._stops[self.i])
            return self
        except IndexError:
            raise StopIteration

    def __len__(self):
        return self._starts.size

    def __repr__(self):
        # TODO - due to the size of condition, this should take an optional path and
        # serialize as pickle, yaml, or json
        return ('{__class__.__name__}(condition={condition!r}, '
                'sample_period={sample_period!r}, '
                'activation_debounce={_activation_debounce!r}, '
                'deactivation_debounce={_deactivation_debounce!r}, '
                'min_duration={_min_duration!r}, '
                'max_duration={_max_duration!r}, '
                'start_offset={_start_offset!r}, '
                'stop_offset={_stop_offset!r}').format(__class__=self.__class__,
                                                       **self.__dict__)

    def __str__(self):
        args = [len(self), np.min(self.durations),
                np.max(self.durations), np.mean(self.durations)]
        kwargs = {
            'sample_period': '{}s'.format(self.sample_period),
            'activation_debounce': '{}s'.format(self.activation_debounce)
                if self.activation_debounce else None,
            'deactivation_debounce': '{}s'.format(self.deactivation_debounce)
                if self.deactivation_debounce else None,
            'min_duration': '{}s'.format(self.min_duration) if self.min_duration else None,
            'max_duration': '{}s'.format(self.max_duration) if self.max_duration else None,
            'start_offset': '{}s'.format(self.start_offset) if self.start_offset else None,
            'stop_offset': '{}s'.format(self.stop_offset) if self.stop_offset else None
        }
        return (
            'Number of events: {0}'
            '\nMin, Max, Mean Duration: {1:.3f}s, {2:.3f}s, {3:.3f}s'
            '\nsample_period: {sample_period},'
            '\nactivation_debounce: {activation_debounce}, deactivation_debounce: {deactivation_debounce},'
            '\nmin_duration: {min_duration}, max_duration: {max_duration},'
            '\nstart_offset: {start_offset}, stop_offset: {stop_offset}'
        ).format(*args, **kwargs)

    def __eq__(self, scnd_event):
        """Determine if two Events objects are identical

        Compares starts, stops, sample_period and condition.size to
        determine if two events are identical.
        """
        if (np.all(self._starts == scnd_event._starts)
                and np.all(self._stops == scnd_event._stops)
                and self.sample_period == scnd_event.sample_period
                and self.condition.size == scnd_event.condition.size):
            return True
        else:
            return False

    def __hash__(self):
        """Numpy arrays aren't hashable.

        Researching solution that doesn't require something beyond
        standard lib.
        """
        return id(self)


def main():
    np.random.seed(15)
    mask = np.random.random_integers(0, 1, 1000000)
    events = Events(mask > 0, period=1,
                    adeb=1,
                    mindur=3,
                    startoffset=-1).find()

    x = events.as_array(false_values=2.33, true_values=5.35)

    events2 = Events(mask > 0, period=1,
                     adeb=1,
                     mindur=3,
                     startoffset=-1).find()

    print(events)
    print(events == events2)


if __name__ == '__main__':
    import sys
    sys.exit(main())
