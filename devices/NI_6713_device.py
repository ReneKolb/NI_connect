import Queue
import numpy as np
from PyDAQmx import Task
from PyDAQmx.DAQmxConstants import *
from PyDAQmx.DAQmxTypes import *
from threading import Thread


class NI_6713Device():
    """
    This class is the interface to the NI driver for a NI PCI-6713 analog output card
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
        self.NUM_AO = 8
        self.NUM_DO = 8
        self.MAX_name = MAX_name
        self.limits = [-10, 10]

        #Create AO Task
        self.ao_task = Task()
        self.ao_read = int32()
        self.ao_data = np.zeros((self.NUM_AO,), dtype=np.float64)

        #Create DO Task
        self.do_task = Task()
        self.do_read = int32()
        self.do_data = np.zeros((self.NUM_DO,), dtype=np.uint8)

        self.setup_static_channels()

        #DAQmx Start Code
        self.ao_task.StartTask()
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
                #read an instruction from the message queue
                typ, msg = message_queue.get(timeout=0.5) 
            except Queue.Empty:
                continue #if there is no instruction in the queue, just read again until there is an instruction, or until the the the thread stops (running==False)

            # handle incoming instructions
            if typ == 'manual':
                # the msg argument contains the dict front_panel_values to send to the device
                self.program_manual(msg)
                message_queue.task_done() #signalise the sender, that the instruction is complete
            elif typ == 'trans to buff':
                #Transition to Buffered
                # msg is a dict containing all relevant arguments
                # If fresh is true, the hardware should be programmed with new commands, which were permitted
                # if fresh is false, use the last programmed harware commands again, so no hardware programming is needed at all
                if msg['fresh']:
                    self.transition_to_buffered(True, msg['clock_terminal'], msg['ao_channels'], msg['ao_data'])
                else:
                    self.transition_to_buffered(False, None, None, None)
                message_queue.task_done() #signalize that the task is done
            elif typ == 'trans to man':
                #Transition to Manual
                self.transition_to_manual(msg['more_reps'], msg['abort'])
                message_queue.task_done() # signalise that the task is done
            else:
                # an unknown/unimplemented instruction is requestet
                print("unkown message: "+msg)
                message_queue.task_done()
                continue   
                

    def setup_static_channels(self):
        self.wait_for_rerun = False
        #setup AO channels
        for i in range(self.NUM_AO):
            self.ao_task.CreateAOVoltageChan(self.MAX_name + "/ao%d"%i, "", self.limits[0], self.limits[1], DAQmx_Val_Volts, None)    
        #setup DO port(s)
        self.do_task.CreateDOChan(self.MAX_name + "/port0/line0:7", "", DAQmx_Val_ChanForAllLines) 

    def shutdown(self):
        """
        Shutdown the device (stop & clear all tasks). Also stop the message queue thread
        """
        print("shutdown device")
        self.running = False
        self.ao_task.StopTask()
        self.ao_task.ClearTask()
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
            self.ao_task.StopTask()
            self.ao_task.ClearTask()
            self.do_task.StopTask()
            self.do_task.ClearTask()
            self.ao_task = Task()
            self.do_task = Task()
            self.setup_static_channels()
            self.wait_for_rerun = False

        for i in range(self.NUM_AO):
            self.ao_data[i] = front_panel_values['ao%d'%i]
        self.ao_task.WriteAnalogF64(1, True, 1, DAQmx_Val_GroupByChannel, self.ao_data, byref(self.ao_read), None)

        for i in range(self.NUM_DO):
            self.do_data[i] = front_panel_values['do_%d'%i]
        self.do_task.WriteDigitalLines(1, True, 1, DAQmx_Val_GroupByChannel, self.do_data, byref(self.do_read), None)

    def transition_to_buffered(self, fresh, clock_terminal, ao_channels, ao_data):
        """
        Transition the device to buffered mode

        This method does the hardware programming if needed

        Parameters
        ----------
        fresh : bool
            True if the device should be programmed with new instructions
            False if the old instructions should be executed again, so no programming is needed (just rerun last instructions)
        clock_terminal : str
            The device connection on which the clock signal is connected (e.g. 'PFI0')
        ao_channels : list str
            A list of all analog output channels that should be used 
        ao_data : 2d-numpy array, float64
            A 2d-array containing the instructions for each ao_channel for every clock tick
        """
        self.ao_task.StopTask() #Stop the last task (static mode or last buffered shot)
        if not fresh:
            if not self.wait_for_rerun:
                raise Exception("Cannot rerun Task.")
            self.ao_task.StartTask() #just run old task again
            return
        elif not clock_terminal or not ao_channels or ao_data is None:
            raise Exception("Cannot progam device. Some arguments are missing.")

        self.ao_task.ClearTask() #clear the last task and create a new one with new parameters & instructions
        self.ao_task = Task()
        
        self.ao_task.CreateAOVoltageChan(ao_channels, "", -10.0, 10.0, DAQmx_Val_Volts, None)
        self.ao_task.CfgSampClkTiming(clock_terminal, 1000000, DAQmx_Val_Rising, DAQmx_Val_FiniteSamps, ao_data.shape[0])
        self.ao_task.WriteAnalogF64(ao_data.shape[0], False, 10.0, DAQmx_Val_GroupByScanNumber, ao_data, self.ao_read, None)

        self.ao_task.StartTask() #finally start the task

    def transition_to_manual(self, more_reps, abort):
        """
        Stop buffered mode
        """
        if abort:
            self.wait_for_rerun = False
            self.ao_task.ClearTask()
            self.do_task.StopTask()
            self.do_task.ClearTask()

            self.ao_task = Task()
            self.do_task = Task()

            self.setup_static_channels()
            self.ao_task.StartTask()
            self.do_task.StartTask()
        else:
            self.wait_for_rerun = True

        #if abort:
            #self.program_manual(self.initial_values)