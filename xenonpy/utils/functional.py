# Copyright 2018 TsumiNa. All rights reserved.
# Use of this source code is governed by a BSD-style
# license that can be found in the LICENSE file.

# A timer utility class
import time
import types
from collections import defaultdict
from contextlib import contextmanager
from functools import wraps
from os import getenv
from pathlib import Path

from ruamel.yaml import YAML

from .. import __cfg_root__


@contextmanager
def set_env(**kwargs):
    """
    Set temp environment variable with ``with`` statement.

    Examples
    --------
    >>> import os
    >>> with set_env(test='test env'):
    >>>    print(os.getenv('test'))
    test env
    >>> print(os.getenv('test'))
    None

    Parameters
    ----------
    kwargs: dict
        Dict with string value.
    """
    import os

    tmp = dict()
    for k, v in kwargs.items():
        tmp[k] = os.getenv(k)
        os.environ[k] = v
    yield
    for k, v in tmp.items():
        if not v:
            del os.environ[k]
        else:
            os.environ[k] = v


def __get_package_info(key):
    yaml = YAML(typ='safe')
    yaml.indent(mapping=2, sequence=4, offset=2)
    cwd = Path(__file__).parents[1] / 'conf.yml'
    with open(str(cwd), 'r') as f:
        info = yaml.load(f)
    return info[key]


def get_conf(key: str):
    """
    Return config value with key or all config.

    Parameters
    ----------
    key: str
        Key of config item.

    Returns
    -------
    object
        key value in ``conf.yml`` file.
    """
    yaml = YAML(typ='safe')
    yaml.indent(mapping=2, sequence=4, offset=2)
    home = Path.home()
    dir_ = home / __cfg_root__
    cfg_file = dir_ / 'conf.yml'

    # from user local
    with open(str(cfg_file)) as f:
        conf = yaml.load(f)

    # if no key locally, use default
    if key not in conf:
        with open(str(Path(__file__).parents[1] / 'conf.yml')) as f:
            conf_ = yaml.load(f)
            conf[key] = conf_[key]
        with open(str(cfg_file), 'w') as f:
            yaml.dump(conf, f)

    return conf[key]


def get_dataset_url(name: str):
    """
    Return url with the given file name.

    Args
    ----
    name: str
        binary file name.

    Return
    ------
    str
        binary file url.
    """
    username = __get_package_info('github_username')
    return 'https://github.com/' + username + '/dataset/releases/download/v0.1.1' + '/' + name + '.pkl.pd_'


def get_data_loc(name):
    """Return user data location"""

    scheme = ('userdata', 'usermodel')
    if name not in scheme:
        raise ValueError('{} not in {}'.format(name, scheme))
    if getenv(name):
        return str(Path(getenv(name)).expanduser())
    return str(Path(get_conf(name)).expanduser())


def absolute_path(path, ignore_err=True):
    """
    Resolve path when path include ``~``, ``parent/here``.

    Parameters
    ----------
    path: str
        Path to expand.
    ignore_err: bool
        FileNotFoundError is raised when set to False.
        When True, the path will be created.
    Returns
    -------
    str
        Expanded path.
    """
    from sys import version_info

    p = Path(path)
    if version_info[1] == 5:
        if ignore_err:
            p.expanduser().mkdir(parents=True, exist_ok=True)
        return str(p.expanduser().resolve())
    return str(p.expanduser().resolve(not ignore_err))


class Timer(object):
    class __Timer:
        def __init__(self):
            self.start = None
            self.times = []

        @property
        def elapsed(self):
            all_ = sum(self.times)
            dt = 0.0
            if self.start:
                dt = time.perf_counter() - self.start
            return all_ + dt

    def __init__(self, time_func=time.perf_counter):
        self._func = time_func
        self._timers = defaultdict(self.__Timer)

    def __call__(self, *args, **kwargs):
        self.timed(*args, **kwargs)

    def start(self, fn_name='main'):
        if self._timers[fn_name].start is not None:
            raise RuntimeError('Timer <%s> Already started' % fn_name)
        self._timers[fn_name].start = self._func()

    def stop(self, fn_name='main'):
        if self._timers[fn_name].start is None:
            raise RuntimeError('Timer <%s> not started' % fn_name)
        elapsed = self._func() - self._timers[fn_name].start
        self._timers[fn_name].times.append(elapsed)
        self._timers[fn_name].start = None

    @property
    def elapsed(self):
        if 'main' in self._timers:
            return self._timers['main'].elapsed
        return sum([v.elapsed for v in self._timers.values()])

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def get_sha256(fname):
    """
    Calculate file's sha256 value

    Parameters
    ----------
    fname: str
        File name.

    Returns
    -------
    str
        sha256 value.
    """
    from hashlib import sha256
    hasher = sha256()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def timed(fn):
    if isinstance(fn, (types.FunctionType, types.MethodType)):
        @wraps(fn)
        def fn_(self, *args, **kwargs):
            self._timer.start(fn.__name__)
            rt = fn(self, *args, **kwargs)
            self._timer.stop(fn.__name__)
            return rt

        return fn_
    raise TypeError('Need <FunctionType> or <MethodType> but got %s' % type(fn))


class TimedMetaClass(type):
    """
    This metaclass replaces each methods of its classes
    with a new function that is timed
    """

    def __new__(mcs, name, bases, attr):

        if '__init__' in attr:
            real_init = attr['__init__']

            # we do a deepcopy in case default is mutable
            # but beware, this might not always work
            def injected_init(self, *args, **kwargs):
                setattr(self, '_timer', Timer())
                # call the "real" __init__ that we hid with our injected one
                real_init(self, *args, **kwargs)
        else:
            def injected_init(self, *args, **kwargs):
                setattr(self, '_timer', Timer())
        # inject it
        attr['__init__'] = injected_init

        for name, value in attr.items():
            if name[0] != '_' and isinstance(value, (types.FunctionType, types.MethodType)):
                attr[name] = timed(value)

        return super(TimedMetaClass, mcs).__new__(mcs, name, bases, attr)
