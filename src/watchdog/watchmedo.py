# coding: utf-8
#
# Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>
# Copyright 2012 Google, Inc & contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
:module: watchdog.watchmedo
:author: yesudeep@google.com (Yesudeep Mangalapilly)
:author: contact@tiger-222.fr (Mickaël Schoentgen)
:synopsis: ``watchmedo`` shell script utility.
"""

import errno
import os
import os.path
import sys
import yaml
import time
import logging
from io import StringIO

from argparse import ArgumentParser
from watchdog.version import VERSION_STRING
from watchdog.utils import WatchdogShutdown, load_class

logging.basicConfig(level=logging.INFO)

CONFIG_KEY_TRICKS = 'tricks'
CONFIG_KEY_PYTHON_PATH = 'python-path'

epilog = """Copyright 2011 Yesudeep Mangalapilly <yesudeep@gmail.com>.
Copyright 2012 Google, Inc & contributors.

Licensed under the terms of the Apache license, version 2.0. Please see
LICENSE in the source code for more information."""

cli = ArgumentParser(epilog=epilog)
cli.add_argument('--version',
                 action='version',
                 version='%(prog)s ' + VERSION_STRING)
subparsers = cli.add_subparsers(dest="command")


def argument(*name_or_flags, **kwargs):
    """Convenience function to properly format arguments to pass to the
      command decorator.
    """
    return (list(name_or_flags), kwargs)


def command(args=[], parent=subparsers, cmd_aliases=[]):
    """Decorator to define a new command in a sanity-preserving way.
      The function will be stored in the ``func`` variable when the parser
      parses arguments so that it can be called directly like so::
          args = cli.parse_args()
          args.func(args)
    """
    def decorator(func):
        parser = parent.add_parser(func.__name__, description=func.__doc__, aliases=cmd_aliases)
        for arg in args:
            parser.add_argument(*arg[0], **arg[1])
            parser.set_defaults(func=func)
    return decorator


def path_split(pathname_spec, separator=os.pathsep):
    """
    Splits a pathname specification separated by an OS-dependent separator.

    :param pathname_spec:
        The pathname specification.
    :param separator:
        (OS Dependent) `:` on Unix and `;` on Windows or user-specified.
    """
    return list(pathname_spec.split(separator))


def add_to_sys_path(pathnames, index=0):
    """
    Adds specified paths at specified index into the sys.path list.

    :param paths:
        A list of paths to add to the sys.path
    :param index:
        (Default 0) The index in the sys.path list where the paths will be
        added.
    """
    for pathname in pathnames[::-1]:
        sys.path.insert(index, pathname)


def load_config(tricks_file_pathname):
    """
    Loads the YAML configuration from the specified file.

    :param tricks_file_path:
        The path to the tricks configuration file.
    :returns:
        A dictionary of configuration information.
    """
    with open(tricks_file_pathname, 'rb') as f:
        return yaml.safe_load(f.read())


def parse_patterns(patterns_spec, ignore_patterns_spec, separator=';'):
    """
    Parses pattern argument specs and returns a two-tuple of
    (patterns, ignore_patterns).
    """
    patterns = patterns_spec.split(separator)
    ignore_patterns = ignore_patterns_spec.split(separator)
    if ignore_patterns == ['']:
        ignore_patterns = []
    return (patterns, ignore_patterns)


def observe_with(observer, event_handler, pathnames, recursive):
    """
    Single observer thread with a scheduled path and event handler.

    :param observer:
        The observer thread.
    :param event_handler:
        Event handler which will be called in response to file system events.
    :param pathnames:
        A list of pathnames to monitor.
    :param recursive:
        ``True`` if recursive; ``False`` otherwise.
    """
    for pathname in set(pathnames):
        observer.schedule(event_handler, pathname, recursive)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except WatchdogShutdown:
        observer.stop()
    observer.join()


def schedule_tricks(observer, tricks, pathname, recursive):
    """
    Schedules tricks with the specified observer and for the given watch
    path.

    :param observer:
        The observer thread into which to schedule the trick and watch.
    :param tricks:
        A list of tricks.
    :param pathname:
        A path name which should be watched.
    :param recursive:
        ``True`` if recursive; ``False`` otherwise.
    """
    for trick in tricks:
        for name, value in list(trick.items()):
            TrickClass = load_class(name)
            handler = TrickClass(**value)
            trick_pathname = getattr(handler, 'source_directory', None) or pathname
            observer.schedule(handler, trick_pathname, recursive)


@command([argument('files',
                   nargs='*',
                   help='perform tricks from given file'),
          argument('--python-path',
                   default='.',
                   help='paths separated by %s to add to the python path' % os.pathsep),
          argument('--interval',
                   '--timeout',
                   dest='timeout',
                   default=1.0,
                   type=float,
                   help='use this as the polling interval/blocking timeout (in seconds)'),
          argument('--recursive',
                   default=True,
                   help='recursively monitor paths'),
          argument('--debug-force-polling',
                   default=False,
                   help='[debug] forces polling'),
          argument('--debug-force-kqueue',
                   default=False,
                   help='[debug] forces BSD kqueue(2)'),
          argument('--debug-force-winapi',
                   default=False,
                   help='[debug] forces Windows API'),
          argument('--debug-force-winapi-async',
                   default=False,
                   help='[debug] forces Windows API + I/O completion'),
          argument('--debug-force-fsevents',
                   default=False,
                   help='[debug] forces Mac OS X FSEvents'),
          argument('--debug-force-inotify',
                   default=False,
                   help='[debug] forces Linux inotify(7)')], cmd_aliases=['tricks'])
def tricks_from(args):
    """
    command to execute tricks from a tricks configuration file.

    :param args:
        Command line argument options.
    """
    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    elif args.debug_force_kqueue:
        from watchdog.observers.kqueue import KqueueObserver as Observer
    elif args.debug_force_winapi_async:
        from watchdog.observers.read_directory_changes_async import\
            WindowsApiAsyncObserver as Observer
    elif args.debug_force_winapi:
        from watchdog.observers.read_directory_changes import\
            WindowsApiObserver as Observer
    elif args.debug_force_inotify:
        from watchdog.observers.inotify import InotifyObserver as Observer
    elif args.debug_force_fsevents:
        from watchdog.observers.fsevents import FSEventsObserver as Observer
    else:
        # Automatically picks the most appropriate observer for the platform
        # on which it is running.
        from watchdog.observers import Observer

    add_to_sys_path(path_split(args.python_path))
    observers = []
    for tricks_file in args.files:
        observer = Observer(timeout=args.timeout)

        if not os.path.exists(tricks_file):
            raise OSError(errno.ENOENT, os.strerror(errno.ENOENT), tricks_file)

        config = load_config(tricks_file)

        try:
            tricks = config[CONFIG_KEY_TRICKS]
        except KeyError:
            raise KeyError("No %r key specified in %s." % (
                           CONFIG_KEY_TRICKS, tricks_file))

        if CONFIG_KEY_PYTHON_PATH in config:
            add_to_sys_path(config[CONFIG_KEY_PYTHON_PATH])

        dir_path = os.path.dirname(tricks_file)
        if not dir_path:
            dir_path = os.path.relpath(os.getcwd())
        schedule_tricks(observer, tricks, dir_path, args.recursive)
        observer.start()
        observers.append(observer)

    try:
        while True:
            time.sleep(1)
    except WatchdogShutdown:
        for o in observers:
            o.unschedule_all()
            o.stop()
    for o in observers:
        o.join()


@command([argument('trick_paths',
                   nargs='*',
                   help='Dotted paths for all the tricks you want to generate'),
          argument('--python-path',
                   default='.',
                   help='paths separated by %s to add to the python path' % os.pathsep),
          argument('--append-to-file',
                   default=None,
                   help='appends the generated tricks YAML to a file; \
    if not specified, prints to standard output'),
          argument('-a',
                   '--append-only',
                   dest='append_only',
                   default=False,
                   help='if --append-to-file is not specified, produces output for \
    appending instead of a complete tricks yaml file.')], cmd_aliases=['generate-tricks-yaml'])
def tricks_generate_yaml(args):
    """
    command to generate Yaml configuration for tricks named on the command
    line.

    :param args:
        Command line argument options.
    """
    python_paths = path_split(args.python_path)
    add_to_sys_path(python_paths)
    output = StringIO()

    for trick_path in args.trick_paths:
        TrickClass = load_class(trick_path)
        output.write(TrickClass.generate_yaml())

    content = output.getvalue()
    output.close()

    header = yaml.dump({CONFIG_KEY_PYTHON_PATH: python_paths})
    header += "%s:\n" % CONFIG_KEY_TRICKS
    if args.append_to_file is None:
        # Output to standard output.
        if not args.append_only:
            content = header + content
        sys.stdout.write(content)
    else:
        if not os.path.exists(args.append_to_file):
            content = header + content
        with open(args.append_to_file, 'ab') as output:
            output.write(content)


@command([argument('directories',
                   nargs='*',
                   default='.',
                   help='directories to watch. (default: \'.\')'),
          argument('-p',
                   '--pattern',
                   '--patterns',
                   dest='patterns',
                   default='*',
                   help='matches event paths with these patterns (separated by ;).'),
          argument('-i',
                   '--ignore-pattern',
                   '--ignore-patterns',
                   dest='ignore_patterns',
                   default='',
                   help='ignores event paths with these patterns (separated by ;).'),
          argument('-D',
                   '--ignore-directories',
                   dest='ignore_directories',
                   default=False,
                   action='store_true',
                   help='ignores events for directories'),
          argument('-R',
                   '--recursive',
                   dest='recursive',
                   default=False,
                   action='store_true',
                   help='monitors the directories recursively'),
          argument('--interval',
                   '--timeout',
                   dest='timeout',
                   default=1.0,
                   type=float,
                   help='use this as the polling interval/blocking timeout'),
          argument('--trace',
                   default=False,
                   help='dumps complete dispatching trace'),
          argument('--debug-force-polling',
                   default=False,
                   help='[debug] forces polling'),
          argument('--debug-force-kqueue',
                   default=False,
                   help='[debug] forces BSD kqueue(2)'),
          argument('--debug-force-winapi',
                   default=False,
                   help='[debug] forces Windows API'),
          argument('--debug-force-winapi-async',
                   default=False,
                   help='[debug] forces Windows API + I/O completion'),
          argument('--debug-force-fsevents',
                   default=False,
                   help='[debug] forces Mac OS X FSEvents'),
          argument('--debug-force-inotify',
                   default=False,
                   help='[debug] forces Linux inotify(7)')])
def log(args):
    """
    command to log file system events to the console.

    :param args:
        Command line argument options.
    """
    from watchdog.utils import echo
    from watchdog.tricks import LoggerTrick

    if args.trace:
        echo.echo_class(LoggerTrick)

    patterns, ignore_patterns =\
        parse_patterns(args.patterns, args.ignore_patterns)
    handler = LoggerTrick(patterns=patterns,
                          ignore_patterns=ignore_patterns,
                          ignore_directories=args.ignore_directories)
    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    elif args.debug_force_kqueue:
        from watchdog.observers.kqueue import KqueueObserver as Observer
    elif args.debug_force_winapi_async:
        from watchdog.observers.read_directory_changes_async import\
            WindowsApiAsyncObserver as Observer
    elif args.debug_force_winapi:
        from watchdog.observers.read_directory_changes import\
            WindowsApiObserver as Observer
    elif args.debug_force_inotify:
        from watchdog.observers.inotify import InotifyObserver as Observer
    elif args.debug_force_fsevents:
        from watchdog.observers.fsevents import FSEventsObserver as Observer
    else:
        # Automatically picks the most appropriate observer for the platform
        # on which it is running.
        from watchdog.observers import Observer
    observer = Observer(timeout=args.timeout)
    observe_with(observer, handler, args.directories, args.recursive)


@command([argument('directories',
                   nargs='*',
                   default='.',
                   help='directories to watch'),
          argument('-c',
                   '--command',
                   dest='command',
                   default=None,
                   help='''shell command executed in response to matching events.
    These interpolation variables are available to your command string::

        ${watch_src_path}    - event source path;
        ${watch_dest_path}   - event destination path (for moved events);
        ${watch_event_type}  - event type;
        ${watch_object}      - ``file`` or ``directory``

    Note::
        Please ensure you do not use double quotes (") to quote
        your command string. That will force your shell to
        interpolate before the command is processed by this
        command.

    Example option usage::

        --command='echo "${watch_src_path}"'
    '''),
          argument('-p',
                   '--pattern',
                   '--patterns',
                   dest='patterns',
                   default='*',
                   help='matches event paths with these patterns (separated by ;).'),
          argument('-i',
                   '--ignore-pattern',
                   '--ignore-patterns',
                   dest='ignore_patterns',
                   default='',
                   help='ignores event paths with these patterns (separated by ;).'),
          argument('-D',
                   '--ignore-directories',
                   dest='ignore_directories',
                   default=False,
                   action='store_true',
                   help='ignores events for directories'),
          argument('-R',
                   '--recursive',
                   dest='recursive',
                   default=False,
                   action='store_true',
                   help='monitors the directories recursively'),
          argument('--interval',
                   '--timeout',
                   dest='timeout',
                   default=1.0,
                   type=float,
                   help='use this as the polling interval/blocking timeout'),
          argument('-w', '--wait',
                   dest='wait_for_process',
                   action='store_true',
                   default=False,
                   help="wait for process to finish to avoid multiple simultaneous instances"),
          argument('-W', '--drop',
                   dest='drop_during_process',
                   action='store_true',
                   default=False,
                   help="Ignore events that occur while command is still being executed "
                   "to avoid multiple simultaneous instances"),
          argument('--debug-force-polling',
                   default=False,
                   help='[debug] forces polling')])
def shell_command(args):
    """
    command to execute shell commands in response to file system events.

    :param args:
        Command line argument options.
    """
    from watchdog.tricks import ShellCommandTrick

    if not args.command:
        args.command = None

    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    else:
        from watchdog.observers import Observer

    patterns, ignore_patterns = parse_patterns(args.patterns,
                                               args.ignore_patterns)
    handler = ShellCommandTrick(shell_command=args.command,
                                patterns=patterns,
                                ignore_patterns=ignore_patterns,
                                ignore_directories=args.ignore_directories,
                                wait_for_process=args.wait_for_process,
                                drop_during_process=args.drop_during_process)
    observer = Observer(timeout=args.timeout)
    observe_with(observer, handler, args.directories, args.recursive)


@command([argument('command',
                   help='''Long-running command to run in a subprocess.'''),
          argument('command_args',
                   metavar='arg',
                   nargs='*',
                   help='''Command arguments.

    Note: Use -- before the command arguments, otherwise watchmedo will
    try to interpret them.
    '''),
          argument('-d',
                   '--directory',
                   dest='directories',
                   metavar='directory',
                   action='append',
                   help='Directory to watch. Use another -d or --directory option '
                   'for each directory.'),
          argument('-p',
                   '--pattern',
                   '--patterns',
                   dest='patterns',
                   default='*',
                   help='matches event paths with these patterns (separated by ;).'),
          argument('-i',
                   '--ignore-pattern',
                   '--ignore-patterns',
                   dest='ignore_patterns',
                   default='',
                   help='ignores event paths with these patterns (separated by ;).'),
          argument('-D',
                   '--ignore-directories',
                   dest='ignore_directories',
                   default=False,
                   action='store_true',
                   help='ignores events for directories'),
          argument('-R',
                   '--recursive',
                   dest='recursive',
                   default=False,
                   action='store_true',
                   help='monitors the directories recursively'),
          argument('--interval',
                   '--timeout',
                   dest='timeout',
                   default=1.0,
                   type=float,
                   help='use this as the polling interval/blocking timeout'),
          argument('--signal',
                   dest='signal',
                   default='SIGINT',
                   help='stop the subprocess with this signal (default SIGINT)'),
          argument('--debug-force-polling',
                   default=False,
                   help='[debug] forces polling'),
          argument('--kill-after',
                   dest='kill_after',
                   default=10.0,
                   help='when stopping, kill the subprocess after the specified timeout '
                   '(default 10)')])
def auto_restart(args):
    """
    command to start a long-running subprocess and restart it
    on matched events.

    :param args:
        Command line argument options.
    """

    if args.debug_force_polling:
        from watchdog.observers.polling import PollingObserver as Observer
    else:
        from watchdog.observers import Observer

    from watchdog.tricks import AutoRestartTrick
    import signal

    if not args.directories:
        args.directories = ['.']

    # Allow either signal name or number.
    if args.signal.startswith("SIG"):
        stop_signal = getattr(signal, args.signal)
    else:
        stop_signal = int(args.signal)

    # Handle termination signals by raising a semantic exception which will
    # allow us to gracefully unwind and stop the observer
    termination_signals = {signal.SIGTERM, signal.SIGINT}

    def handler_termination_signal(_signum, _frame):
        # Neuter all signals so that we don't attempt a double shutdown
        for signum in termination_signals:
            signal.signal(signum, signal.SIG_IGN)
        raise WatchdogShutdown

    for signum in termination_signals:
        signal.signal(signum, handler_termination_signal)

    patterns, ignore_patterns = parse_patterns(args.patterns,
                                               args.ignore_patterns)
    command = [args.command]
    command.extend(args.command_args)
    handler = AutoRestartTrick(command=command,
                               patterns=patterns,
                               ignore_patterns=ignore_patterns,
                               ignore_directories=args.ignore_directories,
                               stop_signal=stop_signal,
                               kill_after=args.kill_after)
    handler.start()
    observer = Observer(timeout=args.timeout)
    try:
        observe_with(observer, handler, args.directories, args.recursive)
    except WatchdogShutdown:
        pass
    finally:
        handler.stop()


def main():
    """Entry-point function."""
    args = cli.parse_args()
    if args.command is None:
        cli.print_help()
    else:
        args.func(args)


if __name__ == '__main__':
    main()
