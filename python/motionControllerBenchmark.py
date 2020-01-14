#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is for benchmarking controller performance. Originally used for evaluating performance between 1-controller vs. 2-controller system

import sys
import time

import psutil
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
class SyncVisionTestClient(object):
    _context = None     # ZMQ context
    _endpoint = None    # Endpoint address

    def __init__(self, serverIp, serverPort) -> None:
        self._context = zmq.Context()
        self._endpoint = 'tcp://' + serverIp + ':' + str(serverPort)

    def _SendReceive(self, data, timeout) -> bool:
        isSendSuccessful = False
        # Send JSON request data to vision server
        socket = self._context.socket(zmq.REQ)
        socket.connect(self._endpoint)
        socket.send_json(data, zmq.NOBLOCK)
        # Receive JSON response data from vision server
        receiveStatus = (socket.poll(timeout, zmq.POLLIN) == zmq.POLLIN)
        if receiveStatus:
            message = socket.recv_json(zmq.NOBLOCK)
            isSendSuccessful = (message['id'] == data['id'])
        socket.close()
        return isSendSuccessful

    def StartVisionBenchmark(self, timeout=1000) -> bool:
        return self._SendReceive(data={'command':'Start', 'id':str(os.getpid())}, timeout=timeout)

    def StopVisionBenchmark(self, timeout=1000) -> bool:
        return self._SendReceive(data={'command':'Stop', 'id':str(os.getpid())}, timeout=timeout)

    def __del__(self):
        self._context.destroy()


def WriteDataSaveGraphs(**kwargs) -> None:
    # Configuration
    num_total_cpu = kwargs['num_total_cpu']
    num_physical_cpu = kwargs['num_physical_cpu']

    # Summary
    total_time = kwargs['total_time']
    num_cycles = kwargs['num_cycles']

    # Log data
    detection_times = np.array(kwargs['detection_time'])
    planning_times = np.array(kwargs['planning_times'])
    trajectory_times = np.array(kwargs['trajectory_times'])
    
    # Collected data
    total_cpu_percent = np.array(kwargs['total_cpu_percent'])
    per_cpu_percent = np.array(kwargs['per_cpu_percent'])
    total_cpu_freq = np.array(kwargs['total_cpu_freq'])
    per_cpu_freq = np.array(kwargs['per_cpu_freq'])
    cpu_temp = np.array(kwargs['cpu_temp'])
    total_context_switches = kwargs['total_context_switches']

    # Process CPU affinities
    detector_cpu_affinity = kwargs['detector_cpu_affinity']
    planning_cpu_affinity = kwargs['planning_cpu_affinity']
    rbridges_cpu_affinity = kwargs['rbridges_cpu_affinity']

    #####################
    # WRITE TO FILE
    #####################

    # Write configuration
    file = open('Motion_Controller_Results.txt', 'w')

    configurations = {'num_total_cpu': num_total_cpu, 'num_physical_cpu': num_physical_cpu}
    utilities.WriteConfigurations(file, **configurations)

    # Write summary
    summary = {'total_time': total_time, 'num_cycles': num_cycles, 'average': total_time / num_cycles, 'units': 'seconds'}
    utilities.WriteSummary(file, **summary)
    
    # Write log data
    utilities.ComputeStatisticsAndWriteToFile(file, 'Detection', detection_times)
    utilities.ComputeStatisticsAndWriteToFile(file, 'Planning', planning_times)
    utilities.ComputeStatisticsAndWriteToFile(file, 'Trajectory execution', trajectory_times)

    # Write collected data
    utilities.ComputeStatisticsAndWriteToFile(file, 'Total CPU usage', total_cpu_percent)
    utilities.ComputeStatisticsAndWriteToFile(file, 'Individual usage CPU', per_cpu_percent)
    utilities.ComputeStatisticsAndWriteToFile(file, 'Total CPU frequency', total_cpu_freq)
    utilities.ComputeStatisticsAndWriteToFile(file, 'Individual frequency CPU', per_cpu_freq)
    utilities.ComputeStatisticsAndWriteToFile(file, 'Individual temperature CPU', cpu_temp)
    utilities.WriteGeneralData(file, 'Total number of CPU context switching', total_context_switches)

    # Write process CPU affinities
    utilities.WriteProcessCpuAffinities('Detection', detector_cpu_affinity)
    utilities.WriteProcessCpuAffinities('Planning', planning_cpu_affinity)
    utilities.WriteProcessCpuAffinities('Robot bridges', rbridges_cpu_affinity)

    file.close()

    ##########################
    # SAVE ARRAYS FOR PLOTTING
    ##########################

    # Plot CPU usage and frequency as function of time and save figures
    np.save('Total_CPU_Usage_Data', total_cpu_percent)
    np.save('Per_CPU_Usage_Data', per_cpu_percent)
    np.save('Total_CPU_Freq_Data', total_cpu_freq)
    np.save('Per_CPU_Usage_Data', per_cpu_freq)
    np.save('Per_CPU_Temperature_Data', total_context_switches)


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
    planning_cpu_affinity = [p.cpu_affinity() for p in psutil.process_iter() if 'mujin_plannings' in p.as_dict(attrs=['pid', 'name'])['name']]
    rbridges_cpu_affinity = [p.cpu_affinity() for p in psutil.process_iter() if 'mujin_robotbridges_start' in p.as_dict(attrs=['pid', 'name'])['name']]

    ######################
    # INFRASTRUCTURE SETUP
    ######################

    parser = argparse.ArgumentParser(description='client for collecting vision controller data')
    parser.add_argument('-v', '--vision_server', action='store', type=str, dest='serverIp', required=True, help='IP address for vision controller server process')
    parser.add_argument('-p', '--port', action='store', type=int, dest='serverPort', default=7777, help='Port for vision controller server process')
    parser.add_argument('-c', '--cycles', action='store', type=int, dest='productionCycles', default=10, help='Number of production cycles to run')
    parser.add_argument('-s', '--seconds', action='store', type=int, dest='samplingRate', default=5, help='Sample frequency: Number of seconds per sample')
    options = parser.parse_args()

    ConfigureLogging()

    # Have one plc memory per MUJIN controller
    memory = plcmemory.PLCMemory()
    logger = plcmemory.PLCMemoryLogger(memory)
    controller = plccontroller.PLCController(memory, maxHeartbeatInterval=0.1)
    plc = plclogic.PLCLogic(controller)

    # Start a network server instance for MUJIN controllers to connect to
    log.warn('Server starting...')
    server = plczmqserver.PLCZMQServer(memory, 'tcp://*:5555')
    server.Start()
    log.warn('Server started!')

    # Wait until connected to controller
    log.warn('Connecting to controller...')
    plc.WaitUntilConnected(timeout=1.0)
    log.warn('Connected to controller!')

    # Clean errors
    if plc.IsError() is True:
        plc.ResetError()
        log.warn('Reset error(s)')
    
    # Clear signals
    plc.ClearAllSignals()
    log.warn('Cleared all signal(s)')

    # Wait for robot ready to move robot to home
    # Debug later: Timeout...caused by not setting correct values?
    try:
        plc.WaitUntilMoveToHomeReady()
        log.warn('Robot ready to move to home')
    except:
        log.warn('Robot ready to move to home timeout')

    # Move robot to home
    # Debug later: Issue caused by robot bridges not setting PLC variable(s) to correct values
    try:
        plc.StartMoveToHome()
        log.warn('Robot moving to home')
    except:
        log.warn('Robot moving to home timeout')

    # Wait for robot ready for order cycle
    # Debug later: Timeout...caused by not setting correct values?
    try:
        plc.WaitUntilOrderCycleReady()
        log.warn('Robot ready for order cycle')
    except:
        log.warn('Robot ready for order cycle timeout')

    # Define order parameters
    # Debug later: PLC logic class fails to set order variables in memory correctly
    controller.Set('orderRobotName', 'GP7')
    controller.Set('orderPartType', 'polydent')
    controller.Set('orderPickLocation', 2)
    controller.Set('orderPlaceLocation', 3)
    controller.Set('orderNumber', options.productionCycles)
    controller.Set('startOrderCycle', True)
    log.warn('Prepared order parameters')

    # Sync with vision controller, so that controller begins running test
    visionClient = SyncVisionTestClient(options.serverIp, options.serverPort)
    serverState = visionClient.StartVisionBenchmark()

    #########################
    # DATA COLLECTION
    #########################

    if serverState is True:
        # Waits for controller to set 'isRunningOrderCycle' to True
        # Debug later: plc.WaitForOrderCycleStatusChange()
        while controller.SyncAndGet('isRunningOrderCycle') is not True:
            continue
        log.warn('Started running order cycles!')

        # Set PLC signal done
        controller.Set('startOrderCycle', False)
        log.warn('Set startOrderCycle to OFF')

        # Start measuring context switches
        contextSwitchesStart = psutil.cpu_stats().ctx_switches

        # Waits for controller to set 'isRunningOrderCycle' to False (production cycles finished running)
        lastSample = time.time()
        sampleInterval = options.samplingRate
        while controller.SyncAndGet('isRunningOrderCycle') is not False:
            if time.time() - lastSample < sampleInterval: 
                total_cpu_percent.append(psutil.cpu_percent())
                per_cpu_percent.append(psutil.cpu_percent(percpu=True))
                total_cpu_freq.append(psutil.cpu_freq())
                per_cpu_freq.append(psutil.cpu_freq(percpu=False))
                cpu_temp.append(psutil.sensors_temperatures()['coretemp'][1:(num_total_cpu+1)])
                lastSample = time.time()
            continue
        log.warn('Finished running order cycles!')

        # Stop measuring context switches
        total_context_switches = contextSwitchesStart - psutil.cpu_stats().ctx_switches

        ###################################
        # COLLECT DATA FROM ORDER CYCLE LOG
        ###################################

        # Collect data from /var/log/mujin/ordercycles/ordercycles.log
        logFile = '/var/log/mujin/ordercycles/ordercycles.log'
        numCycles = kwargs['num_cycles']
        orderCycleLogEntriesList = ParseRotatedLog(logFile, logparserfn=lambda cursor, line: (cursor, ujson.loads(line)), limit=1)[0][1]

        total_time = float(orderCycles['cycleElapsedProcessingTime'])
        detection_times = [cycle['objectDetectionTime'] for cycle in orderCycleLogEntriesList['visionStatistics']['detectionHistory']]
        planning_times = [cycle['totalPlanningComputationTime'] for cycle in orderCycleLogEntriesList['cycleStatistics']['executed']]
        trajectory_times = [cycle['trajtotalduration'] for cycle in orderCycleLogEntriesList['cycleStatistics']['executed']]

        #####################################
        # WRITE DATA TO FILES AND SAVE GRAPHS
        #####################################

        # Data
        kwargs =
        {
            'num_total_cpu': num_total_cpu,
            'num_physical_cpu': num_physical_cpu,
            'total_time': total_time,
            'num_cycles': options.productionCycles,
            'detection_times': detection_times,
            'planning_times': planning_times,
            'trajectory_times': trajectory_times,            
            'total_cpu_percent': total_cpu_percent,
            'per_cpu_percent': per_cpu_percent,
            'total_cpu_freq': total_cpu_freq,
            'per_cpu_freq': per_cpu_freq,
            'cpu_temp': cpu_temp,
            'total_context_switches': total_context_switches,
            'detector_cpu_affinity': detector_cpu_affinity,
            'planning_cpu_affinity': planning_cpu_affinity,
            'rbridges_cpu_affinity': rbridges_cpu_affinity
        }

        # Write to output file
        WriteDataSaveGraphs(**kwargs)

    else:
        log.warn('Unable to sync with vision controller for testing!')

    # Stop everything
    log.warn('Server stopping.')
    server.Stop()
    log.warn('Server stopped.')


if __name__ == '__main__':
    main()
