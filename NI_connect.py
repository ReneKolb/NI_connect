from __future__ import print_function
import socket
import sys
from os import system

"""National Instruments Connect

Network interface for BLACS to communicate with remote NI-cards

Usage: python NI_connect.py [options]

Options:
  -a ..., --address=...   use specified address to connect to BLACS server
  -p ..., --port=...      use specified port to connect to BLACS server
  -D ..., --Device=...    use specified Device (MAX name)
  -t ..., --type=...      use specified Device type (like 6713, dio, ...)
  -r, --no_reconnect      disable autoreconnect
  -h, --help              show this help

Examples:
  NI_connect.py                                      connect to BLACS with default settings
  NI_connect.py -D Dev6                              use Dev6 as NI-card and connect to BLACS
  NI_connect.py -a 192.168.1.112 -p 10028 -D Dev6    use Dev6 and connect on port 10028 to BLACS with address 192.168.1.112

"""

__author__ = "Rene Kolb (rene.kolb@gmail.com)"
__version__ = "$Revision: 1.0 $"
__date__ = "$Date: 2016/12/04 12:20 $"

from multiprocessing import JoinableQueue
from Client_Connection import Client_Connection
#from NI_device import NI_6713Device, NI_DIODevice
import sys
import getopt

#DEFAULT_PORT = 1028

def usage():
    print(__doc__)

def main(argv):
    print("\n     ########################")
    print("     #                      #")
    print("     #      NI-CONNECT      #")
    print("     #                      #")
    print("     ########################\n")

    #define some defaults
    MAX_name = 'Dev1'
    address = '192.168.1.114'
    port = 1028 
    dev_type = "6713"
    disable_autoreconnect = False

    try:
        opts, args = getopt.getopt(sys.argv[1:], 'a:p:hD:t:r',['address=','port=','help','Device=','type=',"no_reconnect"])
    except getopt.GetoptError:
        usage()
        sys.exit(2) 

    #opts are recognized options
    #args are remaining arguments (like a source filename)
    for opt, arg in opts:
        if opt in ('-h','--help'):
            usage()
            sys.exit()
        elif opt in ('-D', '--Device'):
            MAX_name = arg
        elif opt in ('-t', '--type'):
            dev_type = arg
        elif opt in ('-a', '--address'):
            address = arg
        elif opt in ('-p', '--port'):
            port = int(arg)
        elif opt in ('-r','--no_reconnect'):
            disable_autoreconnect = True    

    system("title NI-Connect: "+str(MAX_name)+" as "+str(dev_type)+"    BLACS: "+str(address)+":"+str(port)) #set console title
    print("Connect to BLACS "+str(address)+":"+str(port)+". Use "+str(MAX_name)+" as type "+str(dev_type)+"\n")
    ni_connect = NI_Connect(MAX_name, address, port, dev_type, disable_autoreconnect)
    ni_connect.start()        


class NI_Connect():

    def __init__(self, MAX_name, BLACS_address, BLACS_port, Device_type, disable_autoreconnect=False):
        """
        Initialise the NI connect Object with the given parameters

        Parameters
        ----------
        MAX_name : str
            The Device's unique name which the driver uses to find the actual hardware
        BLACS_address : str
            The network (IP)address of the BLACS control server
        BLACS_port : int
            The network TCP-port which is used to communicate with the BLACS control server
        Device_type : str ['6713', 'dio']
            Tell NI connect, which card type we are using (like 'dio' for NI-DIO-32HS, or '6713' for NI-PCI6713)
        disable_autoreconnect : bool
            A flag to disable the auto reconnect when the connection is lost
        """
        self.msg_queue = JoinableQueue() #a quque to communicate between the network BLACS thread and the driver thread
        #initialise the network connection to BLACS
        self.client_connection = Client_Connection(self.msg_queue, debug=True, autoreconnect=(not disable_autoreconnect), MAX_name=MAX_name)
        self.BLACS_address = BLACS_address
        self.BLACS_port = BLACS_port

        #select and initialise the correct NI device driver class
        if Device_type == '6713':
            from devices.NI_6713_device import NI_6713Device
            self.NI_device = NI_6713Device(MAX_name, self.msg_queue)
        elif Device_type =='dio':
            from devices.NI_DIO_device import NI_DIODevice
            self.NI_device = NI_DIODevice(MAX_name, self.msg_queue)  
        else:
            print("unsupported device type")
            sys.exit()    
        self.NI_device.start() #start the device driver

    def start(self):
        """
        This method connects to BLACS using the parameters from  __init__() and handles keyboard inputs
        """
        self.client_connection.connect((self.BLACS_address, self.BLACS_port))
        do_close = False

        while not do_close:
            try:
                print("\nType 'close' to exit NI-Connect")
                command = raw_input(">")
            except (KeyboardInterrupt, SystemExit):
                #due to Strg+C interrupt...
                command = ""
                do_close = True
            except Exception as ex:
                raise

            if "close" in command:
                do_close = True
                self.client_connection.close()
                self.NI_device.shutdown()       

if __name__ == "__main__":
    system("title NI-Connect") #set the console title
    main(sys.argv[1:])
