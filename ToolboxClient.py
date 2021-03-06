#Instructions:
#Download and install Python 2.7 or 2.8 (not 3.x)
#go to this folder and run: python get-pip.py
#add c:\Python27\Scripts\ to the environment path
#close and reopen command prompt
#cmd run pip install requests

import os
import sys
import time
import requests
import json
import socket


def get_hosts():
    hostlist = []
    with open("hosts.txt", "r") as hosts:
        host = hosts.readline().rstrip()
        hostlist.append(host)
    return hostlist


def post_iof3_resultList(event, file):
    hosts = get_hosts()
    for host in hosts:
        try:
            print("sending results to " + host)

            # post sport software IOFv3 results file
            url = host + '/api/event/' + event + '/results'
            f = {'file': open(file, 'r')}
            #What should be in this header???
            #header = {'content-type': 'text/plain'}
            r = requests.post(url, files=f)
            print r.status_code, r.text
        except:
            print("failed to send results to " + host)

def put_clubcodetable(file):
    hosts = get_hosts()
    for host in hosts:
        print("sending clubs to " + host)
        
        url = host + '/api/clubs'
        f = {'file': open(file, 'r')}
        r = requests.put(url, files=f)
        print r.status_code, r.text

def put_cclasstable(event, file):
    hosts = get_hosts()
    for host in hosts:
        host = hosts.readline().rstrip()
        if not host: break
        print("sending classes to " + host)
        
        url = host + '/api/event/' + event + '/classes'
        f = {'file': open(file, 'r')}
        r = requests.put(url, files=f)
        print r.status_code, r.text

def put_eventtable(file):
    hosts = get_hosts()
    for host in hosts:
        host = hosts.readline().rstrip()
        if not host: break
        print("sending events to " + host)
        
        url = host + '/api/events'
        f = {'file': open(file, 'r')}
        r = requests.put(url, files=f)
        print r.status_code, r.text

def put_entrylist(event, file):
    hosts = get_hosts()
    for host in hosts:
        print("sending entries to " + host)
        
        url = host + '/api/event/' + event + '/entries'
        f = {'file': open(file, 'r')}
        r = requests.put(url, files=f)

def poll_for_results(eventcode, dir):
    lastUpdate = None
    while True:
        dircontents = os.listdir(dir)
        if len(dircontents) == 1:
            # TODO actually get the right file rather than picking the only one!
            fn = os.path.join(dir, dircontents[0])
            t = os.path.getmtime(fn)
            if t > lastUpdate:
                print "found new file, posting"
                post_iof3_resultList(eventcode, fn)
                lastUpdate = t
            else:
                print "no new file"
        print "sleeping, brb"
        for i in range(60):
            time.sleep(1)
    return

def relay_wibox():
    from sireader import SIReaderControl
    WiBox1 = 'socket://192.168.103.201:10001'
    reader = SIReaderControl(port=WiBox1)
    #with open('confighosts.txt', 'r') as f:
    #    hosts = []
    #    for line in f:
    #        hosts.append(line.rstrip())

    hosts = get_hosts()
    while True:
        punches = reader.poll_punch()
        if len(punches) > 0:
            for p in punches:
                punch = {'station': p[0], 'sicard': p[1], 'time': p[2].strftime('%H:%M:%S')}
                print punch
                header = {'content-type': 'text/json'}
                for h in hosts:
                    print 'Sending to ', h
                    url = h + '/telemetry/' + str(punch['station'])
                    r = requests.post(url, headers=header, data=json.dumps(punch))
                    print 'Sent {} to {}'.format(punch, h)
    return

if __name__ == '__main__':
    method = sys.argv[1]
    
    if method == 'iof3':
        ''' 
        post an iof3 resultList file to refresh the data on the server
        python ToolboxClient.py iof3 2016-02-27-1 testdata.xml 
        '''
        post_iof3_resultList(sys.argv[2], sys.argv[3])

    elif method == 'monitor':
        ''' 
        monitor a folder for new results and post them
        usage: python ToolboxClient.py monitor 2016-05-05-1 ./results_go_here 
        '''
        poll_for_results(sys.argv[2], sys.argv[3])

    elif method == 'wibox-relay':
        '''
        relay data incoming from a given wi-box on TCP to the host via a POST request
        usage: python ToolboxClient.py wibox-relay
        '''
        relay_wibox()

    elif method == 'telemetry':
        ''' 
        mimic a call coming in from a remote punch box
        python ToolboxClient.py http://localhost telemetry 17 99999 "09:42:17" 
        '''
        d = {}
        d['station'] = sys.argv[2]
        d['sicard'] = sys.argv[3]
        d['time'] = sys.argv[4]
        host = sys.argv[1]
        url = host + '/telemetry/' + d['station']
        header = {'content-type': 'text/json'}
        r = requests.post(url, headers=header, data=json.dumps(d))
        print r.text

    elif method == 'clubs':
        '''
        post a json file containing the mapping of club code to full name
        python ToolboxClient.py clubs clubcodes.json
        '''
        put_clubcodetable(sys.argv[2])

    elif method == 'classes':
        '''
        post a json file containing the mapping of class code to full name
        python ToolboxClient.py classes 2016-02-27-1 classcodes.csv
        '''
        put_cclasstable(sys.argv[2], sys.argv[3])

    elif method == 'entries':
        '''
        post a xml file containing the entries for the meet
        python ToolboxClient.py entries 2016-02-27-1 meetentries.xml
        '''
        put_entrylist(sys.argv[2], sys.argv[3])

    elif method == 'events':
        '''
        post a tsv file containing the event information
        python ToolboxClient.py events eventinfo.tsv
        '''
        put_eventtable(sys.argv[2])

    # elif method == 'prep-db':
        # '''
        # prep the database with classes, teams, and anything else...
        # python ToolboxClient.py prep-db
        # '''
        # put_clubcodetable('clubcodes.json')
        # put_cclasstable('classcodes.json')
