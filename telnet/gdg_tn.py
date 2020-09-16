# -*- coding: utf-8 -*-
# @Time    : 2020-09-15
# @File    : gdg_tn.py
# @Software: PyCharm
# @Author  : Di Wang(KEK Linac)
# @Email   : sdcswd@post.kek.jp
import sys
import telnetlib
import logging
import time
import queue

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%m/%d/%Y %H:%M:%S %p"


class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)


class TelnetClient:
    """
    GDG has two channels: A and B, both are able to change the delay and pulse width
    gdg command:
    read current setting:
    `ral`

    channel pulse delay:
    `apd 9999999`         # channel A delay: 9 s 999 ms 999 us
    `bpd 2.1`               # channel B delay: 2.1 us


    channel pulse width:
    `apw 9999999`         # channel A width: 9 s 999 ms 999 us
    `bpw 2.1`               # channel B width: 2.1 us


    trigger mode: First Mode (omit the later input signal during the delay period), Last Mode (omit the first signal),
    `apf`
    `apl`

    disable or enable output
    `adi`
    `aen`
    `bdi`
    `ben`
    """

    def __init__(self, debug):

        self.logger = logging.getLogger('gdg_main')
        self.timeout = 1
        self.tn = telnetlib.Telnet()
        self.debug = debug
        if self.debug:
            self.tn.set_debuglevel(100)
            logging.basicConfig(level=logging.DEBUG, format=LOG_FORMAT, datefmt=DATE_FORMAT)
        else:
            logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=DATE_FORMAT)
        self.log_queue = queue.Queue()
        self.queue_handler = QueueHandler(self.log_queue)
        self.queue_handler.setFormatter(
            logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT))
        self.logger.addHandler(self.queue_handler)

    def connect(self, host, port=10001):
        try:
            self.tn.open(host, port, self.timeout)
        except OSError as e:
            self.logger.error(e)
            return False
        if self.tn is None:
            self.logger.error("connection fails")
            return False
        time.sleep(1)
        self.logger.info("connected to host: %s, port: %s" % (host, port))
        return True

    def execute_cmd(self, flag, cmd: str):
        if self.tn is None:
            self.logger.error("can not run cmd since connection fails")
            return False
        tn_cmd = cmd
        self.tn.write(tn_cmd.encode('ascii'))
        time.sleep(1)
        resp = self.tn.read_until(flag, 1).decode('ascii', errors='ignore').strip()
        self.logger.debug("run cmd:" + cmd.strip() + ", return:" + resp)
        return resp

    def logout(self):
        if self.tn is None:
            self.logger.debug("already disconnected")
            return True
        self.tn.close()
        self.logger.info("logout")
        return True

    def read_all(self):
        resp = self.execute_cmd(b'\n', "ral\n")
        self.logger.info("Read current setting %s" % resp)
        return resp

    def set_trigger_mode(self, ch: str, mode: str):
        if mode.lower() == "first" or mode.lower() == "f":
            if ch.lower() == "a":
                cmd = "apf"
            elif ch.lower() == "b":
                cmd = "bpf"
            else:
                self.logger.error("Error channel value: %s" % ch)
                return False
        elif mode.lower() == "last" or mode.lower() == "l":
            if ch.lower() == "a":
                cmd = "apl"
            elif ch.lower() == "b":
                cmd = "bpl"
            else:
                self.logger.error("Error channel value: %s" % ch)
                return False
        else:
            self.logger.error("Error trigger mode value: %s" % mode)
            return False
        resp = self.execute_cmd(b'\n', cmd + "\n")
        self.logger.info("Set channel (%s) mode as %s, return: %s" % (ch, mode, resp))
        return True

    def set_control(self, ch: str, ctrl: str):
        if ctrl.lower() == "enable" or ctrl.lower() == "en":
            if ch.lower() == "a":
                cmd = "aen"
            elif ch.lower() == "b":
                cmd = "ben"
            else:
                self.logger.error("Error channel value: %s" % ch)
                return False
        elif ctrl.lower() == "disable" or ctrl.lower() == "di":
            if ch.lower() == "a":
                cmd = "adi"
            elif ch.lower() == "b":
                cmd = "bdi"
            else:
                self.logger.error("Error channel value: %s" % ch)
                return False
        else:
            self.logger.error("Error control value: %s" % ctrl)
            return False
        resp = self.execute_cmd(b'\n', cmd + "\n")
        self.logger.info("Set channel (%s) mode as %s, return: %s" % (ch, ctrl, resp))
        return True

    def set_delay(self, ch: str, tp: str, val: str):
        """
        set delay, channel is either A or B, delay value is between 0.1 ~ 15999999.9 us, pulse width is 0.1 us ~ 10 s
        :param ch: channel
        :type ch: str
        :param tp: delay or width
        :type tp: str
        :param val: delay value
        :type val: str
        :return: response string from GDG
        :rtype: str
        """
        # should add some para check here...
        if tp.lower() == "delay" or tp.lower() == "d":
            if 0.1 <= float(val) <= 15999999.9:
                if ch.lower() == "a":
                    cmd = "apd " + val
                elif ch.lower() == "b":
                    cmd = "bpd " + val
                else:
                    self.logger.error("Error channel value: %s" % ch)
                    return False
            else:
                self.logger.error("Error delay value: %s" % val)
                return False
        elif tp.lower() == "width" or tp.lower() == "w":
            if 0.1 <= float(val) <= 9999999.9:
                if ch.lower() == "a":
                    cmd = "apw " + val
                elif ch.lower() == "b":
                    cmd = "bpw " + val
                else:
                    self.logger.error("Error channel value: %s" % ch)
                    return False
            else:
                self.logger.error("Error delay value: %s" % val)
                return False
        else:
            self.logger.error("Error type value: %s" % tp)
            return False
        # print(cmd)
        resp = self.execute_cmd(b'\n', cmd + "\n")
        self.logger.info("Set channel (%s) %s as value %s, return: %s" % (ch, tp, val, resp))
        return True


if __name__ == '__main__':
    h = "gdg3"
    p = 10001
    client = TelnetClient(debug=False)

    if client.connect(h, p):
        client.read_all()
        client.set_delay("a", "delay", "888888")
        client.read_all()
        client.set_trigger_mode("a", "f")
        client.set_control("a", "disable")
        client.read_all()
    time.sleep(1)
    client.logout()
