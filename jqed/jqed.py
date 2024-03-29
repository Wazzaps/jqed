#!/usr/bin/env python3
import sys
import urwid
import urwid_readline
import os
import subprocess as sp
import shutil
import shlex
import select
import platform
import re

VERSION = 'v0.1.4 (2021-09-07)'

PROMPT = 'jq> '
PAUSED_PROMPT_A = '||'
PAUSED_PROMPT_B = '> '

IS_WSL = "Microsoft" in platform.platform()

palette = [
    ('prompt_ok', 'light green,bold', 'default'),
    ('prompt_paused', 'yellow,bold', 'default'),
    ('prompt_err', 'light red,bold', 'default'),
    ('inp_plain', 'bold', 'default'),
    ('body_plain', '', 'default'),
    ('err_bar', 'light red,bold', 'default'),
]

# Forgive me for I have sinned:
inp = None
err_bar = None
orig_stdin = None
orig_stdout = None
body = None
loop = None
jq_man = None

class JqManager:
    def __init__(self, inp_file, loop):
        self.inp_file = inp_file
        self.loop = loop

        self.loop.event_loop.watch_file(self.inp_file.fileno(), self._file_avail_cb)
        self.inp_data = ''
        self.last_out_data = ''
        self.out_data = ''
        self.out_err = ''
        self.scroll_line = 0

        self.paused = False
        self.prompt_ok = True
        self.is_inp_data_done = False
        self._jq_path = shutil.which('jq')
        if not self._jq_path:
            try:
                orig_stdout.write('jq does not seem to be installed\nPerhaps you want: sudo apt install jq\n'.encode())
            except BrokenPipeError:
                sys.stderr.write('jq does not seem to be installed\nPerhaps you want: sudo apt install jq\n')
            exit(1)
        self.jq_proc = None
        self.respawn_jq(None, inp.get_edit_text())

        urwid.connect_signal(inp, 'change', self.respawn_jq)

    def _file_avail_cb(self):
        chunk = orig_stdin.read(1024)
        if len(chunk) != 0:
            self.inp_data += chunk
            try:
                self.jq_proc.stdin.write(chunk)
            except ValueError:
                # if `self.jq_proc.stdin` was closed
                pass
        else:
            self.loop.event_loop.remove_watch_file(orig_stdin.fileno())
            self.is_inp_data_done = True
            self.jq_proc.stdin.close()

    def toggle_pause(self):
        self.paused = not self.paused
        if self.out_data != '':
            self.last_out_data = self.out_data
        if self.prompt_ok:
            self.update_body()
        if self.paused:
            if self.prompt_ok:
                inp.set_caption([('prompt_paused', PAUSED_PROMPT_A), ('prompt_ok', PAUSED_PROMPT_B)])
            else:
                inp.set_caption([('prompt_paused', PAUSED_PROMPT_A), ('prompt_err', PAUSED_PROMPT_B)])
            self.loop.event_loop.remove_watch_file(self.inp_file.fileno())
        else:
            if self.prompt_ok:
                inp.set_caption(('prompt_ok', PROMPT))
            else:
                inp.set_caption(('prompt_err', PROMPT))
            self.loop.event_loop.watch_file(self.inp_file.fileno(), self._file_avail_cb)

    def _jq_out_avail_cb(self):
        if self.jq_proc.stdout not in select.select([self.jq_proc.stdout], [], [], 0)[0]:
            # Ignore spurius calls
            return

        chunk = ''
        while self.jq_proc.stdout in select.select([self.jq_proc.stdout], [], [], 0)[0]:
            new_chunk = self.jq_proc.stdout.read(1024)
            if len(new_chunk) == 0:
                break
            chunk += new_chunk

        if len(chunk) != 0:
            self.out_data += chunk
            if not self.paused:
                self.update_body()
        else:
            if self.out_err == '':
                if loop.screen_size is not None:
                    new_scroll_line = min(max(len(self.out_data.split('\n')) - int(loop.screen_size[1] / 2), 0), self.scroll_line)
                    if new_scroll_line != self.scroll_line:
                        self.scroll_line = new_scroll_line
                    self.update_body()
            self.loop.event_loop.remove_watch_file(self.jq_proc.stdout.fileno())
            self.jq_proc.stdout.close()
            self.jq_proc.stdin.close()
            self.jq_proc.wait()

    def _jq_err_avail_cb(self):
        if self.jq_proc.stderr not in select.select([self.jq_proc.stderr], [], [], 0)[0]:
            # Ignore spurius calls
            return

        chunk = ''
        while self.jq_proc.stderr in select.select([self.jq_proc.stderr], [], [], 0)[0]:
            new_chunk = self.jq_proc.stderr.read(1024)
            if len(new_chunk) == 0:
                break
            chunk += new_chunk

        if len(chunk) != 0:
            self.out_err += chunk
            err_bar.set_text(self.out_err.replace(' (Unix shell quoting issues?)', '').strip())
        else:
            self.loop.event_loop.remove_watch_file(self.jq_proc.stderr.fileno())
            self.jq_proc.stderr.close()

        if self.out_err != '':
            self.prompt_ok = False

            if self.paused:
                inp.set_caption([('prompt_paused', PAUSED_PROMPT_A), ('prompt_err', PAUSED_PROMPT_B)])
            else:
                inp.set_caption(('prompt_err', PROMPT))
        elif self.out_data == '':
            self.last_out_data = ''
            self.update_body()

    def respawn_jq(self, _, query):
        if self.jq_proc is not None:
            if not self.jq_proc.stdout.closed:
                self.loop.event_loop.remove_watch_file(self.jq_proc.stdout.fileno())
            if not self.jq_proc.stderr.closed:
                self.loop.event_loop.remove_watch_file(self.jq_proc.stderr.fileno())
            self.jq_proc.stdin.close()
            self.jq_proc.stdout.close()
            self.jq_proc.stderr.close()
            self.jq_proc.terminate()
            self.jq_proc.wait()
            err_bar.set_text('')
        if self.out_data != '' and not self.paused:
            self.last_out_data = self.out_data
        self.out_data = ''
        self.out_err = ''
        self.prompt_ok = True
        if self.paused:
            inp.set_caption([('prompt_paused', PAUSED_PROMPT_A), ('prompt_ok', PAUSED_PROMPT_B)])
        else:
            inp.set_caption(('prompt_ok', PROMPT))

        self.jq_proc = sp.Popen([self._jq_path, query], stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, bufsize=0, text=True)
        try:
            try:
                for offset in range(0, len(self.inp_data), 1024):
                    self.jq_proc.stdin.write(self.inp_data[offset:offset+1024])
                    self._jq_out_avail_cb()
                    self._jq_err_avail_cb()
                if self.is_inp_data_done:
                    self.jq_proc.stdin.close()
                self.loop.event_loop.watch_file(self.jq_proc.stdout.fileno(), self._jq_out_avail_cb)
                self.loop.event_loop.watch_file(self.jq_proc.stderr.fileno(), self._jq_err_avail_cb)
            except ValueError:
                pass
        except BrokenPipeError:
            pass

    def update_body(self):
        height = 256
        if self.loop.screen_size is not None:
            height = self.loop.screen_size[1]

        if self.out_data and not self.paused:
            body.set_text('\n'.join(self.out_data.split('\n')[self.scroll_line:][:height]))
        else:
            body.set_text('\n'.join(self.last_out_data.split('\n')[self.scroll_line:][:height]))

class BetterEdit(urwid_readline.ReadlineEdit):
    def keypress(self, size, key):
        if key == 'ctrl left':
            try:
                self.edit_pos = self.edit_text[:self.edit_pos].rindex(' ')
            except ValueError:
                self.edit_pos = 0
        elif key == 'ctrl right':
            try:
                self.edit_pos += self.edit_text[self.edit_pos:].index(' ') + 1
            except ValueError:
                self.edit_pos = len(self.edit_text)
        elif key == 'ctrl p':
            jq_man.toggle_pause()
        elif key in ('up', 'down', 'page up', 'page down'):
            if key == 'up':
                jq_man.scroll_line = max(0, jq_man.scroll_line - 1)
            elif key == 'down':
                jq_man.scroll_line = min(max(len(jq_man.out_data.split('\n')) - int(loop.screen_size[1] / 2), 0), jq_man.scroll_line + 1)
            elif key == 'page up':
                jq_man.scroll_line = max(0, jq_man.scroll_line - int(loop.screen_size[1] / 2))
            elif key == 'page down':
                jq_man.scroll_line = min(max(len(jq_man.out_data.split('\n')) - int(loop.screen_size[1] / 2), 0), jq_man.scroll_line + int(loop.screen_size[1] / 2))
            jq_man.update_body()
        else:
            return super().keypress(size, key)


class WSLScreen(urwid.raw_display.Screen):
    """
    This class is used to fix issue #6, where urwid has artifacts under WSL
    """
    def write(self, data):
        # replace urwid's SI/SO, which produce artifacts under WSL.
        # at some point we may figure out what they actually do.
        data = re.sub("[\x0e\x0f]", "", data)
        super().write(data)


def cli():
    global inp, err_bar, orig_stdin, orig_stdout, body, loop, jq_man
    if sys.stdin.isatty():
        sys.stderr.write('error: jqed requires some data piped on standard input, for example try: `ip --json link | jqed`\n')
        exit(1)

    if len(sys.argv) > 2:
        sys.stderr.write('usage: jqed [initial expression]\n')
        exit(1)

    # Preserve original stdio, and replace stdio with /dev/tty
    orig_stdin = os.fdopen(os.dup(sys.stdin.fileno()))
    orig_stdout = os.fdopen(os.dup(sys.stdout.fileno()), mode='wb', buffering=0)

    os.close(0)
    os.close(1)
    sys.stdin = open('/dev/tty', 'rb')
    sys.stdout = open('/dev/tty', 'wb')

    # Apparently urwid has some artifacts with WSL, see issue #6
    # Hopefully this won't break WSL2
    if IS_WSL:
        urwid_screen = WSLScreen()
    else:
        urwid_screen = urwid.raw_display.Screen()


    # Create gui
    inp = BetterEdit(('prompt_ok', PROMPT))
    if len(sys.argv) == 2:
        # If the user specified an argument, use it as an initial expression
        inp.set_edit_text(sys.argv[1])
        inp.set_edit_pos(len(sys.argv[1]))
    body = urwid.Text('')
    body_filler = urwid.AttrMap(urwid.Filler(body, 'top'), 'body_plain')
    err_bar = urwid.Text(('inp_plain', 'HELP: ^C: Exit, ^P: Pause, jq manual: https://stedolan.github.io/jq/manual'))

    frame = urwid.Frame(
        body_filler,
        header=urwid.AttrMap(inp, 'inp_plain'),
        footer=urwid.AttrMap(err_bar, 'err_bar'),
        focus_part='header'
    )
    loop = urwid.MainLoop(frame, palette, handle_mouse=False, screen=urwid_screen)
    try:
        jq_man = JqManager(orig_stdin, loop)
        loop.run()
    except KeyboardInterrupt:
        line = shlex.quote(inp.edit_text.strip())
        if line.startswith("''"):
            line = line[2:]
        if line.endswith("''"):
            line = line[:-2]
        try:
            orig_stdout.write(
                ('{}\njqed: jq editor ' + VERSION + ' https://github.com/wazzaps/jqed\n' +
                'jqed: | jq {}\n').format(jq_man.out_data, line).encode())
        except BrokenPipeError:
            sys.stderr.write('jq {}\n'.format(line))
        exit(0)


if __name__ == '__main__':
    cli()
