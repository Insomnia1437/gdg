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
import re
import time
import threading
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
            self.hostname = "hostname = ?"
            self.user = "user = ?"
            self.display = "display = ?"

        self.window = self.create_widget()
        self.connected = False
        self.connection_in_progress = False
        self.ramp_running = False
        self.autorun_running = False
        self.ramp_thread = None
        self.ramp_stop_event = threading.Event()
        self.autorun_thread = None
        self.autorun_stop_event = threading.Event()
        self.connect_thread = None

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
            [sg.Frame('Parsed Status Monitor', [
                [sg.Text('Ch A Delay (us):'), sg.Input('0.0', key='status_delay_a', size=(12, 1), readonly=True, text_color='#B22222', background_color='white'),
                 sg.Text('Ch A Width (us):'), sg.Input('0.0', key='status_width_a', size=(12, 1), readonly=True, text_color='#B22222', background_color='white')],
                [sg.Text('Ch B Delay (us):'), sg.Input('0.0', key='status_delay_b', size=(12, 1), readonly=True, text_color='#B22222', background_color='white'),
                 sg.Text('Ch B Width (us):'), sg.Input('0.0', key='status_width_b', size=(12, 1), readonly=True, text_color='#B22222', background_color='white')]
            ], background_color='white')],
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
            [sg.Frame(title='Auto Run Sweep', layout=[
                [sg.Text('Start (us)'), sg.Input('0', key='inp_autorun_start', size=(8, 1)),
                 sg.Text('End (us)'), sg.Input('20000', key='inp_autorun_end', size=(8, 1)),
                 sg.Text('Step (us)'), sg.Input('', key='inp_step', size=(8, 1)),
                 sg.Text('Interval (s)'), sg.Input('', key='inp_interval', size=(8, 1))],
                [sg.Text('Pause Every (us)'), sg.Input('', key='inp_pause_every', size=(8, 1), tooltip='Optional. Pause sweep after every N us increase/decrease'),
                 sg.Text('Pause Time (s)'), sg.Input('', key='inp_pause_time', size=(8, 1), tooltip='Optional. Wait duration in seconds during pause')],
                [sg.Button('Start Sweep', key='autorun', size=(12, 1), button_color=('white', '#007ACC')),
                 sg.Button('Stop Sweep', key='stop_autorun', size=(12, 1), button_color=('white', '#CC3333'), disabled=True)]
            ])],
            [sg.Frame(title='Gradual Delay Control', layout=[
                [sg.Text('Target (us)'), sg.Input('', key='inp_target_delay', size=(10, 1)),
                 sg.Text('Step (us)'), sg.Input('', key='inp_ramp_step', size=(10, 1)),
                 sg.Text('Interval (s)'), sg.Input('', key='inp_ramp_interval', size=(10, 1))],
                [sg.Text('Pause Every (us)'), sg.Input('', key='inp_ramp_pause_every', size=(10, 1), tooltip='Optional. Pause ramp after every N us increase/decrease'),
                 sg.Text('Pause Time (s)'), sg.Input('', key='inp_ramp_pause_time', size=(10, 1), tooltip='Optional. Wait duration in seconds during pause')],
                [sg.Button('Start Ramp', key='start_ramp', size=(12, 1), button_color=('white', '#007ACC')),
                 sg.Button('Stop Ramp', key='stop_ramp', size=(12, 1), button_color=('white', '#CC3333'), disabled=True)]
            ])]
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
            [sg.Button('Save Log', key='save_log', size=(12, 1), button_color=('white', '#007ACC')),
             sg.Push(), sg.Button('Exit', size=(8, 1))]
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
            width, height = 1100, 920
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

    def update_control_states(self):
        # Enabled only when connected and no thread is active
        enabled = self.connected
        any_active = self.ramp_running or self.autorun_running or self.connection_in_progress

        # Connect / Disconnect buttons
        self.window['connect'].update(disabled=self.connected or any_active)
        self.window['disconnect'].update(disabled=not self.connected or any_active)

        # Read & Write control panels
        self.window['read'].update(disabled=not enabled or any_active)
        self.window['write'].update(disabled=not enabled or any_active)

        # Settings Inputs & Radio controls
        for k in key_ch + key_type + key_mode + key_ctrl + ['inp_val']:
            self.window[k].update(disabled=not enabled or any_active)

        # Auto Run Controls
        self.window['inp_autorun_start'].update(disabled=not enabled or any_active)
        self.window['inp_autorun_end'].update(disabled=not enabled or any_active)
        self.window['inp_step'].update(disabled=not enabled or any_active)
        self.window['inp_interval'].update(disabled=not enabled or any_active)
        self.window['inp_pause_every'].update(disabled=not enabled or any_active)
        self.window['inp_pause_time'].update(disabled=not enabled or any_active)
        self.window['autorun'].update(disabled=not enabled or any_active)
        self.window['stop_autorun'].update(disabled=not enabled or not self.autorun_running)

        # Gradual Ramp Controls
        self.window['inp_target_delay'].update(disabled=not enabled or any_active)
        self.window['inp_ramp_step'].update(disabled=not enabled or any_active)
        self.window['inp_ramp_interval'].update(disabled=not enabled or any_active)
        self.window['inp_ramp_pause_every'].update(disabled=not enabled or any_active)
        self.window['inp_ramp_pause_time'].update(disabled=not enabled or any_active)
        self.window['start_ramp'].update(disabled=not enabled or any_active)
        self.window['stop_ramp'].update(disabled=not enabled or not self.ramp_running)

    def execute_connect(self, client, host):
        success = client.connect(host)
        self.window.write_event_value('-CONNECT_FINISHED-', (host, success))

    def execute_autorun(self, client, ch, start, end, step, interval, pause_every=None, pause_time=None):
        client.logger.info(f"Start auto sweep for channel {ch.upper()}: {start} us -> {end} us (step: {step} us, interval: {interval} s)")
        if pause_every and pause_time:
            client.logger.info(f"Sweep pause configured: every {pause_every} us for {pause_time} s")
        current = start
        last_pause_val = start
        try:
            if start <= end:
                while current <= end:
                    if self.autorun_stop_event.is_set():
                        client.logger.info("Sweep cancelled by user.")
                        break
                    val_str = f"{current:.1f}"
                    if not client.set_delay(ch, "delay", val_str):
                        client.logger.error(f"Failed to set delay to {val_str} us. Aborting sweep.")
                        break

                    if pause_every and pause_time and abs(current - last_pause_val) >= pause_every - 1e-9:
                        client.logger.info(f"Delay change reached {abs(current - last_pause_val):.1f} us (>= {pause_every:.1f} us). Pausing sweep for {pause_time:.1f} s...")
                        last_pause_val = current
                        slept = 0.0
                        last_log_time = 0.0
                        while slept < pause_time:
                            if self.autorun_stop_event.is_set():
                                break
                            if slept - last_log_time >= 10.0:
                                client.logger.info(f"Pause ongoing: {pause_time - slept:.0f} s remaining...")
                                last_log_time = slept
                            time.sleep(0.1)
                            slept += 0.1
                    else:
                        slept = 0.0
                        while slept < interval:
                            if self.autorun_stop_event.is_set():
                                break
                            time.sleep(0.05)
                            slept += 0.05

                    if self.autorun_stop_event.is_set():
                        client.logger.info("Sweep cancelled by user.")
                        break

                    if current == end:
                        break
                    current = min(current + step, end)
            else:
                while current >= end:
                    if self.autorun_stop_event.is_set():
                        client.logger.info("Sweep cancelled by user.")
                        break
                    val_str = f"{current:.1f}"
                    if not client.set_delay(ch, "delay", val_str):
                        client.logger.error(f"Failed to set delay to {val_str} us. Aborting sweep.")
                        break

                    if pause_every and pause_time and abs(current - last_pause_val) >= pause_every - 1e-9:
                        client.logger.info(f"Delay change reached {abs(current - last_pause_val):.1f} us (>= {pause_every:.1f} us). Pausing sweep for {pause_time:.1f} s...")
                        last_pause_val = current
                        slept = 0.0
                        last_log_time = 0.0
                        while slept < pause_time:
                            if self.autorun_stop_event.is_set():
                                break
                            if slept - last_log_time >= 10.0:
                                client.logger.info(f"Pause ongoing: {pause_time - slept:.0f} s remaining...")
                                last_log_time = slept
                            time.sleep(0.1)
                            slept += 0.1
                    else:
                        slept = 0.0
                        while slept < interval:
                            if self.autorun_stop_event.is_set():
                                break
                            time.sleep(0.05)
                            slept += 0.05

                    if self.autorun_stop_event.is_set():
                        client.logger.info("Sweep cancelled by user.")
                        break

                    if current == end:
                        break
                    current = max(current - step, end)

            if not self.autorun_stop_event.is_set():
                client.logger.info(f"Auto sweep completed successfully at {end:.1f} us.")
        except Exception as e:
            client.logger.error(f"Error in sweep thread: {str(e)}")
        finally:
            self.window.write_event_value('-AUTORUN_FINISHED-', None)

    def parse_and_update_status_monitor(self, resp):
        if not resp:
            return
        # Strip control characters to avoid breaking number boundaries
        cleaned_resp = "".join(c for c in resp if 32 <= ord(c) < 127 or c in '\r\n\t')
        numbers = re.findall(r'[-+]?\d*\.\d+|\d+', cleaned_resp)
        if len(numbers) >= 4:
            try:
                self.window['status_delay_a'].update(f"{float(numbers[0]):.1f}")
                self.window['status_width_a'].update(f"{float(numbers[1]):.1f}")
                self.window['status_delay_b'].update(f"{float(numbers[2]):.1f}")
                self.window['status_width_b'].update(f"{float(numbers[3]):.1f}")
            except ValueError:
                pass

    def get_current_delay(self, client, ch):
        """
        Queries current settings via client.read_all() and parses the delay
        for the selected channel (A or B).
        """
        resp = client.read_all()
        if not resp:
            return None
        self.parse_and_update_status_monitor(resp)
        # Extract all float or integer numbers
        cleaned_resp = "".join(c for c in resp if 32 <= ord(c) < 127 or c in '\r\n\t')
        numbers = re.findall(r'[-+]?\d*\.\d+|\d+', cleaned_resp)
        if len(numbers) < 4:
            client.logger.error("Could not parse enough parameters from read_all response: '%s'" % resp)
            return None

        try:
            if ch.lower() == 'a':
                return float(numbers[0])
            elif ch.lower() == 'b':
                return float(numbers[2])
            else:
                client.logger.error("Invalid channel: %s" % ch)
                return None
        except (ValueError, IndexError) as e:
            client.logger.error("Error parsing delay values: %s" % str(e))
            return None

    def execute_ramp(self, client, ch, start, target, step, interval, pause_every=None, pause_time=None):
        """
        Background thread target that incrementally steps the delay value
        from 'start' to 'target' with 'step' increment and 'interval' seconds.
        """
        current = start
        last_pause_val = start
        client.logger.info(f"Start gradual delay ramp for channel {ch.upper()}: {start} us -> {target} us (step: {step} us, interval: {interval} s)")
        if pause_every and pause_time:
            client.logger.info(f"Ramp pause configured: every {pause_every} us for {pause_time} s")

        try:
            if start < target:
                while current < target:
                    if self.ramp_stop_event.is_set():
                        client.logger.info("Ramping cancelled by user.")
                        break
                    current = min(current + step, target)
                    val_str = f"{current:.1f}"
                    if not client.set_delay(ch, "delay", val_str):
                        client.logger.error(f"Failed to set delay to {val_str} us. Aborting ramp.")
                        break

                    if pause_every and pause_time and abs(current - last_pause_val) >= pause_every - 1e-9:
                        client.logger.info(f"Delay change reached {abs(current - last_pause_val):.1f} us (>= {pause_every:.1f} us). Pausing ramp for {pause_time:.1f} s...")
                        last_pause_val = current
                        slept = 0.0
                        last_log_time = 0.0
                        while slept < pause_time:
                            if self.ramp_stop_event.is_set():
                                break
                            if slept - last_log_time >= 10.0:
                                client.logger.info(f"Pause ongoing: {pause_time - slept:.0f} s remaining...")
                                last_log_time = slept
                            time.sleep(0.1)
                            slept += 0.1
                    else:
                        # Sleep in small chunks to check the cancellation event frequently
                        slept = 0.0
                        while slept < interval:
                            if self.ramp_stop_event.is_set():
                                break
                            time.sleep(0.05)
                            slept += 0.05

                    if self.ramp_stop_event.is_set():
                        client.logger.info("Ramping cancelled by user.")
                        break
            else:
                while current > target:
                    if self.ramp_stop_event.is_set():
                        client.logger.info("Ramping cancelled by user.")
                        break
                    current = max(current - step, target)
                    val_str = f"{current:.1f}"
                    if not client.set_delay(ch, "delay", val_str):
                        client.logger.error(f"Failed to set delay to {val_str} us. Aborting ramp.")
                        break

                    if pause_every and pause_time and abs(current - last_pause_val) >= pause_every - 1e-9:
                        client.logger.info(f"Delay change reached {abs(current - last_pause_val):.1f} us (>= {pause_every:.1f} us). Pausing ramp for {pause_time:.1f} s...")
                        last_pause_val = current
                        slept = 0.0
                        last_log_time = 0.0
                        while slept < pause_time:
                            if self.ramp_stop_event.is_set():
                                break
                            if slept - last_log_time >= 10.0:
                                client.logger.info(f"Pause ongoing: {pause_time - slept:.0f} s remaining...")
                                last_log_time = slept
                            time.sleep(0.1)
                            slept += 0.1
                    else:
                        slept = 0.0
                        while slept < interval:
                            if self.ramp_stop_event.is_set():
                                break
                            time.sleep(0.05)
                            slept += 0.05

                    if self.ramp_stop_event.is_set():
                        client.logger.info("Ramping cancelled by user.")
                        break

            if not self.ramp_stop_event.is_set() and current == target:
                client.logger.info(f"Gradual delay ramp completed successfully at {target:.1f} us.")
        except Exception as e:
            client.logger.error(f"Error in ramping thread: {str(e)}")
        finally:
            self.window.write_event_value('-RAMP_FINISHED-', None)

    def run(self):
        client = gdg_tn.TelnetClient(debug=False)
        # client.connect()
        host = None
        # Initialize dynamic control states based on connection status (initially disconnected)
        self.update_control_states()

        while True:
            event, values = self.window.read(timeout=100)
            if event in ('Exit', None):
                self.ramp_stop_event.set()
                self.autorun_stop_event.set()
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

                # Start connection in a background thread to prevent UI freezing
                self.connection_in_progress = True
                self.window['connected'].update('Connecting...')
                self.update_control_states()
                self.connect_thread = threading.Thread(
                    target=self.execute_connect,
                    args=(client, host),
                    daemon=True
                )
                self.connect_thread.start()

            if event == '-CONNECT_FINISHED-':
                self.connection_in_progress = False
                res_host, success = values['-CONNECT_FINISHED-']
                if success:
                    client.logger.info("connect to " + res_host)
                    self.connected = True
                    self.set_connected(res_host)
                    # Fetch initial parameters
                    resp = client.read_all()
                    if resp != "":
                        self.window['output_val'].update(resp)
                        self.parse_and_update_status_monitor(resp)
                else:
                    sg.popup_error("Error when connecting to host %s" % res_host)
                    self.connected = False
                    self.set_connected(None)
                    host = None
                self.update_control_states()

            if event == 'disconnect':
                if not host:
                    sg.popup_error("already disconnected!")
                    continue
                client.logger.info("disconnect from host %s" % host)
                client.logout()
                host = None
                self.connected = False
                self.set_connected(host)
                # Reset parsed monitor widgets
                self.window['status_delay_a'].update('0.0')
                self.window['status_width_a'].update('0.0')
                self.window['status_delay_b'].update('0.0')
                self.window['status_width_b'].update('0.0')
                self.window['output_val'].update('00000000.0, 00000000.0, 00000000.0, 00000000.0')
                self.update_control_states()

            if event == 'read':
                if not self.connected:
                    sg.popup_error("please connect to a host first!")
                    continue
                if not host:
                    sg.popup_error("no host founded")
                    continue
                resp = client.read_all()
                if resp == "":
                    client.logger.error("Return empty string from host")
                else:
                    self.window['output_val'].update(resp)
                    self.parse_and_update_status_monitor(resp)

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
                if not selected_tp == key_type[0]:
                    if client.set_delay(selected_ch, selected_tp, inp_val):
                        sg.popup_ok("Set delay success!")
                if not selected_md == key_mode[0]:
                    if client.set_trigger_mode(selected_ch, selected_md):
                        sg.popup_ok("Set trigger mode success!")
                if not selected_ctrl == key_ctrl[0]:
                    if client.set_control(selected_ch, selected_ctrl):
                        sg.popup_ok("Set output control success!")
                # Refresh status monitor display after write
                resp = client.read_all()
                if resp != "":
                    self.window['output_val'].update(resp)
                    self.parse_and_update_status_monitor(resp)

            if event == 'autorun':
                if not self.connected:
                    sg.popup_error("please connect to a host first!")
                    continue
                if not host:
                    sg.popup_error("no host founded")
                    continue

                # Retrieve and validate sweep bounds
                try:
                    start_val_str = values['inp_autorun_start']
                    if not start_val_str:
                        raise ValueError("Start delay cannot be empty")
                    sweep_start = float(start_val_str)
                    if not (0.1 <= sweep_start <= 15999999.9):
                        raise ValueError("Start delay must be between 0.1 and 15999999.9 us")
                except ValueError as e:
                    sg.popup_error(f"Invalid Sweep Start: {str(e)}")
                    continue

                try:
                    end_val_str = values['inp_autorun_end']
                    if not end_val_str:
                        raise ValueError("End delay cannot be empty")
                    sweep_end = float(end_val_str)
                    if not (0.1 <= sweep_end <= 15999999.9):
                        raise ValueError("End delay must be between 0.1 and 15999999.9 us")
                except ValueError as e:
                    sg.popup_error(f"Invalid Sweep End: {str(e)}")
                    continue

                try:
                    step_val_str = values['inp_step']
                    if not step_val_str:
                        raise ValueError("Step cannot be empty")
                    sweep_step = float(step_val_str)
                    if sweep_step <= 0:
                        raise ValueError("Step must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Sweep Step: {str(e)}")
                    continue

                try:
                    interval_val_str = values['inp_interval']
                    if not interval_val_str:
                        raise ValueError("Interval cannot be empty")
                    sweep_interval = float(interval_val_str)
                    if sweep_interval <= 0:
                        raise ValueError("Interval must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Sweep Interval: {str(e)}")
                    continue

                sweep_pause_every = None
                try:
                    pause_every_str = values['inp_pause_every'].strip()
                    if pause_every_str:
                        sweep_pause_every = float(pause_every_str)
                        if sweep_pause_every <= 0:
                            raise ValueError("Pause threshold must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Pause Every: {str(e)}")
                    continue

                sweep_pause_time = None
                try:
                    pause_time_str = values['inp_pause_time'].strip()
                    if pause_time_str:
                        sweep_pause_time = float(pause_time_str)
                        if sweep_pause_time <= 0:
                            raise ValueError("Pause time must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Pause Time: {str(e)}")
                    continue

                if (sweep_pause_every is not None and sweep_pause_time is None) or (sweep_pause_every is None and sweep_pause_time is not None):
                    sg.popup_error("Both Sweep 'Pause Every' and 'Pause Time' must be set (or both left empty)")
                    continue

                selected_ch = [k for k in key_ch if values[k]][0]

                self.autorun_running = True
                self.update_control_states()
                self.autorun_stop_event.clear()
                self.autorun_thread = threading.Thread(
                    target=self.execute_autorun,
                    args=(client, selected_ch, sweep_start, sweep_end, sweep_step, sweep_interval, sweep_pause_every, sweep_pause_time),
                    daemon=True
                )
                self.autorun_thread.start()

            if event == 'stop_autorun':
                self.autorun_stop_event.set()
                client.logger.info("Requesting to stop auto sweep...")

            if event == '-AUTORUN_FINISHED-':
                self.autorun_running = False
                self.update_control_states()
                resp = client.read_all()
                if resp != "":
                    self.window['output_val'].update(resp)
                    self.parse_and_update_status_monitor(resp)

            if event == 'start_ramp':
                if not self.connected:
                    sg.popup_error("please connect to a host first!")
                    continue
                if not host:
                    sg.popup_error("no host founded")
                    continue

                # Retrieve and validate inputs
                try:
                    target_val_str = values['inp_target_delay']
                    if not target_val_str:
                        raise ValueError("Target delay cannot be empty")
                    target_delay = float(target_val_str)
                    if not (0.1 <= target_delay <= 15999999.9):
                        raise ValueError("Target delay must be between 0.1 and 15999999.9 us")
                except ValueError as e:
                    sg.popup_error(f"Invalid Target Delay: {str(e)}")
                    continue

                try:
                    step_val_str = values['inp_ramp_step']
                    if not step_val_str:
                        raise ValueError("Step cannot be empty")
                    ramp_step = float(step_val_str)
                    if ramp_step <= 0:
                        raise ValueError("Step must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Step: {str(e)}")
                    continue

                try:
                    interval_val_str = values['inp_ramp_interval']
                    if not interval_val_str:
                        raise ValueError("Interval cannot be empty")
                    ramp_interval = float(interval_val_str)
                    if ramp_interval <= 0:
                        raise ValueError("Interval must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Interval: {str(e)}")
                    continue

                ramp_pause_every = None
                try:
                    pause_every_str = values['inp_ramp_pause_every'].strip()
                    if pause_every_str:
                        ramp_pause_every = float(pause_every_str)
                        if ramp_pause_every <= 0:
                            raise ValueError("Pause threshold must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Pause Every: {str(e)}")
                    continue

                ramp_pause_time = None
                try:
                    pause_time_str = values['inp_ramp_pause_time'].strip()
                    if pause_time_str:
                        ramp_pause_time = float(pause_time_str)
                        if ramp_pause_time <= 0:
                            raise ValueError("Pause time must be positive")
                except ValueError as e:
                    sg.popup_error(f"Invalid Pause Time: {str(e)}")
                    continue

                if (ramp_pause_every is not None and ramp_pause_time is None) or (ramp_pause_every is None and ramp_pause_time is not None):
                    sg.popup_error("Both Ramp 'Pause Every' and 'Pause Time' must be set (or both left empty)")
                    continue

                selected_ch = [k for k in key_ch if values[k]][0]

                # Fetch current delay value of selected channel
                start_delay = self.get_current_delay(client, selected_ch)
                if start_delay is None:
                    sg.popup_error("Failed to query the current delay from the device. Please verify connection and retry.")
                    continue

                if start_delay == target_delay:
                    client.logger.info("Current delay is already at the target delay. No ramping needed.")
                    continue

                self.ramp_running = True
                self.update_control_states()

                # Start ramping thread
                self.ramp_stop_event.clear()
                self.ramp_thread = threading.Thread(
                    target=self.execute_ramp,
                    args=(client, selected_ch, start_delay, target_delay, ramp_step, ramp_interval, ramp_pause_every, ramp_pause_time),
                    daemon=True
                )
                self.ramp_thread.start()

            if event == 'stop_ramp':
                self.ramp_stop_event.set()
                client.logger.info("Requesting to stop ramping...")

            if event == '-RAMP_FINISHED-':
                self.ramp_running = False
                self.update_control_states()
                resp = client.read_all()
                if resp != "":
                    self.window['output_val'].update(resp)
                    self.parse_and_update_status_monitor(resp)
            if event == 'version':
                self.info_popup()
            if event == 'save_log':
                log_content = self.window['out_log'].get()
                default_filename = f"gdg_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                filepath = sg.popup_get_file(
                    'Save Log File',
                    save_as=True,
                    default_path=default_filename,
                    file_types=(('Log Files', '*.log'), ('All Files', '*.*')),
                    no_window=True
                )
                if filepath:
                    try:
                        with open(filepath, 'w', encoding='utf-8') as f:
                            f.write(log_content)
                        sg.popup_ok(f"Log saved successfully to:\n{filepath}")
                    except Exception as e:
                        sg.popup_error(f"Failed to save log file:\n{str(e)}")
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
