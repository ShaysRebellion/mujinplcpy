#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script is for benchmarking controller performance. Originally used for evaluating performance between 1-controller vs. 2-controller system

import sys
import time
import numpy as np

from mujinplc import plcmemory, plccontroller, plclogic, plczmqserver

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


def main():
    NUM_PRODUCTION_CYCLES = 5

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

    # Clean slate
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
    controller.Set('orderNumber', NUM_PRODUCTION_CYCLES)
    controller.Set('startOrderCycle', True)
    log.warn('Prepared order parameters')

    # Start timer
    startTime = time.time()

    # Waits for controller to set 'isRunningOrderCycle' to True
    # Debug later: plc.WaitForOrderCycleStatusChange()
    while controller.SyncAndGet('isRunningOrderCycle') is not True:
        continue
    log.warn('Started running order cycles!')

    # Set PLC signal done
    controller.Set('startOrderCycle', False)
    log.warn('Set startOrderCycle to OFF')

    # Waits for controller to set 'isRunningOrderCycle' to False
    while controller.SyncAndGet('isRunningOrderCycle') is not False:
        continue
    log.warn('Finished running order cycles!')

    # Stop timer
    endTime = time.time()

    # Write to output file
    totalTime = endTime - startTime
    f = open('results.txt', 'a')
    f.write('Ran production cycle %d times, which took %d seconds\n' % (NUM_PRODUCTION_CYCLES, totalTime))

    # Stop everything
    log.warn('Server stopping.')
    server.Stop()
    log.warn('Server stopped.')


if __name__ == '__main__':
    main()