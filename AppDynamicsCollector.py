# AppDynamcis Integration Plugin with EMC MNR.
# Developed by: Mohamed ELMesseiry, m.messeiry@gmail.com, 2015

__author__ = 'Mohamed ELMesseiry'

from appd.request import AppDynamicsClient


import os,json, calendar, logging
from collections import defaultdict
from datetime import datetime
from time import mktime
from dateutil import parser as DUp
from socket import *

from lxml.builder import ElementMaker
from lxml import etree
import tzlocal

from appd.cmdline import parse_argv
from appd.request import AppDynamicsClient


serverHost = '10.10.4.225'
serverPort = 2222

######  vars
doSendToBackend = True
printData = True


s = None
#============================================================================================
# Removing non-printable characters from a string
#============================================================================================
def filter_non_printable(obj):
    if isinstance(obj, list):
        for i in range(0,len(obj)):
            obj[i] = filter_non_printable(obj[i])
        return obj
    else:
        return ''.join([c for c in obj if ord(c) > 31 or ord(c) == 9])

#============================================================================================
# SEND DATA to Socket
#============================================================================================

def sendToBackend(dataToSend):
	global s
	if not s:
		s = socket(AF_INET,SOCK_STREAM)    # create a TCP socket
		s.connect((serverHost,serverPort)) # connect to server on the port
	if not "\n" in dataToSend: dataToSend+= "\n"
	s.send(dataToSend.encode('utf-8')) # send the data

def send(data):
	if doSendToBackend: sendToBackend(data)
	if printData: print data


#============================================================================================
# Convert to TimeStamp
#============================================================================================
def convertToTimeStamp(ts):
	return str(int(time.mktime(time.strptime(ts,"%Y-%m-%d %H:%M:%S"))))


#============================================================================================
# Convert Data to Raw Data Format
#============================================================================================

def toRawData(timestamp,group,var,val,device,devtype,unit,name,source,other):
	result =  "+r\t"+timestamp+"\t"+group+"\t"+var+"\t"+val+"\tdevice="+device+"\tdevtype="+devtype+"\tunit=""\tname="+name+"\tsource="+source
	if other:
		result += "\t"+other
	return result


#============================================================================================
##### MAIN PROCESSING #######
#============================================================================================

# The report will generate data for the 24-hour period before midnight of the current day. To change the
# reporting period, adjust these variables.

time_in_mins = 5000
end_time = datetime.now()
end_epoch = int(mktime(end_time.timetuple())) * 1000


# Helper functions

def now_rfc3339():
	return datetime.now(tzlocal.get_localzone()).isoformat('T')


# Parse command line arguments and create AD client:

#args = parse_argv()
#c= AppDynamicsClient("http://staging.demo.appdynamics.com","ADPartner","adsellappd")

c= AppDynamicsClient("http://10.10.12.137:8090","admin","changeme")
#c = AppDynamicsClient(args.url, args.username, args.password, args.account, args.verbose)


# Get the list of configured apps, and get backend metrics for each one:

METRIC_MAP = {'Average Block Time (ms)': 'abt',
			  'Average CPU Used (ms)': 'cpu',
			  'Average Request Size': 'req_size',
			  'Average Response Time (ms)': 'art',
			  'Average Wait Time (ms)': 'wait_time',
			  'Calls per Minute': 'cpm',
			  'End User Average Response Time (ms)': 'eum_art',
			  'End User Network Average Response Time (ms)': 'eum_net',
			  'End User Page Render Average Response Time (ms)': 'eum_render',
			  'Errors per Minute': 'epm',
			  'Normal Average Response Time (ms)': 'norm_art',
			  'Number of Slow Calls': 'slow',
			  'Number of Very Slow Calls': 'veryslow',
			  'Stall Count': 'stalls'}


empty_row = dict([(x,0) for x in METRIC_MAP.values()])
rows = defaultdict(dict)

for app in c.get_applications():
	print app.name
	bt_list = c.get_bt_list(app.id)

	for md in c.get_metrics('Business Transaction Performance|Business Transactions|*|*|*',
							app.id, time_range_type='BEFORE_TIME', end_time=end_epoch,
							duration_in_mins=time_in_mins, rollup=True):

		# Get the last 3 components of the metric path. This should be 'tier_name|bt_name|metric_name'.
		tier_name, bt_name, metric_name = md.path.split('|')[-3:]
		tier_bts = bt_list.by_tier_and_name(bt_name, tier_name)
		if tier_bts:
			bt = tier_bts[0]
			if len(md.values) > 0 and METRIC_MAP.has_key(metric_name):
				key = (tier_name, bt_name)
				rows.setdefault(key, empty_row.copy()).update({'app_id': app.id,
															   'app_name': app.name,
															   'bt_id': bt.id,
															   'bt_name': bt.name,
															   'tier_name': bt.tier_name,
															   'type': bt.type,
															   METRIC_MAP[metric_name]: md.values[0].value})
					#print rows.setdefault(key, empty_row.copy())



XSI = 'http://www.w3.org/2001/XMLSchema-instance'
E = ElementMaker(nsmap={'xsi': XSI})

root = E.BusinessTransactions(Controller=c.base_url, GenerationTime=now_rfc3339())
root.set('{%s}noNamespaceSchemaLocation' % XSI, 'bt_metrics.xsd')


timestamper = int(mktime(datetime.now().timetuple()))

for k, v in sorted(rows.items()):
	v['calls'] = v['cpm'] * time_in_mins
	v['errors'] = v['epm'] * time_in_mins
	v['error_pct'] = round(float(v['errors']) / float(v['calls']) * 100.0, 1) if v['calls'] > 0 else 0

	root.append(E.BusinessTransaction(
		E.TimeStamp(str(timestamper)),
		E.ApplicationName(v['app_name']),
		E.BusinessTransactionName(v['bt_name']),
		E.TierName(v['tier_name']),
		E.AverageResponseTime(str(v['art'])),
		E.CallsPerMinute(str(v['cpm'])),
		E.TotalCalls(str(v['calls'])),
		E.TotalErrors(str(v['errors'])),
		E.ErrorsPerMinute(str(v['epm'])),
		E.ErrorPercentage(str(v['error_pct'])),
		E.SlowCalls(str(v['slow'])),
		E.VerySlowCalls(str(v['veryslow'])),
		E.Stalls(str(v['stalls'])),
		))

	timeStamp = str(timestamper)
	applicationName = str(v['app_name'])
	businessTransactionName=str(v['bt_name'])
	tierName=str(v['tier_name'])
	averageResponseTime = str(v['art'])
	callsPerMinute=str(v['cpm'])
	totalCalls=str(v['calls'])
	totalErrors=str(v['errors'])
	errorsPerMinute=str(v['epm'])
	errorPercentage=str(v['error_pct'])
	slowCalls=str(v['slow'])
	verySlowCalls=str(v['veryslow'])
	stalls=str(v['stalls'])

	print timeStamp
	print applicationName
	print businessTransactionName
	print tierName

	print averageResponseTime
	print callsPerMinute
	print totalCalls
	print totalErrors
	print errorsPerMinute
	print errorPercentage
	print slowCalls
	print verySlowCalls
	print stalls


	group = "group"
	unit = ""
	var = str(applicationName) + str(businessTransactionName) + str(tierName)
	source = "AppDynamics"
	other="appName=%s\tbusTrans=%s\ttierName=%s" % (applicationName,businessTransactionName,tierName)

	#send(toRawData(timestamp,group,var,val,device,devtype,unit,name,source,other))
	send(toRawData(timeStamp,group,var+"averageResponseTime",averageResponseTime,"","",unit,"averageResponseTime",source,other))
	send(toRawData(timeStamp,group,var+"callsPerMinute",callsPerMinute,"","",unit,"callsPerMinute",source,other))
	send(toRawData(timeStamp,group,var+"totalCalls",totalCalls,"","",unit,"totalCalls",source,other))
	send(toRawData(timeStamp,group,var+"totalErrors",totalErrors,"","",unit,"totalErrors",source,other))
	send(toRawData(timeStamp,group,var+"errorsPerMinute",errorsPerMinute,"","",unit,"errorsPerMinute",source,other))
	send(toRawData(timeStamp,group,var+"errorPercentage",errorPercentage,"","",unit,"errorPercentage",source,other))
	send(toRawData(timeStamp,group,var+"slowCalls",slowCalls,"","",unit,"slowCalls",source,other))
	send(toRawData(timeStamp,group,var+"verySlowCalls",verySlowCalls,"","",unit,"verySlowCalls",source,other))
	send(toRawData(timeStamp,group,var+"stalls",stalls,"","",unit,"stalls",source,other))



###################################################
# NO NEED: will send to socket collector directly
###################################################

## Print the report to stdout.
#print etree.ProcessingInstruction('xml', 'version="1.0" encoding="UTF-8"')
#print etree.tostring(root, pretty_print=True, encoding='UTF-8')
#
## Print to file
#from xml.etree import ElementTree as ET
#with open(str(timestamper) + ".xml", "w") as f:
#	f.write(ET.tostring(root))
#	f.close()
