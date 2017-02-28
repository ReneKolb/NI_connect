import Queue
import numpy as np
from PyDAQmx import Task
from PyDAQmx.DAQmxConstants import *
from PyDAQmx.DAQmxTypes import *
from threading import Thread


class NI_DIODevice():
    """
    This class is the interface to the NI driver for a NI PCI-DIO-32HS digital output card
    """    
    def __init__(self, MAX_name, message_queue):
        """
        Initialise the driver and tasks using the given MAX name and message queue to communicate with this class

        Parameters
        ----------
        MAX_name : str
            the National Instrument MAX name used to identify the hardware card
        message_queue : JoinableQueue
            a message queue used to send instructions to this class
        """        
        print("initialize device")
        self.NUM_DO = 32
        self.MAX_name = MAX_name

        #Create DO Task
        self.do_task = Task()
        self.do_read = int32()
        self.do_data = np.zeros((self.NUM_DO,), dtype=np.uint8)

        self.setup_static_channels()

        #DAQmx Start Code
        self.do_task.StartTask()

        self.wait_for_rerun = False

        self.running = True
        self.read_Thread = Thread(target=self.read_fun, args=(message_queue,))


    def start(self):
        """
        Starts the message queue thread to read incoming instructions
        """        
        self.read_Thread.start()

    def read_fun(self, message_queue):
        """
        Main method to read incoming instructions from the message queue
        """
        while self.running:
            try:
                typ, msg = message_queue.get(timeout=0.5)
            except Queue.Empty:
                continue

            if typ == 'manual':
                self.program_manual(msg)
                message_queue.task_done()
            elif typ == 'trans to buff':
                #Transition to Buffered
                if msg['fresh']:
                    self.transition_to_buffered(True, msg['clock_terminal'], msg['do_channels'], msg['do_data'])
                else:
                    self.transition_to_buffered(False, None, None, None)
                message_queue.task_done() #signalize that the task is done
            elif typ == 'trans to man':
                #Transition to Manual
                self.transition_to_manual(msg['more_reps'], msg['abort'])
                message_queue.task_done()
            else:
                print("unkown message: "+msg)
                message_queue.task_done()
                continue   
                

    def setup_static_channels(self):
        #setup DO port(s)
        self.do_task.CreateDOChan(self.MAX_name + "/port0/line0:7," + self.MAX_name + "/port1/line0:7," +self.MAX_name + "/port2/line0:7," +self.MAX_name + "/port3/line0:7", "", DAQmx_Val_ChanForAllLines) 

    def shutdown(self):
        """
        Shutdown the device (stop & clear all tasks). Also stop the message queue thread
        """
        print("shutdown device")
        self.running = False
        self.do_task.StopTask()
        self.do_task.ClearTask()

    def program_manual(self, front_panel_values):
        """
        Update the static output chanels with new values.

        This method transitions the device into manual mode (if it is still in rerun mode) and
        updates the output state of all channels

        Parameters
        ----------
        front_panel_values : dict {connection name : new state, ...}
            Containing the connection name and corresponding new output state
        """        
        if self.wait_for_rerun:
            print("dont wait for rerun any more. setup static")
            self.do_task.StopTask()
            self.do_task.ClearTask()
            self.do_task = Task()
            self.setup_static_channels()
            self.wait_for_rerun = False

        for port in range(4):
            for line in range(8):
                self.do_data[port*8+line] = front_panel_values['port%d/line%d'%(port, line)]

        self.do_task.WriteDigitalLines(1, True, 1, DAQmx_Val_GroupByChannel, self.do_data, byref(self.do_read), None)

    def transition_to_buffered(self, fresh, clock_terminal, do_channels, do_data):
        """
        Transition the device to buffered mode

        This method does the hardware programming if needed

        Parameters
        ----------
        fresh : bool
            True if the device should be programmed with new instructions
            False if the old instructions should be executed again, so no programming is needed (just rerun last instructions)
        clock_terminal : str
            The device connection on which the clock signal is connected (e.g. 'PFI2')
        ao_channels : list str
            A list of all analog output channels that should be used 
        ao_data : 2d-numpy array, uint8
            A 2d-array containing the instructions for each ao_channel for every clock tick
        """        
        self.do_task.StopTask()
        if not fresh:
            if not self.wait_for_rerun:
                raise Exception("Cannot rerun Task.")
            self.do_task.StartTask() #just run old task again
            return
        elif not clock_terminal or not do_channels or do_data is None:
            raise Exception("Cannot progam device. Some arguments are missing.")

        self.do_task.ClearTask()
        self.do_task = Task()
        
        self.do_task.CreateDOChan(do_channels, "", DAQmx_Val_ChanPerLine)
        self.do_task.CfgSampClkTiming(clock_terminal, 10000000, DAQmx_Val_Rising, DAQmx_Val_FiniteSamps, do_data.shape[0])
        self.do_task.WriteDigitalLines(do_data.shape[0], False, 10.0, DAQmx_Val_GroupByScanNumber, do_data, self.do_read, None)

        #print("Wrote "+str(self.do_read)+" samples to the buffer")

        self.do_task.StartTask()


    def transition_to_manual(self, more_reps, abort):
        """
        Stop buffered mode
        """        
        if abort:
            self.wait_for_rerun = False
            self.do_task.ClearTask()
            self.do_task = Task()

            self.setup_static_channels()
            self.do_task.StartTask()
        else:
            self.wait_for_rerun = True

        #if abort:
            #self.program_manual(self.initial_values)