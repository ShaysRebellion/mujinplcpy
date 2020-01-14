import numpy as np


def WriteConfigurations(file, **kwargs) -> None:
    numTotalCores = kwargs['num_total_cpu']
    numPhysicalCores = kwargs['num_physical_cpu']
    if numTotalCores == numPhysicalCores:
        file.write('Without hyper-threading configuration\n\n')
    else:
        file.write('With hyper-threading configuration\n\n')


def WriteSummary(file, **kwargs) -> None
    file.write('Total time: {} {}\n'.format(kwargs['total_time'], kwargs['units']))
    file.write('Number of cycles: {}\n'.format(kwargs['total_time']))
    file.write('Average time per cycle: {} {}\n\n'.format(kwargs['num_cycles'], kwargs['units']))


def _ComputeStatistics(data) -> tuple:
    minimum = np.amin(data)
    maximum = np.amax(data)
    average = np.mean(data)
    std_dev = np.std(data)
    return minimum, maximum, average, std_dev


def _WriteStatisticsToFile(file, name, **kwargs) -> None:
    file.write(name + ' statistics\n')
    file.write('Minimum: {} {}\n'.format(kwargs['minimum'], kwargs['units']))
    file.write('Maximum: {} {}\n'.format(kwargs['maximum'], kwargs['units']))
    file.write('Average: {} {}\n'.format(kwargs['average'], kwargs['units']))
    file.write('Standard deviation: {}\n\n'.format(kwargs['std_dev']))


def ComputeStatisticsAndWriteToFile(file, name, data) -> None:
    if len(data.shape) == 1:
        minimum, maximum, average, std_dev = _ComputeStatistics(data)
        kwargs = {'minimum': minimum, 'maximum': maximum, 'average': average, 'std_dev': std_dev}
        _WriteStatisticsToFile(file, name, **kwargs)
    elif len(data.shape) == 2:
        for index in range(len(data)):
            extractedData = [:, index]
            minimum, maximum, average, std_dev = _ComputeStatistics(extractedData)
            kwargs = {'minimum': minimum, 'maximum': maximum, 'average': average, 'std_dev': std_dev}
            indexName = name + '_{}'.format(index)
            _WriteStatisticsToFile(file, indexName, **kwargs)
    else:
        pass


def WriteGeneralData(file, name, data) -> None
    file.write('{}: {}', name, data)


def WriteProcessCpuAffinities(file, processName, affinity) -> None:
    file.write('CPU affinity for process: {} \n'.format(processName))
    for index in xrange(len(affinity)):
        file.write('Processor {},'.format(affinity[index]))
    file.write('\n\n')