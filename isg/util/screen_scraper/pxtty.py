"""pxtty adds terminal emulation support to the pexpect spawn class.
It does this by keeping a VT100 object handy and feeding all read
input data to it.

"""

import ANSI
import time

from pexpect import EOF, TIMEOUT
from pexpect import spawn as pexpect_spawn

READ_CHUNK_SIZE=1024

__all__ = ['pxtty']

class spawn(pexpect_spawn):
    def __init__(self, command, term, timeout=30, maxread=2000, searchwindowsize=None, logfile=None, cwd=None, env=None):
        assert isinstance(term, ANSI.term), 'pxtty should be passed a terminal instance'
        pexpect_spawn.__init__(self, command, timeout=timeout, maxread=maxread, searchwindowsize=searchwindowsize, logfile=logfile, cwd=cwd, env=env)
        self.term = term
        self.logfiles_read.append(self.term)
        ## TODO: if we're set for local echo, also logfiles_send and logfiles_interact
    def expect_delay(self, delay_time, timeout=30, resolution=0.25, require_input=0):
        """Wait for input to settle for a period not less than delay_time.
        resolution specifies the delay between tests. Raises timeout if we fail
        to settle down within timeout seconds. If require_input is greater than
        zero, we will not start counting for delay until after require_input bytes have
        been read.
        """
        time_since_last_input = 0
        end_time = time.time() + timeout
        if require_input:
            self.read_nonblocking(size=int(require_input), timeout=timeout)
        while True:
            if time.time() > end_time:
                raise TIMEOUT('Client has not stopped sending data within %r seconds' % timeout)
            try:
                self.read_nonblocking(size=READ_CHUNK_SIZE, timeout=resolution)
                time_since_last_input = 0
            except TIMEOUT:
                time_since_last_input += resolution
                if time_since_last_input >= delay_time:
                    return
    def expect_cursor_position(self, row, column, timeout=30, resolution=0.05):
        """Expect the cursor to seek to a given row and column. Polls,
        so this should be used only in cases where the cursor settles
        on the correct position (rather than just passing through)."""
        end_time = time.time() + timeout
        if self.term.cur_r == row and self.term.cur_c == column:
            return
        while True:
            self.read_nonblocking(self.maxread, timeout)
            if (row is None or self.term.cur_r == row) and (column is None or self.term.cur_c == column):
                return
            if time.time() > end_time:
                raise TIMEOUT()
    def expect_line_matching(self, pattern, lineno=0, timeout=-1):
        """Expect a VT100 line to match pattern. If a lineno (which is
        indexed from 1) is given, expect that specific line to match;
        otherwise, any line can be a winner.
        WARNING: This consumes ALL of the incoming buffer.
        """
        compiled_pattern_list = self.compile_pattern_list(pattern)
        return self.expect_line_matching_list(compiled_pattern_list, lineno=lineno, timeout=timeout)
    def expect_line_matching_list(self, pattern_list, timeout=-1, lineno=0):
        if timeout == -1:
            timeout = self.timeout
        end_time = time.time() + timeout
        try:
            incoming = self.buffer
            while True:
                for cre in pattern_list:
                    if cre is EOF or cre is TIMEOUT:
                        continue
                    if lineno:
                        line = self.term.dump_row(lineno-1)
                        match = cre.search(line)
                    else:
                        for line in self.term.dump_rows():
                            match = cre.search(line)
                            if match is not None: break
                    if match is None: continue
                    self.buffer = ''
                    self.before = incoming
                    self.after = ''
                    self.match = match
                    self.match_index = pattern_list.index(cre)
                    return self.match_index
                c = self.read_nonblocking(self.maxread, timeout)
                time.sleep(0.0001)
                incoming += c
                if timeout is not None:
                    timeout = end_time - time.time()
                    if timeout < 0:
                        raise TIMEOUT('Timeout exceeded in expect_line_matching_list().')
        except EOF, e:
            self.buffer = ''
            self.before = incoming
            self.after = EOF
            if EOF in pattern_list:
                self.match = EOF
                self.match_index = pattern_list.index(EOF)
                return self.match_index
            else:
                self.match = None
                self.match_index = None
                raise EOF (str(e) + '\n' + str(self))
        except TIMEOUT, e:
            self.before = incoming
            self.after = TIMEOUT
            if TIMEOUT in pattern_list:
                self.match = TIMEOUT
                self.match_index = pattern_list.index(TIMEOUT)
                return self.match_index
            else:
                self.match = None
                self.match_index = None
                raise TIMEOUT(str(e) + '\n' + str(self))
        except Exception:
            self.before = incoming
            self.after = None
            self.match = None
            self.match_index = None
            raise

# vim: sw=4 ts=4 sts=4 sta et ai
