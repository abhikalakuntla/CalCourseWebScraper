from django.http import HttpResponse, HttpResponseRedirect
from django.core.management import call_command
from django.db import connection

import nltk
import urllib2
import requests

from berkeley.models import Class

# extractText extracts a block of text from the string
# Inputs: 	string - string to parse
#			stringStart - the starting string from which to begin extraction
#			stringEnd - the ending string with which to end extraction
#			includeStart - whether the returned string includes the stringStart
#			includeEnd - whether the returned string includes the stringEnd
def extractText(string, stringStart, stringEnd, includeStart = True, includeEnd = True):
	start = 0
	end = 0

	if(includeStart):
		start = string.index(stringStart)
	else:
		start = string.index(stringStart) + len(stringStart)

	if(includeEnd):
		end = start + string[start:].index(stringEnd) + len(stringEnd)
	else:
		end = start + string[start:].index(stringEnd)

	extractedText = string[start:end];

	return extractedText

# removeText removes a block of text from the string
# Inputs: 	string - string to parse
#			stringStart - the starting string from which to begin removal
#			stringEnd - the ending string with which to end removal
#			includeStart - whether the removed string includes the stringStart
#			includeEnd - whether the removed string includes the stringEnd
def removeText(string, stringStart, stringEnd, includeStart = True, includeEnd = True):
	start = 0
	end = 0

	if(includeStart):
		start = string.index(stringStart)
	else:
		start = string.index(stringStart) + len(stringStart)

	if(includeEnd):
		end = string.index(stringEnd) + len(stringEnd)
	else:
		end = string.index(stringEnd)

	string = string[0:start] + string[end:]

	return string

# scrapeBerkeley scrapes schedule.berkeley.edu to get data about classes
# Data extracted includes: CCN, course title, course department, course time and location, 
# course instructor, number of units, description and enrollment info
def scrape(request):
	# Clear the db
	cursor = connection.cursor()
	cursor.execute('DROP DATABASE scrapers')
	cursor.execute('CREATE DATABASE scrapers')
	cursor.execute('USE scrapers')
	
	# Create the tables in the database
	call_command('syncdb', interactive=True)

	# URL and page for a list of all the courses offered this fall
	url = "http://osoc.berkeley.edu/OSOC/osoc?p_term=FL&p_list_all=Y&p_print_flag=Y"
	page = urllib2.urlopen(url).read()
	
	# Remove the column titles
	courseRow = extractText(page, '<TR>', '</TR>')
	page = removeText(page, '<TR>', '</TR>')
	out = ''
	
	numDepartments = 152
	currentDepartment = 1

	# Go through all courses returned
	while(True):
	#for i in range(5):
		try:
			courseRow = extractText(page, '<TR>', '</TR>')
			page = removeText(page, '<TR>', '</TR>')
			courseDept = ''
			courseNumber = ''
			courseTitle = ''

			# Try to get the form variables (these don't exist in the department name rows, so they'll be skipped)
			try:
				formVars = extractText(courseRow, '$(', 'form.submit();')
				courseDept = extractText(formVars, "$('#p_dept').val('", "');", False, False)
				courseNumber = extractText(formVars, "$('#p_course').val('", "');\n$('#p_title')", False, False)
				courseTitle = extractText(formVars, "$('#p_title').val('", "');form.", False, False)
				print "Parsing " + courseDept + " " + courseNumber
			except:
				#print "Now parsing courses for department " + extractText(courseRow, '<B>', '</B>', False, False) + "..."
				currentDepartment = currentDepartment + 1
				print str(round((currentDepartment/float(numDepartments))*100, 2)) + r'% parsed'
				continue

			# This returns the page with all the lectures and sections for this class
			scheduleURL = 'http://osoc.berkeley.edu/OSOC/osoc'

			# Pass in the basic search data for this class 
			scheduleData = {
				'p_term':'FL',
				'p_dept':courseDept,
				'p_course':courseNumber,
				'p_title':courseTitle,
				'p_print_flag':'N',
				'p_list_all':'N'
			}

			# Get the search results (all the lectures, sections, labs etc. for a class)
			courseListPage = requests.post(scheduleURL, scheduleData)

			# Convert object to string for easy parsing
			classMeetings = courseListPage.text

			# Remove header
			classMeetings = removeText(classMeetings, '<TABLE', '</TABLE>')

			# [Testing] Create string to return
			classMeetingOutput = ''

			# Get the information for every meeting of the class
			while(True):
				try:
					# Extract the  class block
				 	classMeeting = extractText(classMeetings, '<TABLE', '</TABLE>') + "\n"

				 	# Remove left padding image
				 	classMeeting = removeText(classMeeting, '<TD', '</TD>')

				 	# Get the class header
				 	# There are two cases for a course header: a blue one for lectures and black for everything else.
				 	# So I try to get the blue one first and then try to get the black one if the blue one isn't found
				 	cHeader = ''
				 	if('COLOR="#000088' in classMeeting):
					 	# Extract the blue class header
					 	cHeader = extractText(
					 		classMeeting, 
					 		'Course:&#160;</B></FONT></TD><TD NOWRAP><FONT FACE="Helvetica, Arial, sans-serif" SIZE="2" COLOR="#000088"><B>', 
					 		'</B></FONT></TD></TR><FORM ACTION="/catalog/gcc_search_sends_request"',
					 		False, False
					 	).strip()
					else:
					 	# Extract the black class header
					 	cHeader = extractText(
					 		classMeeting, 
					 		'Course:&#160;</B></FONT></TD><TD NOWRAP><FONT FACE="Helvetica, Arial, sans-serif" SIZE="2"><B>', 
					 		'</B></FONT></TD></TR><FORM ACTION="/catalog/gcc_search_sends_request"',
					 		False, False
					 	).strip()
				 	# Parse the class header for the informaiton needed
				 	cHeaderList = cHeader.split()							# Split it into a list of strings
				 	cType = cHeaderList[-1]									# Get the type of class (LEC, DIS, LAB, etc.)
				 	cSecNum = cHeaderList[-2]								# Get the section number
				 	cFullDepartmentName = ' '.join(cHeaderList[:-4])		# Get the full department name
				 	
				 	# Get the class title
				 	cTitle = extractText(
				 		classMeeting,
				 		'Course Title:&#160;</B></FONT></TD><TD NOWRAP><TT><B><FONT FACE="Helvetica, Arial, sans-serif" CLASS="coursetitle"><B>',
				 		'&nbsp;<INPUT TYPE="submit" VALUE="(catalog description)"',
				 		False, False
				 	).strip()
				 	
				 	# Get the class time + location
				 	cTimeLoc = extractText(
				 		classMeeting,
				 		'Location:&#160;</B></FONT></TD><TD NOWRAP><TT>',
				 		'</TT></TD></TR><TR><TD ALIGN=RIGHT VALIGN=TOP NOWRAP>',
				 		False, False
				 	).strip()

				 	# Parse the time+location for information needed
				 	cTimeLocList = cTimeLoc.split(',')						# Split it into a list of 2 strings. First is time; second is location
				 	cLoc = cTimeLocList[1].strip()							# Get the location
				 	
				 	cTime = cTimeLocList[0].strip()							# Get the time string.
				 	cDayTimeList = cTime.split(' ')							# Split the time string into 2. First is days; second is time
				 	days = {'M':1, 'Tu':2, 'W':3, 'Th':4, 'F':5}			# Create a dict to translate from day values to day indeces
				 	cDays = []
				 	for day in days:
			 			if(day in cDayTimeList[0]):
			 				cDays.append(days[day])
				 		
				 	cTimeList = cDayTimeList[1].split('-')
				 	
				 	cStartTime = cTimeList[0]
				 	cStartHour = ''
				 	cStartMinutes = '00'
				 	if len(cStartTime) < 3:
				 		cStartHour = cStartTime
				 	else:
				 		cStartHour = cStartTime[:-2]
				 		cStartMinutes = cStartTime[-2:]

				 	cEndTime = cTimeList[1][:-1]
				 	cEndHour = ''
				 	cEndMinutes = '00'
				 	if len(cEndTime) < 3:
				 		cEndHour = cEndTime
				 	else:
				 		cEndHour = cEndTime[:-2]
				 		cEndMinutes = cEndTime[-2:]

				 	cEndPeriod = cTimeList[1][-1]
				 	cStartPeriod = cEndPeriod
				 	if (cEndPeriod == 'P' and int(cStartHour) > int(cEndHour)):
				 		cStartPeriod = 'P' if (cEndPeriod == 'A') else 'A'

				 	# Get the instructor name
				 	cInstructor = extractText(
				 		classMeeting,
				 		'Instructor:&#160;</B></FONT></TD><TD NOWRAP><TT>',
				 		'</TT></TD></TR><TR><TD ALIGN=RIGHT VALIGN=TOP NOWRAP>',
				 		False, False
				 	).strip()

				 	while(not cInstructor.find('&nbsp;') == -1):
				 		cInstructor = cInstructor.replace('&nbsp;', '')

				 	# Get the CCN (as integer)
				 	# The lecture's CCN is followed by a button to look at books. The others arent.
				 	cCCN = None
				 	try:
				 		# For leactures
					 	cCCN = extractText(
					 		classMeeting,
					 		'Course Control Number:&#160;</B></FONT></TD><TD NOWRAP><TT>',
					 		'<INPUT TYPE="submit" VALUE="View Books" class="button b bookbtn"/>',
					 		False, False
					 	).strip()
					except:
						# For discussions
						cCCN = extractText(
					 		classMeeting,
					 		'Course Control Number:&#160;</B></FONT></TD><TD NOWRAP><TT>',
					 		'</TT></TD></TR><TR><TD ALIGN=RIGHT VALIGN=TOP NOWRAP>',
					 		False, False
					 	).strip()

				 	# Get the number of units for the class
				 	# A meeting other than a lecture won't list a number of units, so this is set to None for those
				 	cUnits = None
				 	try:
					 	cUnits = int(extractText(
					 		classMeeting,
					 		'Units/Credit:&#160;</B></FONT></TD><TD NOWRAP><TT>',
					 		'</TT></TD></TR><TR><TD ALIGN=RIGHT VALIGN=TOP NOWRAP>',
					 		False, False
					 	).strip())
					except:
					 	pass

					cFinalExam = extractText(
						classMeeting,
						'Final Exam Group:&#160;</B></FONT></TD><TD NOWRAP><TT>',
						'</TT></TD></TR><TR><TD ALIGN=RIGHT VALIGN=TOP NOWRAP>',
						False, False
					).strip()

					while(not cFinalExam.find('&#160;') == -1):
				 		cFinalExam = cFinalExam.replace('&#160;', '')

				 	cNote = extractText(
				 		classMeeting,
				 		'Note:&#160;</B></FONT></TD><TD style="max-width: 900px;"><TT>',
				 		'&nbsp</TT></TD></TR><TR><TD ALIGN=RIGHT VALIGN=TOP NOWRAP>',
				 		False, False
				 	).strip()


				 	# Get the enrollment information
				 	cEnrollment = extractText(
				 		classMeeting,
				 		'Enrollment on 09/02/13:&#160;</B></FONT></TD><TD NOWRAP><TT>',
				 		'</TT></TD></TR><form action="https://telebears.berkeley.edu/enrollment-osoc/osc" method="post" target="_blank"/>',
				 		False, False
				 	).strip()

				 	# Separate the enrollment info into Limit, Enrolled, Waitlist and AvailibleSeats
				 	eLimit = int(extractText(cEnrollment, 'Limit:', ' Enrolled:', False, False).strip())
				 	eEnrolled = int(extractText(cEnrollment, 'Enrolled:', ' Waitlist:', False, False).strip())
				 	eWaitlist = int(extractText(cEnrollment, 'Waitlist:', ' Avail Seats', False, False).strip())
				 	eAvailibleSeats = int(cEnrollment[(cEnrollment.index('Avail Seats:') + len('Avail Seats:')):])

				 	# This returns the page with the description of the course
					courseDescriptionURL = 'http://osoc.berkeley.edu/catalog/gcc_search_sends_request'
					courseDescriptionData = {
						'p_dept_cd':courseDept, 
						'p_title':None, 
						'p_number':courseNumber
					}

					courseDescriptionPage = requests.post(courseDescriptionURL, courseDescriptionData).text

					cFullTitle = extractText(courseDescriptionPage, '<TD><FONT FACE="Verdana, Geneva, sans-serif" SIZE="2"><B>',  '&nbsp;--&nbsp;', False, False).strip()
					cDescription = extractText(courseDescriptionPage, '<TD><FONT SIZE="-1"><B>Description: </B>', '</FONT></TD>', False, False).strip()

				 	#out += "Department: " + cFullDepartmentName + "<br>Course: " + courseDept + " " + courseNumber + "<br>Section Number: " + cSecNum + "<br>Class Type: " + cType + "<br>Title: " + cFullTitle + "<br>Days of meeting: " + ','.join(str(x) for x in cDays) + "<br>Start Time: " + cStartHour + ":" + cStartMinutes + cStartPeriod + "<br>End Time: " + cEndHour + ":" + cEndMinutes + cEndPeriod + "<br>Instructor: " + cInstructor + "<br>CCN: " + cCCN +  "<br>Units: " + str(cUnits) + "<br>Enrollment: Limit: " + str(eLimit) + " Enrolled: " + str(eEnrolled) + " Waitlist: " + str(eWaitlist) + " Seats Availible: " + str(eAvailibleSeats) + "<br>"
				 	#out += cDescription + '<br><br>'

				 	c = Class.objects.create(
				 		ccn = cCCN,
				 		header = cHeader,
				 		deptCode = courseDept,
				 		deptName = cFullDepartmentName,
				 		courseNumber = courseNumber,
				 		secNum = cSecNum,
				 		type = cType,
				 		shortTitle = cTitle,
				 		longTitle = cFullTitle,
				 		location = cLoc,
				 		schedule_raw = cTime,
				 		meetingDays = ';'.join(str(x) for x in cDays),
				 		startHour = cStartHour,
				 		startMinutes = cStartMinutes,
				 		startPeriod = cStartPeriod,
				 		endHour = cEndHour,
				 		endMinutes = cEndMinutes,
				 		endPeriod = cEndPeriod,
				 		instructor = cInstructor,
				 		units = cUnits,
				 		note = cNote,
				 		finalExam_raw = cFinalExam,
				 		description = cDescription,
				 		enrollLimit = eLimit,
				 		enrollEnrolled = eEnrolled,
				 		enrollWaitlist = eWaitlist,
				 		enrollAvailible = eAvailibleSeats
				 	)

				 	classMeetings = removeText(classMeetings, '<TABLE', '</TABLE>')
				 	classMeetingOutput += classMeeting + "\n"
				except:
				 	break		
		except:
			break

	return HttpResponse('Berkeley Scraped')