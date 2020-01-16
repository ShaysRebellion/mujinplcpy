#!/usr/bin/env python
# -*- coding: utf-8 -*-

# This script is for plotting data from .npy binary files

import argparse

import numpy as np
import matplotlib
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description='Script for plotting controller CPU data')
    parser.add_argument('-s', '--seconds', action='store', type=int, dest='samplingRate', default=5, help='Sample frequency: Number of seconds per sample')
    parser.add_argument('-if', '--input_file_name', action='store', type=str, dest='inputFileName', required=True, help='Input (.npy) file name')
    parser.add_argument('-tl', '--title', action='store', type=str, dest='title', required=True, help='Title for graph figure')
    parser.add_argument('-xl', '--x_label', action='store', type=str, dest='xLabel', required=True, help='X-axis label for graph figure')
    parser.add_argument('-yl', '--y_label', action='store', type=str, dest='yLabel', required=True, help='Y-axis label for graph figure')
    parser.add_argument('-of', '--output_file_name', action='store', type=str, dest='outputFileName', required=True, help='Output file name (no file extension, automatically saves to .png format)')
    options = parser.parse_args()

    cpuData = np.load(options.inputFileName)
    print(cpuData)
    timeIndices = np.arange(len(cpuData))*options.samplingRate
    if len(cpuData.shape) == 1:
        plt.plot(timeIndices, cpuData)
        plt.title(options.title)
        plt.xlabel(options.xLabel)
        plt.ylabel(options.yLabel)
        plt.savefig(options.outputFileName)

    elif len(cpuData.shape) == 2:
        for index in xrange(len(cpuData[0])):
            plt.plot(timeIndices, cpuData[:,index])
            plt.title(options.title)
            plt.xlabel(options.xLabel)
            plt.ylabel(options.yLabel)
        plt.savefig(options.outputFileName)

    else:
        print('Unrecognized data dimensions {}'.format(cpuData.shape))



if __name__ == '__main__':
    main()