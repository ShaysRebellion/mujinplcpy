#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This script is for collecting data on vision controller CPU performance. Originally used for evaluating performance between 1-controller vs. 2-controller system

import sys
import argparse
import time

import psutil
import numpy as np

import cpuTestUtilities
from cpuTestUtilities import SyncTestWithControllerClient, SyncTestWithControllerServer

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


def WriteDataSaveGraphData(**kwargs):
    # Configuration
    num_total_cpu = kwargs['num_total_cpu']
    num_physical_cpu = kwargs['num_physical_cpu']
    min_cpu_freq = kwargs['min_cpu_freq']
    max_cpu_freq = kwargs['max_cpu_freq']

    # Collected data
    total_cpu_percent = np.array(kwargs['total_cpu_percent'])
    per_cpu_percent = np.array(kwargs['per_cpu_percent'])
    total_cpu_freq = np.array(kwargs['total_cpu_freq'])
    per_cpu_freq = np.array(kwargs['per_cpu_freq'])
    per_cpu_temp = np.array(kwargs['per_cpu_temp'])
    total_context_switches = kwargs['total_context_switches']

    # Process CPU affinities
    detection_cpu_affinity = kwargs['detection_cpu_affinity']

    #####################
    # WRITE TO FILE
    #####################

    # Write configuration
    file = open('Vision_Controller_Results.txt', 'w')

    # Write configuration
    configurations = {'num_total_cpu': num_total_cpu, 'num_physical_cpu': num_physical_cpu, 'min_cpu_freq': min_cpu_freq, 'max_cpu_freq': max_cpu_freq}
    cpuTestUtilities.WriteConfigurations(file, **configurations)

    # Write collected data
    cpuTestUtilities.ComputeStatisticsAndWriteToFile(file, 'TOTAL CPU USAGE', '%' , total_cpu_percent)
    cpuTestUtilities.ComputeStatisticsAndWriteToFile(file, 'INDIVIDUAL USAGE CPU', '%', per_cpu_percent)
    cpuTestUtilities.ComputeStatisticsAndWriteToFile(file, 'TOTAL CPU FREQUENCY', 'Mhz', total_cpu_freq)
    cpuTestUtilities.ComputeStatisticsAndWriteToFile(file, 'INDIVIDUAL FREQUENCY CPU', 'MHz', per_cpu_freq)
    cpuTestUtilities.ComputeStatisticsAndWriteToFile(file, 'INDIVIDUAL TEMPERATURE CPU', 'deg (Celsius)', per_cpu_temp)
    cpuTestUtilities.WriteGeneralData(file, 'TOTAL CPU CONTEXT SWITCHING', total_context_switches)

    # Write process CPU affinities
    cpuTestUtilities.WriteGeneralData(file, 'DETECTION PROCESS CPU AFFINITY', detection_cpu_affinity)

    file.close()

    ##########################
    # SAVE ARRAYS FOR PLOTTING
    ##########################

    # Plot CPU usage and frequency as function of time and save figures
    np.save('Total_CPU_Usage_Data', total_cpu_percent)
    np.save('Per_CPU_Usage_Data', per_cpu_percent)
    np.save('Total_CPU_Freq_Data', total_cpu_freq)
    np.save('Per_CPU_Freq_Data', per_cpu_freq)
    np.save('Per_CPU_Temp_Data', per_cpu_temp)


def main():

    ####################
    # MEASUREMENTS
    ####################

    # Number of CPUs
    num_total_cpu = psutil.cpu_count()                      # Total CPU count (physical and virtual)
    num_physical_cpu = psutil.cpu_count(logical=False)      # Physical CPU count
    min_cpu_freq = psutil.cpu_freq().min                    # Minimum operating frequency
    max_cpu_freq = psutil.cpu_freq().max                    # Maximum operating frequency

    # Overall motion controller CPU percent usage
    
    # Ignore first value. See documentation on usage
    psutil.cpu_percent()            
    psutil.cpu_percent(percpu=True)

    total_cpu_percent = list()      # Total CPU usage                    
    per_cpu_percent = list()        # Per CPU usage

    # Real time CPU frequency
    total_cpu_freq = list()         # Real time CPU frequency
    per_cpu_freq = list()           # Real time per CPU frequency

    per_cpu_temp = list()               # CPU temperature

    total_context_switches = 0      # Total number of context switches

    # Resource heavy processes for monitoring
    detection_cpu_affinity = [p.cpu_affinity() for p in psutil.process_iter() if 'mujin_detectors_runvisionmanager' in p.as_dict(attrs=['pid', 'name'])['name']]

    ######################
    # INFRASTRUCTURE SETUP
    ######################

    parser = argparse.ArgumentParser(description='Script for collecting vision controller data')
    parser.add_argument('-p', '--port', action='store', type=int, dest='serverPort', default=24001, help='Port for vision controller server process')
    parser.add_argument('-s', '--seconds', action='store', type=int, dest='samplingRate', default=5, help='Sample frequency: Number of seconds per sample')
    options = parser.parse_args()

    ConfigureLogging()

    # Create server to listen for start event
    log.warn('Starting vision server...')
    visionControllerServer = SyncTestWithControllerServer(options.serverPort)
    visionControllerServer.Start()    # Spin off thread to listen for start and stop events from motion controller
    log.warn('Created vision server!')

    # Wait for start data collection event
    log.warn('Vision server listening for start collection event!')
    while visionControllerServer.ShouldRun() is not True:
        continue
    log.warn('Starting data collection on vision controller!')


    ####################
    # DATA COLLECTION
    ####################

    # Start measuring context switches
    contextSwitchesStart = psutil.cpu_stats().ctx_switches

    # Waits for client to set to False (production cycles finished running)
    lastSample = time.time()
    sampleInterval = options.samplingRate
    while visionControllerServer.ShouldRun() is not False:
        if time.time() - lastSample < sampleInterval: 
            total_cpu_percent.append(psutil.cpu_percent())
            per_cpu_percent.append(psutil.cpu_percent(percpu=True))
            total_cpu_freq.append(psutil.cpu_freq().current)
            per_cpu_freq.append([cpuFreq.current for cpuFreq in psutil.cpu_freq(percpu=True)])
            per_cpu_temp.append(psutil.sensors_temperatures()['coretemp'][1:(num_total_cpu+1)])
            lastSample = time.time()
        continue
    
    # Stop measuring context switches
    total_context_switches = psutil.cpu_stats().ctx_switches -contextSwitchesStart

    log.warn('Stopping data collection on vision controller and stopping vision controller server...')
    visionControllerServer.Stop()
    log.warn('Stopped vision controller server!')

    #####################################
    # WRITE DATA TO FILES AND SAVE GRAPHS
    #####################################

    log.warn('Writing vision controller data...')

    # Data
    kwargs = \
    { \
        'num_total_cpu': num_total_cpu, \
        'num_physical_cpu': num_physical_cpu, \
        'min_cpu_freq': min_cpu_freq, \
        'max_cpu_freq': max_cpu_freq, \
        'total_cpu_percent': total_cpu_percent, \
        'per_cpu_percent': per_cpu_percent, \
        'total_cpu_freq': total_cpu_freq, \
        'per_cpu_freq': per_cpu_freq, \
        'per_cpu_temp': per_cpu_temp, \
        'total_context_switches': total_context_switches, \
        'detection_cpu_affinity': detection_cpu_affinity \
    }

    # Write to output file
    WriteDataSaveGraphData(**kwargs)

    log.warn('Finished writing vision controller data!')


if __name__ == '__main__':
    main()
