from PyDAQmx import Task
from PyDAQmx.DAQmxConstants import *
from PyDAQmx.DAQmxTypes import *
import numpy as np
from threading import Thread
import Queue


class NI_6713Device():

    def __init__(self, MAX_name, message_queue):
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
        self.read_Thread.start()

    def read_fun(self, message_queue):
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
                    self.transition_to_buffered(True, msg['clock_terminal'], msg['ao_channels'], msg['ao_data'])
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
        self.wait_for_rerun = False
        #setup AO channels
        for i in range(self.NUM_AO):
            self.ao_task.CreateAOVoltageChan(self.MAX_name + "/ao%d"%i, "", self.limits[0], self.limits[1], DAQmx_Val_Volts, None)    
        #setup DO port(s)
        self.do_task.CreateDOChan(self.MAX_name + "/port0/line0:7", "", DAQmx_Val_ChanForAllLines) 

    def shutdown(self):
        print("shutdown device")
        self.running = False
        self.ao_task.StopTask()
        self.ao_task.ClearTask()
        self.do_task.StopTask()
        self.do_task.ClearTask()

    def program_manual(self, front_panel_values):
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
        self.ao_task.StopTask()
        if not fresh:
            if not self.wait_for_rerun:
                raise Exception("Cannot rerun Task.")
            self.ao_task.StartTask() #just run old task again
            return
        elif not clock_terminal or not ao_channels or ao_data is None:
            raise Exception("Cannot progam device. Some arguments are missing.")

        self.ao_task.ClearTask()
        self.ao_task = Task()
        
        self.ao_task.CreateAOVoltageChan(ao_channels, "", -10.0, 10.0, DAQmx_Val_Volts, None)
        self.ao_task.CfgSampClkTiming(clock_terminal, 1000000, DAQmx_Val_Rising, DAQmx_Val_FiniteSamps, ao_data.shape[0])
        self.ao_task.WriteAnalogF64(ao_data.shape[0], False, 10.0, DAQmx_Val_GroupByScanNumber, ao_data, self.ao_read, None)

        self.ao_task.StartTask()

    def transition_to_manual(self, more_reps, abort):
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


class NI_DIODevice():

    def __init__(self, MAX_name, message_queue):
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
        self.read_Thread.start()

    def read_fun(self, message_queue):
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
        print("shutdown device")
        self.running = False
        self.do_task.StopTask()
        self.do_task.ClearTask()

    def program_manual(self, front_panel_values):
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

        self.do_task.StartTask()


    def transition_to_manual(self, more_reps, abort):
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