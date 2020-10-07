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
        # sg.theme('Reddit')
        # sg.theme('GreenTan')
        sg.theme('lightgreen1')
        # define menu
        menu_def = [['&Help', 'version']]
        host_layout = [sg.Radio(k, group_id='hosts', key=k, tooltip=v) for k, v in GDG_MACHINES.items()]
        host_layout.insert(0, sg.Radio('None', group_id='hosts', key='host_none'))
        server_layout = sg.Frame(layout=[host_layout,
                                         [sg.Text('Others: input hostname or IP'),
                                          sg.Input('', key='inp_host', size=(20, 1)),
                                          sg.Button('Connect', key='connect'),
                                          sg.Text('not connected...', background_color='gray', text_color='blue',
                                                  key='connected', size=(20, 1)),
                                          sg.Button('Disconnect', key='disconnect')]
                                         ], title='GDG connection)')
        channel_read_layout = sg.Frame(layout=[
            [sg.Text('Current delay and width'),
             sg.Text('00000000.0, 00000000.0, 00000000.0, 00000000.0', key='output_val', text_color='red', size=(56, 1),
                     background_color='gray'),
             sg.Button('Read', key='read'),
             ]
        ], title='Channel (delay_A, width_A, delay_B, width_B)')

        gdg_set_layout = sg.Frame(layout=[
            [sg.Frame(
                layout=[[sg.Radio('A', 'out_ch', key=key_ch[0], default=True), sg.Radio('B', 'out_ch', key=key_ch[1])]],
                title='Output Channel'),
                sg.Frame(
                    layout=[[sg.Radio('None', 'out_type', key=key_type[0], default=True),
                             sg.Radio('Delay', 'out_type', key=key_type[1]),
                             sg.Radio('Width', 'out_type', key=key_type[2]),
                             sg.Input('000', key='inp_val',
                                      tooltip='delay value is between 0.1 ~ 15999999.9 us, pulse width is 0.1 us ~ 10 s')]],
                    title='Output Type')],
            [sg.Frame(
                layout=[
                    [sg.Radio('None', 'out_mode', key=key_mode[0], default=True),
                     sg.Radio('First', 'out_mode', key=key_mode[1]),
                     sg.Radio('Last', 'out_mode', key=key_mode[2])]],
                title='Trigger Mode', tooltip='Do not select multi options!'),
                sg.Frame(layout=[
                    [sg.Radio('None', 'out_ctrl', key=key_ctrl[0], default=True),
                     sg.Radio('enable', 'out_ctrl', key=key_ctrl[1]),
                     sg.Radio('disable', 'out_ctrl', key=key_ctrl[2])]],
                    title='Output Control', tooltip='Do not select multi options!'),
                sg.Button('Write', button_color=('white', 'blue'), border_width=5, size=(8, 2),
                          font=("Helvetica", 8), key='write')],
            [sg.Frame(layout=[
                [sg.Text('Step (us)'),
                 sg.Input('', key='inp_step', size=(10, 1)), sg.Text('duration (sec)'),
                 sg.Input('', key='inp_duration', size=(10, 1)),
                 sg.Button('Autorun', button_color=('white', 'blue'), border_width=4, size=(8, 1),
                           font=("Helvetica", 8), key='autorun')]
            ], title='Auto Run')]
        ], title='GDG Delay Setting')

        layout = [[sg.Menu(menu_def, background_color='white')],
                  [server_layout],
                  [channel_read_layout],
                  [gdg_set_layout],
                  [sg.Frame(title='Log', layout=[
                      [sg.ML(key='out_log', size=(120, 7),
                             text_color='red')]
                  ])],
                  [sg.Button('Exit')]]
        return sg.Window(self.title, layout=layout)

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
