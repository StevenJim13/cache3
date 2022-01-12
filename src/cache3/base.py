#!/usr/bin/python
# -*- coding: utf-8 -*-
# DATE: 2021/7/24
# Author: clarkmonkey@163.com

import functools
import warnings
from time import time as current
from typing import Any, Type, Optional, Union, Dict, Tuple, Callable, NoReturn, List, Iterator

from cache3.utils import empty
from cache3.setting import (
    DEFAULT_TAG, DEFAULT_TIMEOUT, MAX_TIMEOUT, MIN_TIMEOUT, MAX_KEY_LENGTH,
    DEFAULT_NAME, DEFAULT_MAX_SIZE, DEFAULT_EVICT, DEFAULT_CULL_SIZE, EVICT_LFU,
    EVICT_FIFO, EVICT_LRU
)
from cache3.validate import NumberValidate, StringValidate, EnumerateValidate

Number: Type = Union[int, float]
TG: Type = Optional[str]


class CacheKeyWarning(RuntimeWarning):
    """ A warning that is thrown when the key is not legitimate """


class InvalidCacheKey(ValueError):
    """ An Error thrown when the key invalid """


class BaseCache:
    """ A base class that specifies the API that caching
    must implement and some default implementations.
    """

    name: str = StringValidate(minsize=1, maxsize=MAX_KEY_LENGTH)
    timeout: Number = NumberValidate(minvalue=MIN_TIMEOUT, maxvalue=MAX_TIMEOUT)
    max_size: int = NumberValidate(minvalue=0)
    evict: str = EnumerateValidate(EVICT_LRU, EVICT_FIFO, EVICT_LFU)
    cull_size: str = NumberValidate(minvalue=0)

    def __init__(
            self,
            name: str = DEFAULT_NAME,
            timeout: Number = DEFAULT_TIMEOUT,
            max_size: int = DEFAULT_MAX_SIZE,
            **kwargs
    ) -> None:
        self.name: str = name
        self.timeout: Number = timeout
        self.max_size: int = max_size
        self.evict: str = DEFAULT_EVICT
        self.cull_size: int = 10
        self._kwargs: Dict[str, Any] = kwargs

    def config(self, **kwargs) -> NoReturn:
        """ The cache is configured in fine grain By default,
        Configure the cache eviction policy.
        """
        self.evict = kwargs.get('evict', DEFAULT_EVICT)
        self.cull_size = kwargs.get('cull_size', DEFAULT_CULL_SIZE)

    def set(self, key: str, value: Any, timeout: Number = DEFAULT_TIMEOUT,
            tag: TG = DEFAULT_TAG) -> bool:
        """ Set a value in the cache. Use timeout for the key if
        it's given, Otherwise use the default timeout.
        """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a set() method.'
        )

    def get(self, key: str, default: Any = None, tag: TG = DEFAULT_TAG) -> Any:
        """ Fetch a given key from the cache. If the key does not exist, return
        default, which itself defaults to None.
        """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a get() method'
        )

    def ex_set(self, key: str, value: Any, timeout: float = DEFAULT_TIMEOUT,
               tag: Optional[str] = DEFAULT_TAG) -> bool:
        """ Set a value in the cache if the key does not already exist. If
        timeout is given, use that timeout for the key; otherwise use the
        default cache timeout.

        Return True if the value was stored, False otherwise.
        """
        raise NotImplementedError(
            'subclasses of BaseCache must provide an ex_set() method'
        )

    def get_many(self, keys: List[str], tag: TG = DEFAULT_TAG) -> Dict[str, Any]:
        """ Fetch a bunch of keys from the cache. For certain backends (memcached,
        pgsql) this can be *much* faster when fetching multiple values.

        Return a dict mapping each key in keys to its value. If the given
        key is missing, it will be missing from the response dict.
        """

        returns: Dict[Any, Any] = dict()
        for key in keys:
            value: Any = self.get(key, empty, tag)
            if value is not empty:
                returns[key] = value
        return returns

    def touch(self, key: str, timeout: Number, tag: TG = DEFAULT_TAG) -> bool:
        """ Update the key's expiry time using timeout. Return True if successful
        or False if the key does not exist.
        """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a touch() method'
        )

    def delete(self, key: str, tag: TG = DEFAULT_TAG) -> bool:
        """ Delete a key from the cache

        Return True if delete success, False otherwise.
        """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a delete() method'
        )

    def inspect(self, key: str, tag: TG = DEFAULT_TAG) -> Optional[Dict[str, Any]]:
        """ Displays the information of the key value if it exists in cache.

        Returns the details if the key exists, otherwise None.
        """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a inspect() method'
        )

    def make_key(self, key: str, tag: Optional[str]) -> str:
        """Default function to generate keys.

        Construct the key used by all other methods. By default,
        the key will be converted to a unified string format
        as much as possible. At the same time, subclasses typically
        override the method to generate a specific key.
        """
        if ':' in tag:
            raise ValueError(
                "The ':' is not expected in tag."
            )

        return '%s:%s' % (key, tag)

    @staticmethod
    def _get_key_tag(serial_key: str) -> List[str]:
        """ extract key and tag from serialize key """
        return serial_key.rsplit(':', 1)

    def validate_key(self, key: str) -> Tuple[Optional[str], bool]:
        """ The incoming key is validated to fit the logic of the
        backend storage. It is always closely related to ``make_key(...)``

        By default, it will check the type and length.
        """

        if not isinstance(key, str):
            return (
                'The key must be a string (%s is %s)'
                % (key, type(key).__name__), False
            )

        if len(key) > MAX_KEY_LENGTH:
            warnings.warn(
                'The key is too long( > %s), which can cause '
                'unnecessary waste of resources and risk: %s...%s.'
                % (MAX_KEY_LENGTH, key[:10], key[-10:]),
                CacheKeyWarning
            )
        return None, True

    def make_and_validate_key(self, key: str, tag: Optional[str] = None) -> str:
        """ Validate keys and convert them into a friendlier format for storing
        key-value pairs.

        Returns a friendlier format key if key is validated, thrown ``InvalidCacheKey``
        otherwise.
        """

        key: str = self.make_key(key, tag)
        msg, validated = self.validate_key(key)
        if validated:
            return key
        raise InvalidCacheKey(msg)

    def get_backend_timeout(self, timeout=DEFAULT_TIMEOUT) -> Optional[float]:
        """ Return the timeout value usable by this backend based upon the
        provided timeout.
        """
        if timeout == DEFAULT_TIMEOUT:
            timeout = self._timeout

        return None if timeout is None else current() + timeout

    def serialize(self, value: Any, *args, **kwargs) -> Any:
        """ Serialize the value for easy backend storage.
        By default, return directly to value doing nothing.
        """
        return value

    def deserialize(self, dump: Any, *args, **kwargs) -> Any:
        """ Restores the value returned by the backend to be consistent
        with when deposited. Usually it is always the opposite of the
        ``serialize(...)`` method.

        By default, return directly to value doing nothing.
        """
        return dump

    def incr(self, key: str, delta: int = 1, tag: TG = DEFAULT_TAG) -> Number:
        """ Add delta to value in the cache. If the key does not exist, raise a
        ValueError exception.  """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a incr() method'
        )

    def decr(self, key: str, delta: int = 1, tag: TG = DEFAULT_TAG) -> Number:
        """ Subtract delta from value in the cache. If the key does not exist,
         raise a ValueError exception. """
        return self.incr(key, -delta, tag)

    def has_key(self, key: str, tag: TG = DEFAULT_TAG) -> bool:
        """ Return True if the key is in the cache and has not expired. """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a incr() method'
        )

    def memoize(self, tag: Optional[str] = DEFAULT_TAG, timeout: float = DEFAULT_TIMEOUT) -> Any:
        """ The cache is decorated with the return value of the function,
        and the timeout is available. """

        if callable(tag):
            raise TypeError(
                "Mame cannot be callable. ('@cache.memoize()' not '@cache.memoize')."
            )

        def decorator(func) -> Callable[[Callable[[Any], Any]], Any]:
            """ Decorator created by memoize() for callable `func`."""

            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                """Wrapper for callable to cache arguments and return values."""
                value: Any = self.get(func.__name__, empty, tag)
                if value is empty:
                    value: Any = func(*args, **kwargs)
                    self.set(func.__name__, value, timeout, tag)
                return value
            return wrapper

        return decorator

    def clear(self) -> bool:
        """ Empty all caches. """
        raise NotImplementedError(
            'subclasses of BaseCache must provide a clear() method'
        )

    @property
    def evictor(self) -> Callable:
        """ Implementation of the cache eviction policy.

        The ``_evict`` parameter is used to determine the eviction policy.
        By default, the lru algorithm is used to evict the cache.

        The behavior of a cache eviction policy always gets the method by
        ``_evict`` property, so the default behavior can be modified through
        the ``config()`` method. the mru_evict will be use, if cache.config(
        evict="mru_evict") and the cache has been implemented ``mru_evict()``.

        Returns evict method if the ``_evict`` is a callable object, thrown
        warning otherwise.
        """

        evictor: Callable = getattr(self, self._evict, empty)
        if evictor is empty:
            warnings.warn(
                "Not found '%s' evict method, it will cause the"
                "cache to grow without limit." % self._evict,
                RuntimeWarning
            )
            # Just to return a callable object ~.
            return object

        if not callable(evictor):
            warnings.warn(
                "Invalid evict '%s', It must a callable object." % evictor,
                RuntimeWarning
            )
            return object

        return evictor

    def __repr__(self) -> str:
        return "<%s '%s' timeout:%.2f>" % (
            self.__class__.__name__, self._name, self._timeout
        )

    def __iter__(self) -> Iterator:
        raise NotImplementedError(
            'subclasses of BaseCache must provide a __iter__() method.'
        )

    __delitem__ = delete
    __getitem__ = get
    __setitem__ = set
