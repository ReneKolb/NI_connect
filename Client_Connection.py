from __future__ import print_function
import socket, errno
import sys
from threading import Thread
import time
import traceback
import struct
import numpy as np
import math

class Client_Connection():

    def __init__(self, message_queue, debug=False, autoreconnect = True, MAX_name=None):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.message_queue = message_queue
        self.debug = debug
        self.running = True
        self.connected = False
        self.autoreconnect = autoreconnect
        self.MAX_name = MAX_name
        self.read_Thread = Thread(target=self.read_fun, args=(message_queue,))
        self.len_packer = struct.Struct('>i') #int 4bytes
        self.type_packer = struct.Struct('>h') #short 2bytes

    def connect(self, server_address, reconnect = False):
        """
        Open a TCP connection to BLACS

        Parameters
        ----------
        server_address : tuple (host_address, port)
            The parameters to used to connect tp BLACS
        reconnect : bool
            This parameter determins if this method call is a reconnect. If so, we don't need to start the receiving thread since it is still running
        """
        self.last_server_address = server_address
        if self.debug: print('connecting to %s on port %s...'%server_address)
        try:
#            self.socket.settimeout(5)
            self.socket.connect(server_address)
#            self.socket.settimeout(0) #make blocking again
            if self.debug: print('connected successfully')
            self.connected = True
            if not reconnect: #if it's a reconnect, the thread is already running
                self.read_Thread.start()
        except Exception as ex:
            print('Error. cannot connect to server: '+str(ex), sys.stderr) 

    def close(self):
        """
        This method closes the current TCP connection to BLACS
        """
        print("closing network connection")
        self.running = False
        self.socket.close()

    def read_fun(self, message_queue):
        """
        The method where all TCP messages / packed are received, decoded and delegated

        A message packet consists of:
            4 bytes          length
            2 bytes          packet type
            arbitrary bytes  data
        """
        self.running = True

        while self.running:
            if not self.connected:
                print("not connected. Trying to reconnect...")
                self.socket.close() #make sure that the socket is closed
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.connect(self.last_server_address, reconnect=True)
            else:  
                try:
                    packet_length = self.socket.recv(4) #packet length is encoded as int (4bytes)
                    if not packet_length: #connection is closed
                        self.socket.close()
                        #self.running = False
                        self.connected = False
                        self.running = self.autoreconnect
                        print("connection closed by host")
                        continue

                    packet_length, = self.len_packer.unpack(packet_length)
                    packet_type = self.socket.recv(2) #packet type is encoded as short (2bytes)
                    packet_type, = self.type_packer.unpack(packet_type)
                    if packet_type == 0:
                        # Packet:
                        #    raw string message
                        msg = self.socket.recv(packet_length)
                        msg = msg.decode('utf-8')
                        print(msg)
                    elif packet_type == 1: 
                        # Packet:
                        #    ping packet. ignore
                        pass
                    elif packet_type == 2:
                        # Packet:
                        #    program manual using float64
                        msg = self.socket.recv(packet_length)
                        msg = msg.decode('utf-8')
                        msg = eval(msg) #str to dict
                        message_queue.put(('manual', msg))
                    elif packet_type == 3:
                        # Packet:
                        #    transition to buffered using float64 (for analog output devices)
                        msg = self.socket.recv(packet_length)
                        msg = msg.decode('utf-8')
                        data = eval(msg) #receive clock_terminal & used channels
                        #print("Program Fresh: "+str(data['fresh']))
                        if not data['fresh']:
                            message_queue.put(('trans to buff', data))
                            message_queue.join() #wait for all the tasks to be finished
                            self.socket.send(self.type_packer.pack(5)) #send 'task done'-message to BLACS
                            continue

                        shape0 = self.socket.recv(4)
                        shape0, = self.len_packer.unpack(shape0)
                        shape1 = self.socket.recv(4)
                        shape1, = self.len_packer.unpack(shape1)

                        ao_data = np.empty(int(math.ceil(1+shape0*shape1/1024.0)*1024.0), dtype=np.dtype('>f')) #4bytes per number
                        to_receive = 4 * shape0 * shape1 #bytes to receive
                        received_amount = 0
                        while received_amount < to_receive:
                            remaining = to_receive - received_amount
                            if remaining >= 4*1024:
                                amount = self.socket.recv_into(ao_data[received_amount/4:received_amount/4+1024],4*1024)
                            else:
                                amount = self.socket.recv_into(ao_data[received_amount/4:(received_amount+remaining)/4], remaining)    
                            received_amount += amount

                        ao_data = np.resize(ao_data, (shape0, shape1))
                        ao_data = ao_data.astype(np.float64)
                        data['ao_data'] = ao_data
                        message_queue.put(('trans to buff',data))
                        message_queue.join() #wait for all the tasks to be finished
                        self.socket.send(self.type_packer.pack(5)) # send 'task done'-message to BLACS

                    elif packet_type == 4:
                        # Packet:
                        #    transition to manual
                        msg = self.socket.recv(packet_length)
                        msg = msg.decode('utf-8')
                        msg = eval(msg) #str to dict
                        message_queue.put(('trans to man', msg))
                        message_queue.join()
                        self.socket.send(self.type_packer.pack(5)) #send 'task done'-message to BLACS
                    elif packet_type == 6:
                        # Packet:
                        #    transition to buffered using uint8 (for digital output devices)
                        msg = self.socket.recv(packet_length)
                        msg = msg.decode('utf-8')
                        data = eval(msg) #receive clock_terminal & used channels
                        #print("Program Fresh: "+str(data['fresh']))
                        if not data['fresh']:
                            message_queue.put(('trans to buff', data))
                            message_queue.join() #wait for all the tasks to be finished
                            self.socket.send(self.type_packer.pack(5)) #send 'task done'-message to BLACS
                            continue

                        shape0 = self.socket.recv(4)
                        shape0, = self.len_packer.unpack(shape0)
                        shape1 = self.socket.recv(4)
                        shape1, = self.len_packer.unpack(shape1)

                        do_data = np.empty(int(math.ceil(1+shape0*shape1/1024.0)*1024.0), dtype=np.dtype('b')) #1bytes per number
                        to_receive = 1 * shape0 * shape1 #bytes to receive
                        received_amount = 0
                        while received_amount < to_receive:
                            remaining = to_receive - received_amount
                            if remaining >= 1*1024:
                                amount = self.socket.recv_into(do_data[received_amount/1:received_amount/1+1024],1*1024)
                            else:
                                amount = self.socket.recv_into(do_data[received_amount/1:(received_amount+remaining)/1], remaining)    
                            received_amount += amount

                        do_data = np.resize(do_data, (shape0, shape1))
                        do_data = do_data.astype(np.uint8)
                        data['do_data'] = do_data
                        message_queue.put(('trans to buff',data))
                        message_queue.join() #wait for all the tasks to be finished
                        self.socket.send(self.type_packer.pack(5)) #send 'task done'-message to BLACS
                    elif packet_type == 7:
                        # Packet:
                        #    the server requests the MAX_name
                        msg = self.len_packer.pack(len(self.MAX_name)) + self.MAX_name.encode('utf-8')
                        self.socket.send(msg)
                    elif packet_type == 8:
                        # Packet:
                        #    the server requests a connection close due to wrong MAX_name
                        self.autoreconnect = False
                    else:
                        print("Packet size: "+str(packet_length))
                        print("Packet type: "+str(packet_type))   

                except socket.timeout:
                    print("read timeout")
                    continue
                except socket.error as error:
                    if error.errno == errno.WSAECONNRESET:    #host closed the connection
                        self.socket.close()
                        self.connected = False
                        self.running = self.autoreconnect
                except Exception as ex:
                    traceback.print_exc()
                    #print("Exception in read Fun: "+str(ex))
                    self.socket.close()
                    self.connected = False
                    self.running = self.autoreconnect

