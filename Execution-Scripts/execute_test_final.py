##Modules required for operation
import os
import socket
import ftplib
import sys
import hashlib
import iperf3
import json
import shutil
import wiringpi2
import time
import python_arptable
import subprocess32 as subprocess
import netifaces
from python_arptable import get_arp_table
from uuid import getnode as get_mac
from paramiko import SSHClient
import paramiko
from scp import SCPClient

##Set the hostname of the iperf server to perform tests againsts
hostname = "0.0.0.0"

#Define global variables
sent_gbps = ""
received_gbps = ""

##Sleeps are used in the script to add delays for screen output to make each stage
##of the test easily readable.

############### Deals with screen initialisation on the board ###############
# --LCD
LCD_ROW = 2 # 16 Char
LCD_COL = 16 # 2 Line
LCD_BUS = 4 # Interface 4 Bit mode

PORT_LCD_RS = 7 # GPIOY.BIT3(#83)
PORT_LCD_E = 0 # GPIOY.BIT8(#88)
PORT_LCD_D4 = 2 # GPIOX.BIT19(#116)
PORT_LCD_D5 = 3 # GPIOX.BIT18(#115)
PORT_LCD_D6 = 1 # GPIOY.BIT7(#87)
PORT_LCD_D7 = 4 # GPIOX.BIT4(#104)
# --Buttons
PORT_LCD_5 = 5

# --LCD
##Initialise the screen
wiringpi2.wiringPiSetup()
# --LCD
lcdHandle = wiringpi2.lcdInit(LCD_ROW, LCD_COL, LCD_BUS,
PORT_LCD_RS, PORT_LCD_E,
PORT_LCD_D4, PORT_LCD_D5,
PORT_LCD_D6, PORT_LCD_D7, 0, 0, 0, 0);
lcdRow = 0 # LCD Row
lcdCol = 0 # LCD Column
# --LCD

##Function displays the TopLine and BottomLine message passed on the screen
def ScreenOutput(TopLine, BottomLine):
    wiringpi2.lcdClear(lcdHandle)
    wiringpi2.lcdPosition(lcdHandle, lcdCol, lcdRow)
    wiringpi2.lcdPrintf(lcdHandle, TopLine)
    wiringpi2.lcdPosition(lcdHandle, lcdCol, lcdRow + 1)
    wiringpi2.lcdPrintf(lcdHandle, BottomLine)


##Function performs a ping test against the server to ensure that it is accessible
def pingHome():
    ScreenOutput('Ping Test', 'Executing...')
    time.sleep(1)
    ##Perform an OS command to execute the ping test
    response = os.system("ping -c 2 " + hostname)
    status = ""

    ##Check the result to see whether the pings were successful
    if response == 0:
      status = True
      ScreenOutput('Ping Test', 'Succesful')
      time.sleep(1)
    else:
      status = False
      ScreenOutput('Ping Test', 'Unsuccessful')
      time.sleep(3)
    return status

##Function performs a test against the FTP socket to ensure the FTP service is accessible on the server
def testSCPSocket() :
    #check ftp is running on the host by established a socket on port 21. Set the timeout for the socket to 3 seconds
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex((hostname, 22))
    ##Closes the socket to ensure the connection is closed
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
    ##Check whether the socket could connect successfully
    if result == 0:
        ScreenOutput('SFTP Test', 'Succesful')
        time.sleep(1)
        return True
    else:
        ScreenOutput('SFTP Test', 'Unsuccessful')
        time.sleep(3)
        ScreenOutput('Test Failed', 'Retrying...')
        time.sleep(1)
        ##Rerun the test if the FTP socket fails
        executeTesting()
        return False

##Function performs a check against the default IPerf port 5201 to ensure it is up
def testIperfSocket() :
    #check iperf is running on the host by establishing the socket the port 5201
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex((hostname, 5201))
    if result == 0:
        sock.shutdown(socket.SHUT_RDWR)
        ##Close the socket otherwise the server thinks a test is still occurring which prevents any further tests
        sock.close()
        ScreenOutput('Iperf Connection', 'Succesful')
        time.sleep(1)
        return True
    else:
        ScreenOutput('Iperf Connection', 'Unsuccessful')
        time.sleep(3)
        ScreenOutput('Test Failed', 'Retrying...')
        time.sleep(1)
        ##Rerun the test if the IPerf connection fails
        executeTesting()
        return False

def copySCPfiles(hashed_file_name):
    #Specify the location of the log file
    hashed_file_path = "/home/iperf/" + hashed_file_name
    ssh = SSHClient()
    ssh.load_system_host_keys()
    #Will allow SSH keys if they are missing
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    #Connect to the IPerfServer
    ssh.connect(hostname, username="username")
    #Use SCP to copy the files
    scp = SCPClient(ssh.get_transport())
    scp.put(hashed_file_path, hashed_file_path)
    scp.close()
    ScreenOutput('Test Copied', 'To Server')
    time.sleep(1)

##Function will obtain the default gateway MAC address
def get_dg_mac():
    ##Grab the default gateway address
    gws = netifaces.gateways()
    gateway_address_list = gws['default'][netifaces.AF_INET]
    gateway_address = gateway_address_list[0]

    ##Import the contents of the ARP table for reading
    arp_table = get_arp_table()
    ##Loop through each ARP entry to check whether the gateway address is present
    for arp_entry in arp_table:
        if arp_entry["IP address"] == gateway_address:
            ScreenOutput('default GW MAC', arp_entry["HW address"])
            ##Grab the MAC address associated with the gateway address
            gateway_mac = arp_entry["HW address"]
            time.sleep(3)

    return gateway_mac

##Function will take the returned JSON and append new required values on the end
def edit_json(hashed_file_name, gateway_mac) :
    ##Open the file and read the contents
    file_path = "/home/iperf/" + hashed_file_name
    f = open(file_path, 'r')
    file_contents = f.read()
    f.close()

    ##Obtain the MAC address of the board
    board_mac = get_mac()
    ##Format the MAC address into a common form
    formatted_board_mac = str(':'.join(("%012X" % board_mac)[i:i+2] for i in range(0, 12, 2)))

    ##Load in the contents of the file and convert to a JSON object
    json_file_contents = json.loads(file_contents)
    ##Add the new JSON values onto the end, the boards MAC address, the file hash, and the gateway MAC
    json_file_contents["end"]["host_information"] = {"mac_address": formatted_board_mac, "hash": hashed_file_name, "gateway_mac": gateway_mac}

    ##Dump the new JSON information into the file
    json.dump(json_file_contents, open(file_path, "w"))

##Function will run the Line Test
def runTest() :
    global sent_gbps
    global received_gbps
    global hostname

    ScreenOutput('Speed Test', 'Executing...')
    time.sleep(1)

    ##Try and execute the IPerf test. Specifies a timeout of 14 seconds for the IPerf connection
    try:
        procId = subprocess.run(["iperf3","-c", hostname, "-J", "-t", "10" ], stdout=subprocess.PIPE, timeout=14)
    ##Raise an error if the timeout expires and re-run the test
    except subprocess.TimeoutExpired:
        ScreenOutput('Speed Test', 'Failed')
        time.sleep(3)
        executeTesting()
    ##Take the stdout and convert to JSON from the executed command
    json_output = procId.stdout

    ##Write the JSON to the file
    f = open('/home/iperf/results.json', 'w+')
    string_to_write = str(json_output)
    f.write(string_to_write)
    f.close()

    file_name = "/home/iperf/results.json"

    ##Open the JSON file just created
    with open(file_name) as json_data:
        jdata = json.load(json_data)

    ##Check to see whether the JSON entered into the file is from a successful test and not a server
    ##busy message
    try:
        ##Extract the sent and received BPS for screen output
        sent_bps = jdata['end']['sum_sent']['bits_per_second']
        received_bps =  jdata['end']['sum_received']['bits_per_second']
    ##Display the error if the server is busy if the JSON is not complete
    except:
        ScreenOutput('Server Busy', 'Retrying')
        time.sleep(3)
        ##Rerun the test again
        executeTesting()

    ##Convert the bps into gbps
    sent_gbps = sent_bps / 1000000000
    received_gbps = received_bps / 1000000000
    ScreenOutput('Speed Test', 'Finished')
    time.sleep(1)

    ##Read in the contents of the file in order to generate a hash of the data
    with open(file_name) as file_to_hash:
        data = file_to_hash.read()
        md5_hash = hashlib.md5(data).hexdigest()

    ##Take the last 10 characters from the hash to make it shorter
    hash_name = md5_hash[:10]
    new_hash_name = "/home/iperf/" + hash_name.upper()
    ##Rename the file from results.json to the generated hash to uniquely identify the hash
    shutil.move("/home/iperf/results.json", new_hash_name)

    lowerHash = md5_hash[:10]
    ##Convert the hash to uppercase for nicer viewing
    upperHash = lowerHash.upper()

    return upperHash

##Function actually conducts the test and performs the checks
def executeTesting():
    global sent_gbps
    global received_gbps

    ##Display that the test is starting
    ScreenOutput('Starting', 'Speed Test')
    time.sleep(2)
    ##Execute the PingHome function in order to check whether there is connectivity to the IPerf Server
    connectionStatus = pingHome()

    if connectionStatus == True :
        ##Check whether there is connectivity to the SCP port
        testSCPSocket()
        ##Check whether there is connectivity to the IPerf Server on port 5201 for the IPerf test
        testIperfSocket()
        ##Obtain the hash of the file received from executing the test
        hash_file = runTest()
        ##Obtain the MAC address of the current gateway
        gateway_mac = get_dg_mac()
        ##Change the JSON file created to include the extra data including gateway MAC, board MAC, and hash
        edit_json(hash_file, gateway_mac)
        ##Call the function that will copy the test file specified by the hash to the IPerf Server
        copySCPfiles(hash_file)
        ##Execute an infinite while loop to loop the screen output at the end of the test
        while True:
            ##Display the test case ID which is equal to the hash
            ScreenOutput('Test ID', hash_file)
            time.sleep(5)
            ##Display the upload speed extracted from the JSON file
            ScreenOutput('Upload:', str(round(sent_gbps, 2)) + " Gbps" )
            time.sleep(2)
            ##Display the download speed extracted from the JSON file
            ScreenOutput('Download:', str(round(received_gbps, 2)) + " Gbps")
            time.sleep(2)
    else:
        ##If the ping test fails meaning no connectivity to the IPerf server then restart the test again
        ScreenOutput('Test Failed', 'Retrying...')
        time.sleep(3)
        executeTesting()
##Execute the Line Test for the first time
executeTesting()
