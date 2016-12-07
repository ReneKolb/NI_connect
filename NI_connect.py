from __future__ import print_function
import socket
import sys
from os import system

#import readline
#import struct,fcntl,termios
"""National Instruments Connect

Network interface for BLACS to communicate with NI-cards

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
from NI_device import NI_6713Device, NI_DIODevice
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

    system("title NI-Connect: "+str(MAX_name)+" as "+str(dev_type)+"    BLACS: "+str(address)+":"+str(port)) #set title
    print("Connect to BLACS "+str(address)+":"+str(port)+". Use "+str(MAX_name)+" as type "+str(dev_type)+"\n")
    ni_connect = NI_Connect(MAX_name, address, port, dev_type, disable_autoreconnect)
    ni_connect.start()        


class NI_Connect():

    def __init__(self, MAX_name, BLACS_address, BLACS_port, Device_type, disable_autoreconnect):
        self.msg_queue = JoinableQueue()
        self.client_connection = Client_Connection(self.msg_queue, debug=True, autoreconnect=(not disable_autoreconnect))
        self.BLACS_address = BLACS_address
        self.BLACS_port = BLACS_port

        if Device_type == '6713':
            self.NI_device = NI_6713Device(MAX_name, self.msg_queue)
        elif Device_type =='dio':
            self.NI_device = NI_DIODevice(MAX_name, self.msg_queue)  
        else:
            print("unsupported device type")
            sys.exit()    
        self.NI_device.start()

    def start(self):
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

        # while not do_close:
        #     try:
        #         command = raw_input(">")
        #     except (KeyboardInterrupt, SystemExit):
        #         #due to Strg+C interrupt...
        #         command = ""
        #         do_close = True
        #     except Exception as ex:
        #         raise

        #     if "close" in command:
        #         do_close = True
        #         print("closing...")
        #         self.client_connection.close()
        #     elif "connect" in command:
        #         cmd = command.split()
        #         if len(cmd) == 1: #only 'connect'
        #             print('Too view arguments', sys.stderr)
        #         elif len(cmd) == 2: #'connect host:port'
        #             args = cmd[1].split(':')
        #             if len(args) == 1:
        #                 host = args[0]
        #                 port = DEFAULT_PORT
        #             elif len(args) == 2:
        #                 host = args[0]
        #                 port = int(args[1])
        #             else:
        #                 host = None
        #                 port = None
        #                 print("Wrong usage.",sys.stderr)
        #             self.client_connection.connect((host, port))
        #         else:
        #             print("Wrong usage. 'connect host:port", sys.stderr)
        #     elif "test" in command:
        #         spl = command.split()
        #         fpv = {}
        #         for i in range(8):
        #             fpv['ao%d'%i] = 0
        #         fpv['ao0'] = float(spl[1])
        #         self.NI_device.program_manual(fpv)
        #         print("programmed.")
        #     elif not do_close:
        #         print('Unkown command: "'+str(command)+'"')

    

if __name__ == "__main__":
    system("title NI-Connect") #set title
    main(sys.argv[1:])
