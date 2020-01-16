#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# This script queues orders for robot through PLC

import sys
import argparse

from mujinplc import plcmemory, plccontroller, plclogic, plczmqserver
from cpuTestUtilities import SyncTestWithControllerClient

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


def main():
    parser = argparse.ArgumentParser(description='Script for testing controller hardware')
    parser.add_argument('-m', '--motion_controller_ip', action='store', type=str, dest='motionServerIp', required=True, help='Motion controller IP address')
    parser.add_argument('-p', '--motion_controller_port', action='store', type=int, dest='motionServerPort', default=24000, help='Motion controller data collection server port. Default is 7777')
    parser.add_argument('-c', '--cycles', action='store', type=int, dest='productionCycles', default=10, help='Number of production cycles to run')
    options = parser.parse_args()

    ConfigureLogging()

    # Have one plc memory per MUJIN controller
    memory = plcmemory.PLCMemory()
    logger = plcmemory.PLCMemoryLogger(memory)
    controller = plccontroller.PLCController(memory, maxHeartbeatInterval=0.1)
    plc = plclogic.PLCLogic(controller)

    # Start a network server instance for MUJIN controllers to connect to
    log.warn('PLC server starting...')
    server = plczmqserver.PLCZMQServer(memory, 'tcp://*:5555')
    server.Start()
    log.warn('PLC server started!')

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

    # Sync with motion controller, so that motion controller begins running data collection
    log.warn('Connecting to motion controller...')
    motionControllerClient = SyncTestWithControllerClient(options.motionServerIp, options.motionServerPort)
    motionServerState = motionControllerClient.StartControllerDataCollection()

    if motionServerState is True:
        log.warn('Connected to motion controller!')

        # Define order parameters
        # Debug later: PLC logic class fails to set order variables in memory correctly
        controller.Set('orderRobotName', 'GP7')
        controller.Set('orderPartType', 'polydent')
        controller.Set('orderPickLocation', 2)
        controller.Set('orderPlaceLocation', 3)
        controller.Set('orderNumber', options.productionCycles)
        controller.Set('startOrderCycle', True)
        log.warn('Prepared order parameters')

        # Waits for controller to set 'isRunningOrderCycle' to True
        # Debug later: plc.WaitForOrderCycleStatusChange()
        while controller.SyncAndGet('isRunningOrderCycle') is not True:
            continue
        log.warn('Started running order cycles!')

        # Set PLC signal done
        controller.Set('startOrderCycle', False)
        log.warn('Set startOrderCycle to OFF')

        # Waits for controller to set 'isRunningOrderCycle' to False (production cycles finished running)
        while controller.SyncAndGet('isRunningOrderCycle') is not False:
            continue
        # Send stop signal to motion (and eventually vision) controllers
        motionControllerClient.StopControllerDataCollection()

        log.warn('Finished running order cycles!')

    else:
        log.warn('Failed to connect to motion controller or motion controller failed to connect to vision controller!')

    # Stop everything
    log.warn('PLC server stopping.')
    server.Stop()
    log.warn('PLC server stopped.')


if __name__ == '__main__':
    main()
