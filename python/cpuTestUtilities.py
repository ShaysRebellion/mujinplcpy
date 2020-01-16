#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This file contains utility functions for controller CPU testing

import os
import threading
import subprocess

import zmq
import ujson
import numpy as np

import logging
import logging.handlers

log = logging.getLogger(__name__)

# This class is for synchronizing benchmarking between motion and vision controllers
class SyncTestWithControllerClient(object):
    _context = None     # ZMQ context
    _endpoint = None    # Endpoint address

    def __init__(self, serverIp, serverPort):
        self._context = zmq.Context()
        self._endpoint = 'tcp://' + serverIp + ':' + str(serverPort)
        # print('Server')
        # print(self._endpoint)

    def _SendReceive(self, data, timeout):
        isSendSuccessful = False
        # Send JSON request data to vision server
        socket = self._context.socket(zmq.REQ)
        socket.connect(self._endpoint)
        socket.send_json(data, zmq.NOBLOCK)
        # Receive JSON response data from vision server
        receiveStatus = (socket.poll(timeout, zmq.POLLIN) == zmq.POLLIN)
        if receiveStatus:
            message = socket.recv_json(zmq.NOBLOCK)
            isSendSuccessful = (message['command'] == data['command'] and message['id'] == data['id'])
        socket.close()
        return isSendSuccessful

    def StartControllerDataCollection(self, timeout=1000):
        return self._SendReceive(data={'command':'Start', 'id':str(os.getpid())}, timeout=timeout)

    def StopControllerDataCollection(self, timeout=1000):
        return self._SendReceive(data={'command':'Stop', 'id':str(os.getpid())}, timeout=timeout)

    def __del__(self):
        self._context.destroy()


# This class is for synchronizing benchmarking between motion and vision controllers
class SyncTestWithControllerServer(object):
    _context = None                     # ZMQ context
    _endpoint = None                    # Endpoint address
    _thread = None                      # Threading for SyncVisionTestServer
    _lock = None                        # For writing
    _isOk = None
    _shouldRunControllerDataCollection = None    # State indicating
    _syncControllerClient = None        # In case need to sync with another controller, e.g. motion controller needs to sync with vision controller

    def __init__(self, serverPort, syncControllerClient=None):
        self._context = zmq.Context()
        self._endpoint = 'tcp://*:' + str(serverPort)
        self._lock = threading.Lock()
        self._isOk = True
        self._shouldRunControllerDataCollection = False
        self._syncControllerClient = syncControllerClient

    def _RunThread(self):
        socket = self._context.socket(zmq.REP)
        socket.bind(self._endpoint)
        
        while self._isOk:
            receiveStatus = (socket.poll(1000, zmq.POLLIN) == zmq.POLLIN)
            if receiveStatus:
                message = socket.recv_json()
                # print('Received message')
                # print(message)
                if message['command'] == 'Start':
                    # Lock to prevent race conditions between write thread and read thread
                    self._lock.acquire()
                    # print('Lock for write acquired!')
                    shouldStartDataCollection = True

                    # Example case: Need to make sure that vision controller is synced before collecting data on motion controller
                    if self._syncControllerClient is not None:
                        serverState = self._syncControllerClient.StartControllerDataCollection()
                        # print('Request server state (from client)')
                        # print(serverState)
                        shouldStartDataCollection = serverState

                        if shouldStartDataCollection is False:
                            message['command'] = 'FAILURE' # Client is expecting the exact same message to be echoed back

                    self._shouldRunControllerDataCollection = shouldStartDataCollection
                    self._lock.release()
                    # print('Lock for write released!')

                elif message['command'] == 'Stop':
                    self._lock.acquire()
                    self._shouldRunControllerDataCollection = False
                    self._lock.release()

                    # Example case: Need to make sure that vision controller is stopped as well
                    if self._syncControllerClient is not None:
                        self._syncControllerClient.StopControllerDataCollection()

                # Send message back to client
                # print('Sending message')
                # print(message)
                socket.send_json(message, zmq.NOBLOCK)

            else:
                continue

        # print('Controller server successfully closed!')
        socket.close()

    def Start(self):
        self._thread = threading.Thread(target=self._RunThread)
        self._thread.start()

    def Stop(self):
        # Stop server thread
        self._isOk = False
        if self._thread is not None:
            # print('Waiting for thread to join...')
            self._thread.join()
            # print('Thread successfully joined!')
            self._thread = None

        # Additional cleanup
        self._context.destroy()

        # Stop data collection for controller server (e.g. stop vision controller server data collection from motion controller client)
        if self._syncControllerClient is not None:
            self._syncControllerClient = None

    def ShouldRun(self):
        self._lock.acquire()
        runState = self._shouldRunControllerDataCollection
        self._lock.release()
        return runState

    def __del__(self):
        self.Stop()


def ParseRotatedLog(logfile, rotate=None, maxrotate=9, cursor=None, includecursor=False, endcursor=None, includeendcursor=False, forward=False, greps=None, keyword=None, limit=None, logparserfn=None):
    """Parse log file that can be rotated by log rotate.
    This function assumes the each line in the log starts with a timestamp similar to "2017-01-18T07:18:47.499756+00:00,"

    :param logfile: full path to base log file, e.g. /var/log/mujin/mujin.system.debug.log
    :param rotate: used internally to recurse, do not pass in
    :param maxrotate: maximum rotated file to check, e.g. 9 means we check user.log, user.log.1, ..., user.log.9
    :param cursor: the cursor used to resume previous call
    :param includecursor: whether the entry matching the cursor should be included
    :param endcursor: the ending cursor
    :param includeendcursor: similar to includecursor
    :param forward: forward in time, meaning getting log later than the cursor, default to false, meaning get log earlier than the cursor
    :param keyword: keyword to filter log with
    :param greps: a list of lists, each sub list is the list of arguments to pass to grep
    :param limit: maximum number of lines to return, pass in None to return all
    :param logparserfn: custom function that takes the cursor and line as input and emits a log entry
    :return: list of log entry emitted by logparserfn, latest to oldest
    """

    if rotate is None:
        if forward:
            # forward in time, starting from oldest log
            rotate = maxrotate
        else:
            # backward in time, starting from latest log
            rotate = 0
    if rotate < 0 or rotate > maxrotate:
        return []

    # provide a default logparserfn
    if logparserfn is None:
        logparserfn = lambda cursor, line: (cursor, line)  # noqa: E731

    # determine file name
    filename = logfile
    if rotate > 0:
        filename = '%s.%d' % (logfile, rotate)
        # rotated log might be gzipped
        if not os.path.isfile(filename):
            filename = '%s.%d.gz' % (logfile, rotate)

    # if file does not exist
    if not os.path.isfile(filename):
        # when going back in time, if we found a rotated file no longer exit
        # assume we have reached the oldest log, so return no more log
        if not forward and rotate > 0:
            return []

        return ParseRotatedLog(
            logfile,
            rotate=rotate - 1 if forward else rotate + 1,
            maxrotate=maxrotate,
            cursor=cursor,
            includecursor=includecursor,
            endcursor=endcursor,
            includeendcursor=includeendcursor,
            forward=forward,
            greps=greps,
            keyword=keyword,
            limit=limit,
            logparserfn=logparserfn,
        )

    chain = []

    # tr removes null bytes that stop awk from processing lines
    with open(filename, 'r') as f:
        if filename.endswith('.gz'):
            chain.append(subprocess.Popen(['gzip', '-d'], stdin=f, stdout=subprocess.PIPE))
        else:
            chain.append(subprocess.Popen(['cat'], stdin=f, stdout=subprocess.PIPE))

    chain.append(subprocess.Popen(['tr', '-d', r'\000'], stdin=chain[-1].stdout, stdout=subprocess.PIPE))

    if cursor:
        args = ['awk', '-F,', '-v', 'cursor=' + cursor]
        if endcursor:
            args += ['-v', 'endcursor=' + endcursor]
        conditions = []
        if not forward:
            # return log earlier than cursor
            conditions.append('$1<=cursor' if includecursor else '$1<cursor')
        else:
            # return log later than cursor
            conditions.append('$1>=cursor' if includecursor else '$1>cursor')
        if endcursor:
            if not forward:
                # return log later than endcursor
                conditions.append('$1>=endcursor' if includeendcursor else '$1>endcursor')
            else:
                # return log earlier than endcursor
                conditions.append('$1<=endcursor' if includeendcursor else '$1<endcursor')
        args += [' && '.join(conditions)]
        chain.append(subprocess.Popen(args, stdin=chain[-1].stdout, stdout=subprocess.PIPE))

    for args in (greps or []):
        chain.append(subprocess.Popen(['grep'] + args, stdin=chain[-1].stdout, stdout=subprocess.PIPE))

    if keyword:
        chain.append(subprocess.Popen(['grep', '-Fi', keyword], stdin=chain[-1].stdout, stdout=subprocess.PIPE))

    if limit is not None:
        if not forward:
            chain.append(subprocess.Popen(['tail', '-n', str(limit)], stdin=chain[-1].stdout, stdout=subprocess.PIPE))
        else:
            chain.append(subprocess.Popen(['head', '-n', str(limit)], stdin=chain[-1].stdout, stdout=subprocess.PIPE))

    # close all stdout except the last process
    for p in chain[:-1]:
        p.stdout.close()

    lines = chain[-1].communicate()[0].split('\n')
    entries = []
    for line in reversed(lines):
        line = line.strip()
        if len(line) == 0:
            continue

        entry = None
        try:
            parts = line.split(',', 1)
            entry = logparserfn(parts[0].strip(), parts[1].strip())
        except Exception:
            log.exception("failed to parse log line: %s", line[:200])

        if entry is not None:
            entries.append(entry)
            if limit is not None:
                limit -= 1
                if limit <= 0:
                    break

    # if we have not reached the limit, we will continue on to the next rotated file
    if limit is None or limit > 0:
        rotatedlog = ParseRotatedLog(
            logfile,
            rotate=rotate - 1 if forward else rotate + 1,
            maxrotate=maxrotate,
            cursor=cursor,
            includecursor=includecursor,
            endcursor=endcursor,
            includeendcursor=includeendcursor,
            forward=forward,
            greps=greps,
            keyword=keyword,
            limit=limit,
            logparserfn=logparserfn,
        )
        if forward:
            entries = rotatedlog + entries
        else:
            entries = entries + rotatedlog
    return entries


def WriteConfigurations(file, **kwargs):
    numTotalCores = kwargs['num_total_cpu']
    numPhysicalCores = kwargs['num_physical_cpu']
    if numTotalCores == numPhysicalCores:
        file.write('HYPER-THREADING: OFF\n\n')
    else:
        file.write('HYPER-THREADING: ON\n\n')


def WriteSummary(file, units, **kwargs):
    file.write('SUMMARY\n')
    file.write('Total time: {} {}\n'.format(kwargs['total_time'], units))
    file.write('Number of cycles: {}\n'.format(kwargs['num_cycles']))
    file.write('Average time per cycle: {} {}\n\n'.format(kwargs['total_time'] / kwargs['num_cycles'], units))


def _ComputeStatistics(data):
    minimum = np.amin(data)
    maximum = np.amax(data)
    average = np.mean(data)
    std_dev = np.std(data)
    return minimum, maximum, average, std_dev


def _WriteStatisticsToFile(file, name, units, **kwargs):
    file.write(name + ' statistics\n')
    file.write('Minimum: {} {}\n'.format(kwargs['minimum'], units))
    file.write('Maximum: {} {}\n'.format(kwargs['maximum'], units))
    file.write('Average: {} {}\n'.format(kwargs['average'], units))
    file.write('Standard deviation: {} {}\n\n'.format(kwargs['std_dev'], units))


def ComputeStatisticsAndWriteToFile(file, name, units, data):
    if len(data.shape) == 1:
        minimum, maximum, average, std_dev = _ComputeStatistics(data)
        kwargs = {'minimum': minimum, 'maximum': maximum, 'average': average, 'std_dev': std_dev}
        _WriteStatisticsToFile(file, name, units, **kwargs)
    elif len(data.shape) == 2:
        for index in xrange(len(data[0])):
            extractedData = data[:, index]
            minimum, maximum, average, std_dev = _ComputeStatistics(extractedData)
            kwargs = {'minimum': minimum, 'maximum': maximum, 'average': average, 'std_dev': std_dev}
            indexName = name + '_{}'.format(index)
            _WriteStatisticsToFile(file, indexName, units, **kwargs)
    else:
        pass


def WriteGeneralData(file, name, data):
    file.write('{}: {}\n\n'.format(name, data))


def WriteProcessCpuAffinities(file, processName, affinity):
    file.write('CPU affinity for process: {} \n'.format(processName))
    for index in xrange(len(affinity[0])):
        file.write('Processor {},'.format(affinity[index]))
    file.write('\n\n')