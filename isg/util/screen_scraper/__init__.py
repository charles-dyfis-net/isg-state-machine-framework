import logging
import os
import re
import sys

import ANSI

from isg.util.screen_scraper import pxtty
from isg.util.state_machine import HandlerSet
from isg.util.config import ConfigMixIn, UNDEFINED, integer_sort_order

__all__ = ['BaseConnection', 'KEYS', ]

logger = logging.getLogger(__name__)

# default keymappings
keys_dict = {
    'ESC': '\x1b',
    'UP': '\x1bOA',
    'DOWN': '\x1bOB',
    'RIGHT': '\x1bOC',
    'LEFT': '\x1bOD',
    'F1': '\x01',
    'F2': '\x02',
    'F3': '\x03',
    'F4': '\x04',
    'F5': '\x05',
    'F6': '\x06',
    'F7': '\x07',
    # below require xterm-style key support in termcap/terminfo
    'F8': '\x1b[19~',
    'F9': '\x1b[20~',
    'F10':'\x1b[21~',
    'F11':'\x1b[23~',
    'F12':'\x1b[24~',
}

class KEYS: """Container for key constants"""

for key in keys_dict.keys():
    setattr(KEYS, key, key)
del key

class BaseConnection(HandlerSet, ConfigMixIn):
    def __init__(self):
        ConfigMixIn.__init__(self)
        self.child = None
        self.term = ANSI.ANSI()
        super(BaseConnection, self).__init__()
    def cmd_connect(self):
        os.environ['TERM'] = self.config_get('General', 'term', default='ANSI')
        self.child = pxtty.spawn(self.config_get('Connect', 'spawnString'), self.term)
    def cmd_disconnect(self):
        self.transitionTo('DISCONNECTED')
    def sendline(self, content=None):
        if content:
            self.child.send(content)
        self.child.send(self.config_get('os', 'endline', decode=True))
    @property
    def settle_time(self):
        return self.config_get('General', 'settle_time', isFloat=True, default=0.5)
    def send_key(self, key):
        config_key = 'term_key_%s' % key
        if key in keys_dict:
            default = keys_dict[key]
        else:
            if not self.config_exists('os', config_key):
                raise KeyError('Key %r not defined' % key)
            default = UNDEFINED
        self.child.send(self.config_get('os', config_key, default=default, decode=True))
    def screen_dump(self, outfile=sys.stderr):
        cols = self.child.term.cols
        outfile.write('   ' + ''.join(['%10d' % (n+1) for n in range((cols / 10)+1)])[:cols] + '\n')
        outfile.write('   ' + ('1234567890' * ((cols / 10)+1))[:cols] + '\n')
        outfile.write('   ' + ('=' * cols) + '\n')
        rownum = 0
        for row in self.child.term.dump_rows():
            rownum += 1
            if rownum > 0 and rownum % 10 == 0:
                outfile.write('%1d' % (rownum / 10 % 10))
            else:
                outfile.write(' ')
            outfile.write('%1d' % (rownum % 10))
            outfile.write('|')
            outfile.write(row)
            outfile.write('\n')
        outfile.write('Cursor pos: (%d,%d)\n' % (self.child.term.cur_r, self.child.term.cur_c))
    def image_screen(self, expect_updates=False, settle_time=None, substate='default'):
        """Wait for the screen state to settle; then capture any content"""
        # FIXME: We only validate on the way in, not the way out -- so validate handlers are not inherited.
        # Probably each of these steps should be broken down into separate methods.
        current_handler = self._StateMachineHandler__current_handler
        current_state = self._StateMachineHandler__state
        current_class_name = current_handler.im_func._origin_class.__name__
        config_path = [
            'screens',
            current_class_name,
            current_state,
            substate,
        ]
        if settle_time is None:
            settle_time = self.settle_time
        ## wait for initial updates
        self.child.expect_delay(delay_time=settle_time, require_input=int(expect_updates))
        ## dump the screen if we're in debugging mode
        if self.config_get('General', 'dump_screen', isBoolean=True, default=False):
            self.screen_dump()
        ## validate any verify_* clauses
        for name, value in self.config_get_items(config_path, 'verify_'):
            logger.debug('Validating %r', ((name, value),))
            assert isinstance(value, list)
            assert len(value) == 2 or len(value) == 3
            if len(value) == 2:
                verify_timeout = settle_time
            else:
                verify_timeout = float(value[2])
            self.child.expect_line_matching(value[1], lineno=int(value[0]), timeout=verify_timeout)
        ## perform any redirects
        for name, value in self.config_get_items(config_path, 'redirect_', strip_prefix=True, sort=integer_sort_order):
            logger.debug('Processing redirect_%s (%r)', (name, value))
            if value[0] == 'regex':
                lineno, startcol, length = [ int(n) for n in value[1:4] ]
                re_text, target = value[4:6]
                text = self.child.term.get_region(lineno, startcol, lineno, startcol+length)[0]
                if re.match(re_text, text):
                    return self.image_screen(expect_updates=False, settle_time=settle_time, substate=target)
            elif value[0] == 'always':
                target = value[1]
                return self.image_screen(expect_updates=False, settle_time=settle_time, substate=target)
            elif value[0] == 'error':
                raise Exception(value[1:])
            else:
                raise Exception('Unknown redirect evaluation type: %r' % value[0])
        ## perform any captures
        if not hasattr(self, '_%s__data' % current_class_name):
            setattr(self, '_%s__data' % current_class_name, {})
        current_data_dict = getattr(self, '_%s__data' % current_class_name)
        while True:
            logger.debug('Evaluating captures for %r', config_path)
            for name, value in self.config_get_items(config_path, 'data__', strip_prefix=True):
                if value[0] == 'fixedpos':
                    lineno,startcol,length,strip = [ int(n) for n in value[1:] ]
                    retval = self.child.term.get_region(lineno, startcol, lineno, startcol+length)[0]
                    if strip:
                        retval = retval.strip()
                else:
                    raise Exception('Unknown data retrieval type: %r' % value[0])
                current_data_dict[name] = retval
            if not self.config_exists(config_path, 'inherit_from'):
                break
            config_path[2] = self.config_get(config_path, 'inherit_from')
    def do__INITIAL_STATE(self):
        return 'DISCONNECTED'
    def do__INVALID(self):
        self.cmd_disconnect()
    def do__DISCONNECTED(self):
        self.cmd_connect()
        return 'CONNECTING'
    def transition__default__to__DISCONNECTED(self):
        if self.child is not None:
            try:
                os.kill(self.child.pid, 15)
                os.waitpid(self.child.pid, 0)
            except OSError, e:
                logging.getLogger('OSConnection').error('Unable to kill process %s: %s' %
                                  (self.child.pid, str(e)))
            self.child = None
        self.resetStack()
        self.setState('DISCONNECTED')

# vim: sw=4 ts=4 sts=4 sta et ai
