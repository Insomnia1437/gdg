# -*- coding: utf-8 -*-
# @Time    : 2020-09-15
# @File    : gui.py
# @Software: PyCharm
# @Author  : Di Wang(KEK Linac)
# @Email   : sdcswd@post.kek.jp
import os
import sys
from datetime import datetime
import queue
import PySimpleGUI as sg
from telnet import gdg_tn

GDG_MACHINES = {
    "gdg1": "172.19.68.136",
    "gdg2": "172.19.68.137",
    "gdg3": "172.19.68.138",
    "gdg4": "172.19.68.198",
    "gdg5": "172.19.68.199",
    "gdg7": "172.19.68.209",
    "gdg8": "172.19.68.210",
    "gdg6": "172.19.68.220",
    "gdg9": "172.19.68.229",
    "gdg10": "172.19.68.148"}
key_ch = ['a', 'b']
key_type = ['tp_none', 'delay', 'width']
key_mode = ['md_none', 'first', 'last']
key_ctrl = ['ct_none', 'enable', 'disable']


class GdgGUI:
    def __init__(self):
        self.author = 'author = Di WANG\n'
        self.basename = 'basename = %s\n' % sys.path[0]
        self.path = 'path = %s\n' % sys.executable
        self.version = 'Version = v0.1\n'
        self.title = 'GDG (Tsuji) Control Panel'
        self.start_time = "Start Time = %s\n" % datetime.now()
        self.pid = "pid = %s\n" % (str(os.getpid()))

        try:
            self.hostname = "hostname = %s\n" % (os.environ["HOSTNAME"])
            self.user = "user = %s\n" % (os.environ["LOGNAME"])
            self.display = "display = %s\n" % (os.environ["DISPLAY"])
        except KeyError:
            self.hostname = "hostname = ?\n"
            self.user = "user = ?\n"
            self.display = "display = ?\n"

        self.window = self.create_widget()
        self.connected = False

    def create_widget(self):
        # Use a light theme and larger, readable system font
        sg.theme('LightGrey1')
        sg.set_options(font=('Segoe UI', 14))
        # define menu
        menu_def = [['&Help', 'version']]

        # Host selection column (compact list + manual input)
        host_radios = [[sg.Radio('None', 'hosts', key='host_none', default=True)]]
        # split radios into multiple columns for better visual density
        radios = [sg.Radio(k, 'hosts', key=k, tooltip=v) for k, v in GDG_MACHINES.items()]
        # chunk radios into rows of 3
        row = []
        for i, r in enumerate(radios, 1):
            row.append(r)
            if i % 3 == 0:
                host_radios.append(row)
                row = []
        if row:
            host_radios.append(row)

        connection_col = sg.Column([
            [sg.Text('GDG Hosts', font=('Segoe UI', 12, 'bold'))],
            *host_radios,
            [sg.Text('Other host / IP:'), sg.Input('', key='inp_host', size=(18, 1))],
            [sg.Button('Connect', key='connect', size=(10, 1), button_color=('white', '#007ACC')), 
             sg.Button('Disconnect', key='disconnect', size=(10, 1))],
            [sg.Text('Status:'), sg.Text('not connected...', key='connected', size=(28, 1), text_color='#007700')]
        ], vertical_alignment='top', background_color='white')

        # Channel read/display
        channel_col = sg.Column([
            [sg.Text('Current (delay_A, width_A, delay_B, width_B)', font=('Segoe UI', 13, 'bold'))],
            [sg.Multiline('00000000.0, 00000000.0, 00000000.0, 00000000.0', key='output_val', size=(60, 2),
                          disabled=True, text_color='#B22222', background_color='white')],
            [sg.Button('Read', key='read', size=(10, 1))]
        ], vertical_alignment='top', background_color='white')

        # GDG setting controls
        channel_frame = sg.Frame(title='Output Channel', layout=[[sg.Radio('A', 'out_ch', key=key_ch[0], default=True),
                                                                  sg.Radio('B', 'out_ch', key=key_ch[1])]])
        type_frame = sg.Frame(title='Output Type', layout=[[sg.Radio('None', 'out_type', key=key_type[0], default=True),
                                                            sg.Radio('Delay', 'out_type', key=key_type[1]),
                                                            sg.Radio('Width', 'out_type', key=key_type[2]),
                                                            sg.Input('000', key='inp_val', size=(12, 1),
                                                                     tooltip='delay: 0.1 ~ 15999999.9 us; width: 0.1 us ~ 10 s')]])

        mode_frame = sg.Frame(title='Trigger Mode', layout=[[sg.Radio('None', 'out_mode', key=key_mode[0], default=True),
                                                              sg.Radio('First', 'out_mode', key=key_mode[1]),
                                                              sg.Radio('Last', 'out_mode', key=key_mode[2])]], tooltip='Choose one')
        ctrl_frame = sg.Frame(title='Output Control', layout=[[sg.Radio('None', 'out_ctrl', key=key_ctrl[0], default=True),
                                                               sg.Radio('enable', 'out_ctrl', key=key_ctrl[1]),
                                                               sg.Radio('disable', 'out_ctrl', key=key_ctrl[2])]], tooltip='Choose one')

        settings_col = sg.Column([
            [channel_frame, type_frame],
            [mode_frame, ctrl_frame, sg.Button('Write', key='write', size=(10, 1), button_color=('white', '#007ACC'))],
            [sg.Frame(title='Auto Run', layout=[[sg.Text('Step (us)'), sg.Input('', key='inp_step', size=(10, 1)),
                                               sg.Text('Duration (s)'), sg.Input('', key='inp_duration', size=(10, 1)),
                                               sg.Button('Autorun', key='autorun', size=(10, 1), button_color=('white', '#007ACC'))]])]
        ], vertical_alignment='top')
        settings_col.BackgroundColor = 'white'

        # Log area
        log_col = sg.Frame(title='Log', layout=[[sg.Multiline('', key='out_log', size=(100, 10), disabled=True,
                               autoscroll=True, text_color='#B22222', background_color='white')]], element_justification='left')

        layout = [
            [sg.Menu(menu_def, background_color='white', tearoff=False)],
            [connection_col, sg.VerticalSeparator(), channel_col],
            [sg.HorizontalSeparator()],
            [settings_col],
            [log_col],
            [sg.Push(), sg.Button('Exit', size=(8, 1))]
        ]

        # create window with a fixed size and center it to avoid tiling WMs forcing fullscreen
        win = sg.Window(self.title, layout=layout, finalize=True, resizable=False, background_color='white')
        try:
            tk = win.TKroot
            # Hint the window manager to treat this as a dialog/utility window (may make it float)
            try:
                tk.wm_attributes("-type", "dialog")
            except Exception:
                pass
            # set a sensible fixed size and center on screen
            width, height = 1100, 800
            sw = tk.winfo_screenwidth()
            sh = tk.winfo_screenheight()
            x = int((sw - width) / 2)
            y = int((sh - height) / 2)
            tk.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            # final fallback: ignore if TKroot not available or attributes unsupported
            pass
        return win

    def info_popup(self):
        ver_string = self.author + self.user + self.pid + self.hostname + self.display + \
                     self.start_time + self.basename + self.path + self.version
        sg.PopupScrolled(ver_string, size=(60, 10), title='About', button_color=('blue', 'white'),
                         background_color='white')

    def set_connected(self, h):
        if self.connected:
            self.window['connected'].update('Connected to ' + h)
        else:
            self.window['connected'].update('not connected...')

    def run(self):
        client = gdg_tn.TelnetClient(debug=False)
        # client.connect()
        host = None
        while True:
            event, values = self.window.read(timeout=100)
            if event in ('Exit', None):
                break
            if event == 'connect':
                if host:
                    sg.popup_error('please disconnect from current host first!')
                    continue
                for h in GDG_MACHINES.keys():
                    if values[h]:
                        host = h
                        break
                if not host:
                    inp_host = values['inp_host']
                    if inp_host == "":
                        sg.popup_error('please select a host or input one!')
                        continue
                    host = inp_host
                if client.connect(host):
                    client.logger.info("connect to " + host)
                    self.connected = True
                    self.set_connected(host)
                else:
                    sg.popup_error("Error when connecting to host %s" % host)
            if event == 'disconnect':
                if not host:
                    sg.popup_error("already disconnected!")
                    continue
                client.logger.info("disconnect from host %s" % host)
                client.logout()
                host = None
                self.connected = False
                self.set_connected(host)
            if event == 'read':
                if not self.connected:
                    sg.popup_error("please connect to a host first!")
                    continue
                if not host:
                    sg.popup_error("no host founded")
                    continue
                resp = client.read_all()
                # resp = "test"
                if resp == "":
                    client.logger.error("Return empty string from host")
                else:
                    self.window['output_val'].update(resp)
            if event == 'write':
                if not self.connected:
                    sg.popup_error("please connect to a host first!")
                    continue
                if not host:
                    sg.popup_error("no host founded")
                    continue
                selected_ch = [k for k in key_ch if values[k]][0]
                selected_tp = [k for k in key_type if values[k]][0]
                selected_md = [k for k in key_mode if values[k]][0]
                selected_ctrl = [k for k in key_ctrl if values[k]][0]
                inp_val = values['inp_val']
                # client.logger.info(
                #     "selected %s %s %s %s %s" % (selected_ch, selected_tp, selected_md, selected_ctrl, inp_val))
                if not selected_tp == key_type[0]:
                    if client.set_delay(selected_ch, selected_tp, inp_val):
                        sg.popup_ok("Set delay success!")
                if not selected_md == key_mode[0]:
                    if client.set_trigger_mode(selected_ch, selected_md):
                        sg.popup_ok("Set trigger mode success!")
                if not selected_ctrl == key_ctrl[0]:
                    if client.set_control(selected_ch, selected_ctrl):
                        sg.popup_ok("Set output control success!")
            if event == 'autorun':
                if not self.connected:
                    sg.popup_error("please connect to a host first!")
                    continue
                if not host:
                    sg.popup_error("no host founded")
                    continue
                selected_ch = [k for k in key_ch if values[k]][0]
                inp_step = int(values['inp_step'])
                inp_duration = int(values['inp_duration'])
                client.autorun(selected_ch, inp_step, inp_duration)
            if event == 'version':
                self.info_popup()
            # Poll queue
            try:
                record = client.log_queue.get(block=False)
            except queue.Empty:
                pass
            else:
                msg = client.queue_handler.format(record)
                self.window['out_log'].update(msg + '\n', append=True)

        self.window.close()


if __name__ == '__main__':
    gdg_gui = GdgGUI()
    gdg_gui.run()
