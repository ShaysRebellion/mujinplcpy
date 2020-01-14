#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is for benchmarking controller performance. Originally used for evaluating performance between 1-controller vs. 2-controller system

import sys
import time
import numpy as np

from mujinplc import plcmemory, plccontroller, plclogic, plczmqserver

import ujson
import mujincommon
from mujincommon.commonlogging import ParseRotatedLog
import utilities

import logging
log = logging.getLogger(__name__)


def ConfigureLogging(logLevel=logging.DEBUG, outputStream=sys.stderr):
    handler = logging.StreamHandler(outputStream)
    try:
        import logutils.colorize
        handler = logutils.colorize.ColorizingStreamHandler(outputStream)
        handler.level_map[logging.DEBUG] = (None, 'green', False)
        handler.level_map[logging.INFO] = (None, None, False)
        handler.level_map[logging.WARNING] = (None, 'yellow', False)
        handler.level_map[logging.ERROR] = (None, 'red', False)
        handler.level_map[logging.CRITICAL] = ('white', 'magenta', True)
    except ImportError:
        pass
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s [%(levelname)s] [%(filename)s:%(lineno)s %(funcName)s] %(message)s'))
    handler.setLevel(logLevel)

    root = logging.getLogger()
    root.setLevel(logLevel)
    root.handlers = []
    root.addHandler(handler)


# This class is for synchronizing benchmarking between motion and vision controllers
class SyncVisionTestServer(object):
    _context = None                     # ZMQ context
    _endpoint = None                    # Endpoint address
    _thread = None                      # Threading for SyncVisionTestServer
    _shouldRunVisionBenchmark = None    # State indicating

    def __init__(self, serverPort) -> None:
        self._context = zmq.Context()
        self._endpoint = 'tcp://*:' + str(serverPort)
        self._shouldRunVisionBenchmark = False

    def _RunThread(self) -> None:
        socket = self._context.socket(zmq.REP)
        socket.bind(self._endpoint)
        
        while self._shouldRunVisionBenchmark:
            message = socket.recv_json()
            print(message)
            if message['command'] == 'Stop':
                self._shouldRunVisionBenchmark = False
            socket.send_json(message, zmq.NOBLOCK)
            continue

        print('Vision server successfully closed!')
        socket.close()

    def Start(self) -> None:
        self._shouldRunVisionBenchmark = True
        self._thread = threading.Thread(target=self._RunThread, name='SyncVisionTestServer')
        self._thread.start()

    def ShouldRun(self) -> bool:
        return self._shouldRunVisionBenchmark

    def __del__(self):
        self._context.destroy()


def main():

    ####################
    # MEASUREMENTS
    ####################

    # Number of CPUs
    num_physical_cpu = psutil.cpu_count(logical=False)    # Physical CPU count
    num_total_cpu = psutil.cpu_count()                    # Total CPU count (physical and virtual)

    # Overall motion controller CPU percent usage
    psutil.cpu_percent()            # Ignore first value. See documentation on usage
    total_cpu_percent = list()      # Total CPU usage                    
    per_cpu_percent = list()        # Per CPU usage

    # Real time CPU frequency
    total_cpu_freq = list()         # Real time CPU frequency
    per_cpu_freq = list()           # Real time per CPU frequency

    cpu_temp = list()               # CPU temperature

    total_context_switches = 0      # Total number of context switches

    # Resource heavy processes for monitoring
    detector_cpu_affinity = [p.cpu_affinity() for p in psutil.process_iter() if 'mujin_detectors_runvisionmanager' in p.as_dict(attrs=['pid', 'name'])['name']]

    ######################
    # INFRASTRUCTURE SETUP
    ######################

    parser = argparse.ArgumentParser(description='client for collecting vision controller data')
    parser.add_argument('-p', '--port', action='store', type=int, dest='serverPort', default=7777, help='Port for vision controller server process')
    parser.add_argument('-s', '--seconds', action='store', type=int, dest='samplingRate', default=5, help='Sample frequency: Number of seconds per sample')
    options = parser.parse_args()

    ConfigureLogging()

    # Create server to listen for start event
    visionServer = SyncVisionTestServer(options.serverPort)
    visionServer.Start()    # Spin off thread to listen for start and stop events from motion controller

    # Wait 
    log.warn('Created server to listen for start and stop data collection event!')
    while visionServer.shouldRun is not True:
        continue
    log.warn('Starting data collection on vision controller')

    ####################
    # DATA COLLECTION
    ####################

    


if __name__ == '__main__':
    main()
