#-------------------------------------------------------------------------------
# Name:        Extract CLUs by AOI
# Purpose:
#
# Author: Adolfo.Diaz
#         GIS Specialist
#         National Soil Survey Center
#         USDA - NRCS
# e-mail: adolfo.diaz@usda.gov
# phone: 608.662.4422 ext. 216
#
# Created:     02/27/2020

# ==========================================================================================
# Modified 3/8/2020
# Error Regenerating ArcGIS Token -- submitFSquery function
# The error was occuring in parsing the incoming URLencoded query string into a python
# dictionary using the urllib.parse.parse_qs(INparams) command, which parses a query
# string given as a string argument (data of type application/x-www-form-urlencoded). The
# data are returned as a dictionary. The problem is that the items in the dictionary are
# returned in lists i.e. [('f', ['json']),('token',['U62uXB9Qcd1xjyX1)] and when the
# dictionary is updated and re-urlencoded again the lists mess things up.
# Instead, the urllib.parse.parse_qsl command was used to output a list after which the
# list gets converted to a dicationary.

# ==========================================================================================
# Modified 3/11/2020
# The createListOfJSONextents() subfunction was updated to subdivide the incoming
# feature class instead of a bounding box.  This slightly reduced the # of requests.
# Also, all intermediate files are done "IN_MEMORY" instead of written out.
# Added a failedRequests dictionary to re-request failed extents.

# ==========================================================================================
# Modified 3/12/2020
# Switched the geometry type in the REST request from esriGeometryPolygon to esriGeometryPolygon.
# This potentially reduces the total number of requests to the server and reduces the
# processing time b/c bounding boxes (envelopes) will encompass broader areas and more CLUs.

# ==========================================================================================
# Modified 3/20/2020
# Added functionality so that this script can be used in both ArcMap and ArcPro.
# Specifically, the following modifications were made:
#     1) duplicated the 'createListOfJSONextents' function and made one specifically for
#        ArcMap b/c the 'SubdividePolygon' function is only available in ArcPro.  The only
#        equivalent ArcMap function was creating a fishnet of 2 areas and then intersecting
#        the results to remove unwanted areas.
#     2) URL requests are handled differently in python 2.7 vs. python 3.6.  In order to
#        handle differences a boolean was created to discern between which product was
#        being used using the arcpy.GetInstallInfo()['ProductName'] funciton.  In short,
#        python 3.6 uses the urllib library while python 2.7 uses the urllib2 library.
#     3) Added code to add the final layer to ArcGIS or ArcPro depending on where the tool
#        was invoked from.

# ==========================================================================================
# Modified 3/24/2020
# - There was an error in codeBlock that feeds the calculate field tool that ArcMap was
#   throwing.  Error 009989 and 00999 were thrown.  However, when I manually entered them
#   in the calculate field tool it works.  Instead of using the calculate field tool I
#   used an insertCursor.
# - Used the random function to arbitrarily append a unique number to the features that
#   that are continously being subdivided b/c CLU count exceeds limit.
# - changed count = submitFSquery(RESTurl,params)['count'] to
#   countQuery = submitFSquery(RESTurl,params) bc/ when the submitFSquery() would return
#   false the script would throw the error: 'bool' object has no attribute '__getitem__'
# - Added a 2nd request attempt to the submitFSquery() function.
# - Added a 2nd request attempt to the createListOfJSONextents() functions
# - used randint() instead of random() b/c it returns a long vs float and strings cannot
#   begin with a zero.

# ==========================================================================================
# Modified 3/25/2020
# - ArcMap was erroring out b/c the dataframe coordinate system was set different than
#   AOI input.  This directly impacted the fishnet command b/c of the extents (xim, ymin)
#   generated.  They were based on the coord system of the data frame vs. layer.
#   Introduced code to temporarily change the coord system of the data frame to the AOI.

#-------------------------------------------------------------------------------

## ==============================================================================================================================
def AddMsgAndPrint(msg, severity=0):
    # prints message to screen if run as a python script
    # Adds tool message to the geoprocessor
    #
    #Split the message on \n first, so that if it's multiple lines, a GPMessage will be added for each line
    try:

        #print(msg)
        #for string in msg.split('\n'):
            #Add a geoprocessing message (in case this is run as a tool)
        if severity == 0:
            arcpy.AddMessage(msg)

        elif severity == 1:
            arcpy.AddWarning(msg)

        elif severity == 2:
            arcpy.AddError("\n" + msg)

    except:
        pass

## ==============================================================================================================================
def errorMsg():
    try:

        exc_type, exc_value, exc_traceback = sys.exc_info()
        theMsg = "\t" + traceback.format_exception(exc_type, exc_value, exc_traceback)[1] + "\n\t" + traceback.format_exception(exc_type, exc_value, exc_traceback)[-1]

        if theMsg.find("exit") > -1:
            AddMsgAndPrint("\n\n")
            pass
        else:
            AddMsgAndPrint(theMsg,2)

    except:
        AddMsgAndPrint("Unhandled error in unHandledException method", 2)
        pass

## ===================================================================================
def setScratchWorkspace():
    """ This function will set the scratchWorkspace for the interim of the execution
        of this tool.  The scratchWorkspace is used to set the scratchGDB which is
        where all of the temporary files will be written to.  The path of the user-defined
        scratchWorkspace will be compared to existing paths from the user's system
        variables.  If there is any overlap in directories the scratchWorkspace will
        be set to C:\TEMP, assuming C:\ is the system drive.  If all else fails then
        the packageWorkspace Environment will be set as the scratchWorkspace. This
        function returns the scratchGDB environment which is set upon setting the scratchWorkspace"""

    try:
        AddMsgAndPrint("\nSetting Scratch Workspace")
        scratchWK = arcpy.env.scratchWorkspace

        # -----------------------------------------------
        # Scratch Workspace is defined by user or default is set
        if scratchWK is not None:

            # dictionary of system environmental variables
            envVariables = os.environ

            # get the root system drive i.e C:
            if envVariables.has_key('SYSTEMDRIVE'):
                sysDrive = envVariables['SYSTEMDRIVE']
            else:
                sysDrive = None

            varsToSearch = ['ESRI_OS_DATADIR_LOCAL_DONOTUSE','ESRI_OS_DIR_DONOTUSE','ESRI_OS_DATADIR_MYDOCUMENTS_DONOTUSE',
                            'ESRI_OS_DATADIR_ROAMING_DONOTUSE','TEMP','LOCALAPPDATA','PROGRAMW6432','COMMONPROGRAMFILES','APPDATA',
                            'USERPROFILE','PUBLIC','SYSTEMROOT','PROGRAMFILES','COMMONPROGRAMFILES(X86)','ALLUSERSPROFILE']

##            """ This is a printout of my system environmmental variables - Windows 7
##            -----------------------------------------------------------------------------------------
##            ESRI_OS_DATADIR_LOCAL_DONOTUSE C:\Users\adolfo.diaz\AppData\Local\
##            ESRI_OS_DIR_DONOTUSE C:\Users\ADOLFO~1.DIA\AppData\Local\Temp\6\arc3765\
##            ESRI_OS_DATADIR_MYDOCUMENTS_DONOTUSE C:\Users\adolfo.diaz\Documents\
##            ESRI_OS_DATADIR_COMMON_DONOTUSE C:\ProgramData\
##            ESRI_OS_DATADIR_ROAMING_DONOTUSE C:\Users\adolfo.diaz\AppData\Roaming\
##            TEMP C:\Users\ADOLFO~1.DIA\AppData\Local\Temp\6\arc3765\
##            LOCALAPPDATA C:\Users\adolfo.diaz\AppData\Local
##            PROGRAMW6432 C:\Program Files
##            COMMONPROGRAMFILES :  C:\Program Files (x86)\Common Files
##            APPDATA C:\Users\adolfo.diaz\AppData\Roaming
##            USERPROFILE C:\Users\adolfo.diaz
##            PUBLIC C:\Users\Public
##            SYSTEMROOT :  C:\Windows
##            PROGRAMFILES :  C:\Program Files (x86)
##            COMMONPROGRAMFILES(X86) :  C:\Program Files (x86)\Common Files
##            ALLUSERSPROFILE :  C:\ProgramData """
##            """------------------------------------------------------------------------------------------"""

            bSetTempWorkSpace = False

            """ Iterate through each Environmental variable; If the variable is within the 'varsToSearch' list
                above then check their value against the user-set scratch workspace.  If they have anything
                in common then switch the workspace to something local  """
            for var in envVariables:

                if not var in varsToSearch:
                    continue

                # make a list from the scratch and environmental paths
                varValueList = (envVariables[var].lower()).split(os.sep)          # ['C:', 'Users', 'adolfo.diaz', 'AppData', 'Local']
                scratchWSList = (scratchWK.lower()).split(os.sep)                 # [u'C:', u'Users', u'adolfo.diaz', u'Documents', u'ArcGIS', u'Default.gdb', u'']

                # remove any blanks items from lists
                if '' in varValueList: varValueList.remove('')
                if '' in scratchWSList: scratchWSList.remove('')

                # First element is the drive letter; remove it if they are
                # the same otherwise review the next variable.
                if varValueList[0] == scratchWSList[0]:
                    scratchWSList.remove(scratchWSList[0])
                    varValueList.remove(varValueList[0])

                # obtain a similarity ratio between the 2 lists above
                #sM = SequenceMatcher(None,varValueList,scratchWSList)

                # Compare the values of 2 lists; order is significant
                common = [i for i, j in zip(varValueList, scratchWSList) if i == j]

                if len(common) > 0:
                    bSetTempWorkSpace = True
                    break

            # The current scratch workspace shares 1 or more directory paths with the
            # system env variables.  Create a temp folder at root
            if bSetTempWorkSpace:
                AddMsgAndPrint("\tCurrent Workspace: " + scratchWK,0)

                if sysDrive:
                    tempFolder = sysDrive + os.sep + "TEMP"

                    if not os.path.exists(tempFolder):
                        os.makedirs(tempFolder,mode=777)

                    arcpy.env.scratchWorkspace = tempFolder
                    AddMsgAndPrint("\tTemporarily setting scratch workspace to: " + arcpy.env.scratchGDB,1)

                else:
                    packageWS = [f for f in arcpy.ListEnvironments() if f=='packageWorkspace']
                    if arcpy.env[packageWS[0]]:
                        arcpy.env.scratchWorkspace = arcpy.env[packageWS[0]]
                        AddMsgAndPrint("\tTemporarily setting scratch workspace to: " + arcpy.env.scratchGDB,1)
                    else:
                        AddMsgAndPrint("\tCould not set any scratch workspace",2)
                        return False

            # user-set workspace does not violate system paths; Check for read/write
            # permissions; if write permissions are denied then set workspace to TEMP folder
            else:
                arcpy.env.scratchWorkspace = scratchWK

                if arcpy.env.scratchGDB == None:
                    AddMsgAndPrint("\tCurrent scratch workspace: " + scratchWK + " is READ only!",0)

                    if sysDrive:
                        tempFolder = sysDrive + os.sep + "TEMP"

                        if not os.path.exists(tempFolder):
                            os.makedirs(tempFolder,mode=777)

                        arcpy.env.scratchWorkspace = tempFolder
                        AddMsgAndPrint("\tTemporarily setting scratch workspace to: " + arcpy.env.scratchGDB,1)

                    else:
                        packageWS = [f for f in arcpy.ListEnvironments() if f=='packageWorkspace']
                        if arcpy.env[packageWS[0]]:
                            arcpy.env.scratchWorkspace = arcpy.env[packageWS[0]]
                            AddMsgAndPrint("\tTemporarily setting scratch workspace to: " + arcpy.env.scratchGDB,1)

                        else:
                            AddMsgAndPrint("\tCould not set any scratch workspace",2)
                            return False

                else:
                    AddMsgAndPrint("\tUser-defined scratch workspace is set to: "  + arcpy.env.scratchGDB,0)

        # No workspace set (Very odd that it would go in here unless running directly from python)
        else:
            AddMsgAndPrint("\tNo user-defined scratch workspace ",0)
            sysDrive = os.environ['SYSTEMDRIVE']

            if sysDrive:
                tempFolder = sysDrive + os.sep + "TEMP"

                if not os.path.exists(tempFolder):
                    os.makedirs(tempFolder,mode=777)

                arcpy.env.scratchWorkspace = tempFolder
                AddMsgAndPrint("\tTemporarily setting scratch workspace to: " + arcpy.env.scratchGDB,1)

            else:
                packageWS = [f for f in arcpy.ListEnvironments() if f=='packageWorkspace']
                if arcpy.env[packageWS[0]]:
                    arcpy.env.scratchWorkspace = arcpy.env[packageWS[0]]
                    AddMsgAndPrint("\tTemporarily setting scratch workspace to: " + arcpy.env.scratchGDB,1)

                else:
                    AddMsgAndPrint("\tCould not set scratchWorkspace. Not even to default!",2)
                    return False

        #arcpy.Compact_management(arcpy.env.scratchGDB)
        return arcpy.env.scratchGDB

    except:

        # All Failed; set workspace to packageWorkspace environment
        try:
            packageWS = [f for f in arcpy.ListEnvironments() if f=='packageWorkspace']
            if arcpy.env[packageWS[0]]:
                arcpy.env.scratchWorkspace = arcpy.env[packageWS[0]]
                arcpy.Compact_management(arcpy.env.scratchGDB)
                return arcpy.env.scratchGDB
            else:
                AddMsgAndPrint("\tCould not set scratchWorkspace. Not even to default!",2)
                return False
        except:
            errorMsg()
            return False

## ===================================================================================
def splitThousands(someNumber):
    """will determine where to put a thousands seperator if one is needed. Input is
       an integer.  Integer with or without thousands seperator is returned."""

    try:
        return re.sub(r'(\d{3})(?=\d)', r'\1,', str(someNumber)[::-1])[::-1]

    except:
        errorMsg()
        return someNumber

## ===================================================================================
def getPortalTokenInfo(portalURL):

    try:

        # Returns the URL of the active Portal
        # i.e. 'https://gis.sc.egov.usda.gov/portal/'
        activePortal = arcpy.GetActivePortalURL()

        # {'SSL_enabled': False, 'portal_version': 6.1, 'role': '', 'organization': '', 'organization_type': ''}
        #portalInfo = arcpy.GetPortalInfo(activePortal)

        # targeted portal is NOT set as default
        if activePortal != portalURL:

               # List of managed portals
               managedPortals = arcpy.ListPortalURLs()

               # portalURL is available in managed list
               if activePortal in managedPortals:
                   AddMsgAndPrint("\nYour Active portal is set to: " + activePortal,2)
                   AddMsgAndPrint("Set your active portal and sign into: " + portalURL,2)
                   return False

               # portalURL must first be added to list of managed portals
               else:
                    AddMsgAndPrint("\nYou must add " + portalURL + " to your list of managed portals",2)
                    AddMsgAndPrint("Open the Portals Tab to manage portal connections",2)
                    AddMsgAndPrint("For more information visit the following ArcGIS Pro documentation:",2)
                    AddMsgAndPrint("https://pro.arcgis.com/en/pro-app/help/projects/manage-portal-connections-from-arcgis-pro.htm",1)
                    return False

        # targeted Portal is correct; try to generate token
        else:

            # Get Token information
            tokenInfo = arcpy.GetSigninToken()

            # Not signed in.  Token results are empty
            if not tokenInfo:
                AddMsgAndPrint("\nYou are not signed into: " + portalURL,2)
                return False

            # Token generated successfully
            else:
                return tokenInfo

    except:
        errorMsg()
        return False

## ===================================================================================
def submitFSquery(url,INparams):
    """ This function will send a spatial query to a web feature service and convert
        the results into a python structure.  If the results from the service is an
        error due to an invalid token then a second attempt will be sent with using
        a newly generated arcgis token.  If the token is good but the request returned
        with an error a second attempt will be made.  The funciion takes in 2 parameters,
        the URL to the web service and a query string in URLencoded format.

        Error produced with invalid token
        {u'error': {u'code': 498, u'details': [], u'message': u'Invalid Token'}}

        The function returns requested data via a python dictionary"""

    try:
        # Python 3.6 - ArcPro
        # Data should be in bytes; new in Python 3.6
        if bArcGISPro:
            INparams = INparams.encode('ascii')
            resp = urllib.request.urlopen(url,INparams)  # A failure here will probably throw an HTTP exception
        # Python 2.7 - ArcMap
        else:
            req = urllib2.Request(url,INparams)
            resp = urllib2.urlopen(req)

        responseStatus = resp.getcode()
        responseMsg = resp.msg
        jsonString = resp.read()

        # json --> Python; dictionary containing 1 key with a list of lists
        results = json.loads(jsonString)

        # Check for expired token; Update if expired and try again
        if 'error' in results.keys():
           if results['error']['message'] == 'Invalid Token':
               AddMsgAndPrint("\tRegenerating ArcGIS Token Information")

               # Get new ArcPro Token
               newToken = arcpy.GetSigninToken()

               # Update the original portalToken
               global portalToken
               portalToken = newToken

               # convert encoded string into python structure and update token
               # by parsing the encoded query strting into list of (name, value pairs)
               # i.e [('f', 'json'),('token','U62uXB9Qcd1xjyX1)]
               # convert to dictionary and update the token in dictionary

               queryString = parseQueryString(params)

               requestDict = dict(queryString)
               requestDict.update(token=newToken['token'])

               newParams = urllibEncode(requestDict)

               if bArcGISPro:
                   newParams = newParams.encode('ascii')

               # update incoming parameters just in case a 2nd attempt is needed
               INparams = newParams

               # Python 3.6 - ArcPro
               if bArcGISPro:
                   resp = urllib.request.urlopen(url,newParams)  # A failure here will probably throw an HTTP exception
               else:
                   req = urllib2.Request(url,newParams)
                   resp = urllib2.urlopen(req)

               responseStatus = resp.getcode()
               responseMsg = resp.msg
               jsonString = resp.read()

               results = json.loads(jsonString)

        # Check results before returning them; Attempt a 2nd request if results are bad.
        if 'error' in results.keys() or len(results) == 0:
            time.sleep(5)

            if bArcGISPro:
                resp = urllib.request.urlopen(url,INparams)  # A failure here will probably throw an HTTP exception
            else:
                req = urllib2.Request(url,INparams)
                resp = urllib2.urlopen(req)

            responseStatus = resp.getcode()
            responseMsg = resp.msg
            jsonString = resp.read()

            results = json.loads(jsonString)

            if 'error' in results.keys() or len(results) == 0:
                AddMsgAndPrint("\t2nd Request Attempt Failed - Error Code: " + str(responseStatus) + " -- " + responseMsg + " -- " + str(results),2)
                return False
            else:
                return results

        else:
             return results

    except httpErrors as e:

        if int(e.code) >= 500:
           #AddMsgAndPrint("\n\t\tHTTP ERROR: " + str(e.code) + " ----- Server side error. Probably exceed JSON imposed limit",2)
           #AddMsgAndPrint("t\t" + str(request))
           pass
        elif int(e.code) >= 400:
           #AddMsgAndPrint("\n\t\tHTTP ERROR: " + str(e.code) + " ----- Client side error. Check the following SDA Query for errors:",2)
           #AddMsgAndPrint("\t\t" + getGeometryQuery)
           pass
        else:
           AddMsgAndPrint('HTTP ERROR = ' + str(e.code),2)

    except:
        errorMsg()
        return False

## ===================================================================================
def createListOfJSONextents(inFC,RESTurl):
    """ This function will deconstruct the input FC into JSON format and determine if the
        clu count within this extent exceeds the max record limit of the WFS.  If the clu
        count exceeds the WFS limit then the incoming FC will continously be split
        until the CLU count is below WFS limit.  Each split will be an individual request
        to the WFS. Splits are done by using the subdivide polygon tool.

        The function will return a dictionary of JSON extents created from the individual
        splits of the original fc bounding box along with a CLU count for the request
        {'Min_BND': ['{"xmin":-90.1179,
                       "ymin":37.0066,
                       "xmax":-89.958,
                       "ymax":37.174,
                       "spatialReference":{"wkid":4326,"latestWkid":4326}}', 998]}

        Return False if jsonDict is empty"""

    try:
        # Dictionary containing JSON Extents to submit for geometry
        jsonDict = dict()

        # create JSON extent to send to REST URL to determine if
        # records requested exceed max allowable records.
        #jSONextent  = arcpy.da.Describe(inFC)['extent'].JSON

        # deconstructed AOI geometry in JSON
        jSONpolygon = [row[0] for row in arcpy.da.SearchCursor(inFC, ['SHAPE@JSON'])][0]

        params = urllibEncode({'f': 'json',
                               'geometry':jSONpolygon,
                               'geometryType':'esriGeometryPolygon',
                               'returnCountOnly':'true',
                               'token': portalToken['token']})

        # Get geometry count of incoming fc
        countQuery = submitFSquery(RESTurl,params)

        if not countQuery:
           AddMsgAndPrint("Failed to get estimate of CLU count",2)
           return False

        AddMsgAndPrint("\nThere are approximately " + splitThousands(countQuery['count']) + " CLUs within AOI")

        # if count is within max records allowed no need to proceed
        if countQuery['count'] <= maxRecordCount:
            jsonDict[os.path.basename(inFC)] = [jSONpolygon,countQuery['count']]

        # AOI bounding box will have to be continously split until polygons capture
        # CLU records below 1000 records.
        else:
            AddMsgAndPrint("Determining # of WFS requests")

            numOfAreas = int(countQuery['count'] / 800)  # How many times the input fc will be subdivided initially
            splitNum = 0               # arbitrary number to keep track of unique files
            subDividedFCList = list()  # list containing recycled fcs to be split
            subDividedFCList.append(inFC)

            # iterate through each polygon in fc in list and d
            for fc in subDividedFCList:
                arcpy.SetProgressorLabel("Determining # of WFS requests. Current #: " + str(len(jsonDict)))

                # Subdivide fc into 2
                subdivision_fc = "in_memory" + os.sep + os.path.basename(arcpy.CreateScratchName("subdivision",data_type="FeatureClass",workspace=scratchWS))

                if splitNum > 0:
                   numOfAreas = 2

                arcpy.SubdividePolygon_management(fc,subdivision_fc,"NUMBER_OF_EQUAL_PARTS",numOfAreas, "", "", "", "STACKED_BLOCKS")

                # first iteration will be the input AOI; don't wnat to delete it
                if splitNum > 0:
                   arcpy.Delete_management(fc)

                # Add new fld to capture unique name used for the split tool to create
                newOIDfld = "objectID_TEXT"
                expression = "assignUniqueNumber(!" + arcpy.Describe(subdivision_fc).OIDFieldName + "!)"
                randomNum = str(random.randint(1,9999999999))

                # code block doesn't like indentations
                codeBlock = """
def assignUniqueNumber(oid):
    return \"request_\" + str(""" + str(randomNum) + """) + str(oid)"""

                if not len(arcpy.ListFields(subdivision_fc,newOIDfld)) > 0:
                    arcpy.AddField_management(subdivision_fc,newOIDfld,"TEXT","#","#","30")

                arcpy.CalculateField_management(subdivision_fc,newOIDfld,expression,"PYTHON3",codeBlock)
                splitNum+=1

                # Create a fc for each subdivided polygon
                # split by attributes was faster by 2 secs than split_analysis
                arcpy.SplitByAttributes_analysis(subdivision_fc,"IN_MEMORY",[newOIDfld])
                arcpy.Delete_management(subdivision_fc)

                # Create a list of fcs that the split tool outputs
                #arcpy.env.workspace = scratchWS
                arcpy.env.workspace = "IN_MEMORY"
                #splitFCList = arcpy.ListFeatureClasses('request_' + str(splitNum) + '*')
                splitFCList = arcpy.ListFeatureClasses('request_' + randomNum + '*')

                # Assess each split FC to determine if it
                for splitFC in splitFCList:

                    splitFC = arcpy.da.Describe(splitFC)['catalogPath']
                    arcpy.SetProgressorLabel("Determining # of WFS requests. Current #: " + str(len(jsonDict)))

                    #splitExtent = arcpy.da.Describe(splitFC)['extent'].JSON
                    splitExtent = [row[0] for row in arcpy.da.SearchCursor(splitFC, ['SHAPE@JSON'])][0]

                    params = urllibEncode({'f': 'json',
                                           'geometry':splitExtent,
                                           'geometryType':'esriGeometryPolygon',
                                           'returnCountOnly':'true',
                                           'token': portalToken['token']})

                    # Send geometry count request
                    countQuery = submitFSquery(RESTurl,params)

                    # request failed.....try once more
                    if not countQuery:
                        time.sleep(5)
                        countQuery = submitFSquery(RESTurl,params)

                        if not countQuery:
                           AddMsgAndPrint("\tFailed to get count request -- 3 attempts made -- Recycling request")
                           subDividedFCList.append(splitFC)
                           continue

                    # if count is within max records allowed add it dict
                    if countQuery['count'] <= maxRecordCount:
                        jsonDict[os.path.basename(splitFC)] = [splitExtent,countQuery['count']]

                        #arcpy.CopyFeatures_management(splitFC,scratchWS + os.sep + arcpy.da.Describe(splitFC)['baseName'])
                        arcpy.Delete_management(splitFC)

                    # recycle this fc back to be split into 2 polygons
                    else:
                        subDividedFCList.append(splitFC)

        if len(jsonDict) < 1:
            AddMsgAndPrint("\tCould not determine number of server requests.  Exiting",2)
            return False
        else:
            AddMsgAndPrint("\t" + splitThousands(len(jsonDict)) + " server requests are needed")
            return jsonDict

    except:
        errorMsg()
        return False

## ===================================================================================
def createListOfJSONextents_ArcMap(inFC,RESTurl):
    """ This function will deconstruct the input FC into JSON format and determine if the
        clu count within this extent exceeds the max record limit of the WFS.  If the clu
        count exceeds the WFS limit then the incoming FC will continously be split
        until the CLU count is below WFS limit.  Each split will be an individual request
        to the WFS.  Splits are done by creating a fishnet of the fc and then intersecting
        the output with the original fc.

        The function will return a dictionary of JSON extents created from the individual
        splits of the original fc bounding box along with a CLU count for the request
        {'Min_BND': ['{"xmin":-90.1179,
                       "ymin":37.0066,
                       "xmax":-89.958,
                       "ymax":37.174,
                       "spatialReference":{"wkid":4326,"latestWkid":4326}}', 998]}

        Return False if jsonDict is empty"""

    try:
        # Dictionary containing JSON Extents to submit for geometry
        jsonDict = dict()

        # create JSON extent to send to REST URL to determine if
        # records requested exceed max allowable records.
        #jSONextent  = arcpy.da.Describe(inFC)['extent'].JSON

        # deconstructed AOI geometry in JSON
        jSONpolygon = [row[0] for row in arcpy.da.SearchCursor(inFC, ['SHAPE@JSON'])][0]

        params = urllibEncode({'f': 'json',
                               'geometry':jSONpolygon,
                               'geometryType':'esriGeometryPolygon',
                               'returnCountOnly':'true',
                               'token': portalToken['token']})

        # Get geometry count of incoming fc
        countQuery = submitFSquery(RESTurl,params)

        if not countQuery:
           AddMsgAndPrint("Failed to get estimate of CLU count",2)
           return False

        AddMsgAndPrint("\nThere are approximately " + splitThousands(countQuery['count']) + " CLUs within AOI")

        # if count is within max records allowed no need to proceed
        if countQuery['count'] <= maxRecordCount:
            jsonDict[os.path.basename(inFC)] = [jSONpolygon,countQuery['count']]

        # AOI bounding box will have to be continously split until polygons capture
        # CLU records below 1000 records.
        else:
            AddMsgAndPrint("Determining # of WFS requests")
            fishNetAreas = int(countQuery['count'] / 800)  # How many times the input fc will be subdivided initially
            splitNum = 0               # arbitrary number to keep track of unique files
            subDividedFCList = list()  # list containing recycled fcs to be split
            subDividedFCList.append(inFC)
            bSpatialRefUpdate = False

            # make sure arcmap coord system is the same as the AOI
            # If not set it AOI spatial reference.
            # This is needed for creating the fishnet
            try:
                mxd = arcpy.mapping.MapDocument("CURRENT")
                df = arcpy.mapping.ListDataFrames(mxd)[0]
                dfSpatialRefObject = df.spatialReference

                if dfSpatialRefObject.name != AOIspatialRef.name:
                   df.spatialReference = AOIspatialRef
                   bSpatialRefUpdate = True
                   AddMsgAndPrint("\n\tTemporarily setting Arcmap coord system to: " + AOIspatialRef.name)
            except:
                pass


            # iterate through each polygon in fc in list and d
            for fc in subDividedFCList:
                arcpy.SetProgressorLabel("Determining # of WFS requests. Current #: " + str(len(jsonDict)))

                # ---------------------------------- Create a fishnet of 2 areas
                fishnet_fc = "in_memory" + os.sep + os.path.basename(arcpy.CreateScratchName("fishnet",data_type="FeatureClass",workspace=scratchWS))
                intersectOut =  "in_memory" + os.sep + os.path.basename(arcpy.CreateScratchName("fishnet_int",data_type="FeatureClass",workspace=scratchWS))
                #fishnet_fc = arcpy.CreateScratchName("fishnet",data_type="FeatureClass",workspace=scratchWS)
                #intersectOut =  arcpy.CreateScratchName("fishnet_int",data_type="FeatureClass",workspace=scratchWS)

                ext = arcpy.Describe(fc).extent
                xmin = ext.XMin
                xmax = ext.XMax
                ymin = ext.YMin
                ymax = ext.YMax
                originCoordinate = str(xmin) + " " + str(ymin)
                yAxisCoordinate =  str(xmin) + " " + str(ymin + .25)
                oppositeCorner = str(xmax) + " " + str(ymax)
                cellWidth = 0; cellHeight = 0

                # Determine whether to shape is taller vs wider
                xDifference = xmax - xmin
                yDifference = ymax - ymin

                # geometry is wider - split vertically
                if xDifference > yDifference:
                    if splitNum > 0:
                        numOfRows = 2
                    else:
                        numOfRows = fishNetAreas
                    numOfColumns = 1
                # geometry is taller - split horizontally
                else:
                    if splitNum > 0:
                        numOfColumns = 2
                    else:
                        numOfColumns = fishNetAreas
                    numOfRows = 1

                # create fish net
                arcpy.CreateFishnet_management(fishnet_fc,originCoordinate,yAxisCoordinate,cellWidth,cellHeight,
                                               numOfRows,numOfColumns,oppositeCorner,"NO_LABELS",'#',"POLYGON")

                # intersect fc and fishnet to remove unwanted areas
                arcpy.Intersect_analysis([fishnet_fc,fc],intersectOut,"ONLY_FID","","INPUT")
                arcpy.Delete_management(fishnet_fc)

                # first iteration will be the input AOI; don't wnat to delete it
                if splitNum > 0:
                   arcpy.Delete_management(fc)

                # Add new fld to capture unique name used for the split tool to create
                newOIDfld = "objectID_TEXT"
                #expression = "assignUniqueNumber(!" + arcpy.Describe(intersectOut).OIDFieldName + "!)"

                # Generate a unique name to populate 'objectID_TEXT' field
                #randomNum = str(splitNum) + str(random())[2:7]

                # code block doesn't like indentations
##                codeBlock = """
##def assignUniqueNumber(oid):
##    return \"request_\" + str(""" + str(randomNum) + """) + str(oid)"""

                #codeBlock = "def assignUniqueNumber():\\n    return \"request_\" + str(" + str(randomNum) + ")"

                if not len(arcpy.ListFields(intersectOut,newOIDfld)) > 0:
                    arcpy.AddField_management(intersectOut,newOIDfld,"TEXT","#","#","30")

                #arcpy.CalculateField_management(intersectOut,newOIDfld,expression,"PYTHON_9.3",codeBlock)

                randomNum = str(random.randint(1,9999999999))
                with arcpy.da.UpdateCursor(intersectOut, ["OID@",newOIDfld]) as cursor:
                    for row in cursor:
                        # each feature will be uniquely named - i.e. request_4893871
                        row[1] = "request_" + randomNum + str(row[0])
                        cursor.updateRow(row)

                del cursor
                splitNum+=1

                # Create a fc for each subdivided polygon
                # split by attributes was faster by 2 secs than split_analysis
                arcpy.SplitByAttributes_analysis(intersectOut,"IN_MEMORY",[newOIDfld])
                arcpy.Delete_management(intersectOut)

                # Create a list of fcs that the split tool outputs
                #arcpy.env.workspace = scratchWS

                arcpy.env.workspace = "IN_MEMORY"
                splitFCList = arcpy.ListFeatureClasses('request_' + randomNum + '*')

                # Assess each split FC to determine if it
                for splitFC in splitFCList:

                    splitFC = arcpy.Describe(splitFC).catalogPath
                    arcpy.SetProgressorLabel("Determining # of WFS requests. Current #: " + str(len(jsonDict)))

                    splitExtent = [row[0] for row in arcpy.da.SearchCursor(splitFC, ['SHAPE@JSON'])][0]

                    params = urllibEncode({'f': 'json',
                                           'geometry':splitExtent,
                                           'geometryType':'esriGeometryPolygon',
                                           'returnCountOnly':'true',
                                           'token': portalToken['token']})

                    # Send geometry count request
                    countQuery = submitFSquery(RESTurl,params)

                    # request failed.....try once more
                    if not countQuery:
                        time.sleep(5)
                        countQuery = submitFSquery(RESTurl,params)

                        if not countQuery:
                           AddMsgAndPrint("\tFailed to get count request -- 3 attempts made -- Recycling request")
                           subDividedFCList.append(splitFC)
                           continue

                    # if count is within max records allowed add it dict
                    if countQuery['count'] <= maxRecordCount:
                        jsonDict[os.path.basename(splitFC)] = [splitExtent,countQuery['count']]

                        #arcpy.CopyFeatures_management(splitFC,scratchWS + os.sep + arcpy.da.Describe(splitFC)['baseName'])
                        arcpy.Delete_management(splitFC)

                    # recycle this fc back to be split into 2 polygons
                    else:
                        subDividedFCList.append(splitFC)

        # Reset data frame back to original spatial reference
        if bSpatialRefUpdate:
           df.spatialReference = dfSpatialRefObject

        if len(jsonDict) < 1:
            AddMsgAndPrint("\tCould not determine number of server requests.  Exiting",2)
            return False
        else:
            AddMsgAndPrint("\t" + splitThousands(len(jsonDict)) + " server requests are needed\n")
            return jsonDict

    except:
        errorMsg()
        return False


## ===================================================================================
def createOutputFC(metadata,outputWS,shape="POLYGON"):
    """ This function will create an empty polygon feature class within the outputWS
        The feature class will be set to the same spatial reference as the Web Feature
        Service. All fields part of the WFS will also be added to the new feature class.
        A field dictionary containing the field names and their property will also be
        returned.  This fieldDict will be used to create the fields in the CLU fc and
        by the getCLUgeometry insertCursor.

        fieldDict ={field:(fieldType,fieldLength,alias)
        i.e {'clu_identifier': ('TEXT', 36, 'clu_identifier'),'clu_number': ('TEXT', 7, 'clu_number')}

        Return the field dictionary and new feature class including the path
        Return False if error ocurred."""

    try:
        AddMsgAndPrint("\nCreating New Feature Class: " + "CLU_" + os.path.basename(AOI))
        arcpy.SetProgressorLabel("Creating New Feature Class: " + "CLU_" + os.path.basename(AOI))

        # output FC will have the AOI name with 'CLU_' as a prefix
        newFC = outputWS + os.sep + "CLU_" + os.path.basename(AOI)

        # set the spatial Reference to same as WFS
        # Probably WGS_1984_Web_Mercator_Auxiliary_Sphere
        # {'spatialReference': {'latestWkid': 3857, 'wkid': 102100}
        spatialReferences = metadata['extent']['spatialReference']
        if 'latestWkid' in [sr for sr in spatialReferences.keys()]:
            sr = spatialReferences['latestWkid']
        else:
            sr = spatialReferences['wkid']

        outputCS = arcpy.SpatialReference(sr)

        # fields associated with feature service
        fsFields = metadata['fields']   # {u'alias':u'land_unit_id',u'domain': None, u'name': u'land_unit_id', u'nullable': True, u'editable': True, u'alias': u'LAND_UNIT_ID', u'length': 38, u'type': u'esriFieldTypeString'}
        fieldDict = dict()

        # lookup list for fields that are in DATE field; Date values need to be converted
        # from Unix Epoch format to mm/dd/yyyy format in order to populate a table
        dateFields = list()

        # cross-reference portal attribute description with ArcGIS attribute description
        fldTypeDict = {'esriFieldTypeString':'TEXT','esriFieldTypeDouble':'DOUBLE','esriFieldTypeSingle':'FLOAT',
                       'esriFieldTypeInteger':'LONG','esriFieldTypeSmallInteger':'SHORT','esriFieldTypeDate':'DATE',
                       'esriFieldTypeGUID':'GUID','esriFieldTypeGlobalID':'GUID'}

        # Collect field info to pass to new fc
        for fieldInfo in fsFields:

            # skip the OID field
            if fieldInfo['type'] == 'esriFieldTypeOID':
               continue

            fldType = fldTypeDict[fieldInfo['type']]
            fldAlias = fieldInfo['alias']
            fldName = fieldInfo['name']

            # skip the SHAPE_STArea__ and SHAPE_STLength__ fields
            if fldName.find("SHAPE_ST") > -1:
               continue

            if fldType == 'TEXT':
               fldLength = fieldInfo['length']
            elif fldType == 'DATE':
                 dateFields.append(fldName)
            else:
               fldLength = ""

            fieldDict[fldName] = (fldType,fldLength,fldAlias)

        # Delete newFC if it exists
        if arcpy.Exists(newFC):
           arcpy.Delete_management(newFC)
           AddMsgAndPrint("\t" + os.path.basename(newFC) + " exists.  Deleted")

        # Create empty polygon featureclass with coordinate system that matches AOI.
        arcpy.CreateFeatureclass_management(outputWS, os.path.basename(newFC), shape, "", "DISABLED", "DISABLED", outputCS)

        # Add fields from fieldDict to mimic WFS
        arcpy.SetProgressor("step", "Adding Fields to " + "CLU_" + os.path.basename(AOI),0,len(fieldDict),1)
        for field,params in fieldDict.items():
            try:
                fldLength = params[1]
                fldAlias = params[2]
            except:
                fldLength = 0
                pass

            arcpy.SetProgressorLabel("Adding Field: " + field)
            arcpy.AddField_management(newFC,field,params[0],"#","#",fldLength,fldAlias)
            arcpy.SetProgressorPosition()

        arcpy.ResetProgressor()
        arcpy.SetProgressorLabel("")
        return fieldDict,newFC

    except:
        errorMsg()
        AddMsgAndPrint("\tFailed to create scratch " + newFC + " Feature Class",2)
        return False

## ===================================================================================
def getCLUgeometryByExtent(JSONextent,fc,RESTurl):
    """ This funciton will will retrieve CLU geometry from the CLU WFS and assemble
        into the CLU fc along with the attributes associated with it.
        It is intended to receive requests that will return records that are
        below the WFS record limit"""

    try:

        params = urllibEncode({'f': 'json',
                               'geometry':JSONextent,
                               'geometryType':'esriGeometryPolygon',
                               'returnGeometry':'true',
                               'outFields': '*',
                               'token': portalToken['token']})

        # Send request to feature service; The following dict keys are returned:
        # ['objectIdFieldName', 'globalIdFieldName', 'geometryType', 'spatialReference', 'fields', 'features']
        geometry = submitFSquery(RESTurl,params)

        if not geometry:
           return False

        # Insert Geometry
        with arcpy.da.InsertCursor(fc, [fld for fld in fields]) as cur:

            arcpy.SetProgressor("step", "Assembling Geometry", 0, len(geometry['features']),1)

            # Iterenate through the 'features' key in geometry dict
            # 'features' contains geometry and attributes
            for rec in geometry['features']:

                arcpy.SetProgressorLabel("Assembling Geometry")
                values = list()    # list of attributes

                polygon = json.dumps(rec['geometry'])   # u'geometry': {u'rings': [[[-89.407702228, 43.334059191999984], [-89.40769642800001, 43.33560779300001]}
                attributes = rec['attributes']          # u'attributes': {u'land_unit_id': u'73F53BC1-E3F8-4747-B51F-E598EE445E47'}}

                # "clu_identifier" is the unique field that will be used to
                # maintain unique CLUs; If the CLU exists continue
                if attributes['clu_identifier'] in cluIdentifierList:
                   continue
                else:
                    cluIdentifierList.append(attributes['clu_identifier'])

                for fld in fields:
                    if fld == "SHAPE@JSON":
                        continue

                    # DATE values need to be converted from Unix Epoch format
                    # to dd/mm/yyyy format so that it can be inserted into fc.
                    elif fldsDict[fld][0] == 'DATE':
                        dateVal = attributes[fld]
                        if not dateVal in (None,'null','','Null'):
                            epochFormat = float(attributes[fld]) # 1609459200000

                            # Convert to seconds from milliseconds and reformat
                            localFormat = time.strftime('%m/%d/%Y',time.gmtime(epochFormat/1000))   # 01/01/2021
                            values.append(localFormat)
                        else:
                            values.append(None)

                    else:
                        values.append(attributes[fld])

                # geometry goes at the the end
                values.append(polygon)
                cur.insertRow(values)
                arcpy.SetProgressorPosition()

        arcpy.ResetProgressor()
        arcpy.SetProgressorLabel("")
        del cur

        return True

    except:
        try: del cur
        except: pass

        errorMsg()
        return False

## ====================================== Main Body ==================================
# Import modules
import sys, string, os, traceback
import urllib, re, time, json
import arcgisscripting, arcpy
from arcpy import env
import random

if __name__ == '__main__':

    try:

        """ --------------------------------------------------- Input Parameters -------------------------------"""
        AOI = arcpy.GetParameterAsText(0)
        outputWS = arcpy.GetParameterAsText(1)

        #AOI = r'O:\NRCS_Engineering_Tools_ArcPro\NRCS_Engineering_Tools_ArcPro_Update.gdb\bnd071401070404_WTSH'
        #outputWS = r'O:\NRCS_Engineering_Tools_ArcPro\NRCS_Engineering_Tools_ArcPro_Update.gdb'

        # Determine the ESRI product and set boolean
        productInfo = arcpy.GetInstallInfo()['ProductName']

         # Python 3.6 - ArcPro
        if productInfo == 'ArcGISPro':
            bArcGISPro = True
            AOIpath = arcpy.da.Describe(AOI)['catalogPath']
            from urllib.request import Request, urlopen
            from urllib.error import HTTPError as httpErrors
            urllibEncode = urllib.parse.urlencode
            parseQueryString = urllib.parse.parse_qsl

        # Python 2.7 - ArcMap
        else:
            bArcGISPro = False
            import urllib2
            import urlparse                              # This library is included in urllib in 3.7
            from urllib2 import HTTPError as httpErrors
            AOIpath = arcpy.Describe(AOI).catalogPath
            urllibEncode = urllib.urlencode
            parseQueryString = urlparse.parse_qsl

        arcpy.env.overwriteOutput = True
        AOIspatialRef = arcpy.Describe(AOIpath).spatialReference
        arcpy.env.outputCoordinateSystem = AOIspatialRef

        #scratchWS = r'O:\NRCS_Engineering_Tools_ArcPro\NRCS_Engineering_Tools_ArcPro_Update.gdb'
        scratchWS = arcpy.env.scratchWorkspace
        if not arcpy.Exists(scratchWS):
            scratchWS = setScratchWorkspace()
            arcpy.env.scratchWorkspace = scratchWS

        # Use most of the cores on the machine where ever possible
        arcpy.env.parallelProcessingFactor = "75%"

        """ ---------------------------------------------- ArcGIS Portal Information ---------------------------"""
        nrcsPortal = 'https://gis.sc.egov.usda.gov/portal/'
        portalToken = getPortalTokenInfo(nrcsPortal)
        #portalToken = {'token': '5PkSO0ZZcNVv7eEzXz8MTZBxgZbenP71uyMNnYXOefTqYs8rh0TJFGk7VKyxozK1vHOhKmpy2Z2M6mr-pngEbKjBxgIVeQmSnlfANwGXfEe5aOZjgQOU2UfLHEuGEIn1R0d0HshCP_LDtwn1-JPhbnsevrLY2a-LxTQ6D4QwCXanJECA7c8szW_zv30MxX6aordbhxHnugDD1pzCkPKRXkEoHR7r-dQxuaFSczD1jLFyDNB-7vdakAzhLc2xHPidLGt0PNileXzIecb2SA8PLQ..', 'referer': 'http://www.esri.com/AGO/8ED471D4-0B17-4ABC-BAB9-A9433506FD1C', 'expires': 1584646706}

        if not portalToken:
           AddMsgAndPrint("Could not generate Portal Token. Exiting!",2)
           exit()

        """ --------------------------------------------- get Feature Service Metadata -------------------------------"""
        # URL for Feature Service Metadata (Service Definition) - Dictionary of ;
        cluRESTurl_Metadata = """https://gis.sc.egov.usda.gov/appserver/rest/services/common_land_units/common_land_units/FeatureServer/0"""

        # Used for admin or feature service info; Send POST request
        params = urllibEncode({'f': 'json','token': portalToken['token']})

        # request info about the feature service
        fsMetadata = submitFSquery(cluRESTurl_Metadata,params)

        # Create empty CLU FC with necessary fields
        # fldsDict - {'clu_number': ('TEXT', 7, 'clu_number')}
        fldsDict,cluFC = createOutputFC(fsMetadata,outputWS)
        #fldsDict['SHAPE@JSON'] = ('SHAPE')

        # Isolate the fields that were inserted into new fc
        # Python 3.6 returns a <class 'dict_keys'>
        # Python 2.7 returns a <type 'list'>
        fields = fldsDict.keys()

        # Convert to a list b/c Python 3.6 doesn't support .append
        if bArcGISPro:
           fields = list(fields)

        fields.append('SHAPE@JSON')

        # Get the Max record count the REST service can return
        if not 'maxRecordCount' in fsMetadata:
           AddMsgAndPrint('\t\tCould not determine FS maximum record count: Setting default to 1,000 records',1)
           maxRecordCount = 1000
        else:
           maxRecordCount = fsMetadata['maxRecordCount']

        """ ---------------------------------------------- generate JSON Extents for requests -----------------------------"""
        # deconstructed AOI geometry in JSON
        #jSONpolygon = [row[0] for row in arcpy.da.SearchCursor(AOI, ['SHAPE@JSON'])][0]

        cluRESTurl = """https://gis.sc.egov.usda.gov/appserver/rest/services/common_land_units/common_land_units/FeatureServer/0/query"""

        # Get a dictionary of extents to send to WFS
        # {'request_42': ['{"xmin":-90.15,"ymin":37.19,"xmax":-90.036,"ymax":37.26,"spatialReference":{"wkid":4326,"latestWkid":4326}}', 691]}
        if bArcGISPro:
            geometryEnvelopes = createListOfJSONextents(AOI,cluRESTurl)
        else:
            geometryEnvelopes = createListOfJSONextents_ArcMap(AOI,cluRESTurl)

        if not geometryEnvelopes:
            exit()

        cluIdentifierList = list()  # Unique list of CLUs used to avoid duplicates
        failedRequests = dict()     # copy of geometryEnvelopes items that failed
        i = 1                       # request number

        for envelope in geometryEnvelopes.items():
            extent = envelope[1][0]
            numOfCLUs = envelope[1][1]
            AddMsgAndPrint("Submitting Request " + str(i) + " of " + splitThousands(len(geometryEnvelopes)) + " - " + str(numOfCLUs) + " CLUs")

            # If request fails add to failed Requests for a 2nd attempt
            if not getCLUgeometryByExtent(extent,cluFC,cluRESTurl):
               failedRequests[envelope[0]] = envelope[1]

            i+=1

        # Process failed requests as a 2nd attempt.
        if len(failedRequests) > 1:

           # All Requests failed; Not trying 2nd attempt
           if len(failedRequests) == len(geometryEnvelopes):
              AddMsgAndPrint("ALL WFS requests failed.....exiting!")
              exit()

           else:
                AddMsgAndPrint("There were " + str(len(failedRequests)) + " failed requests -- Attempting to re-download.")
                i = 1                       # request number
                for envelope in failedRequests.items():
                    extent = envelope[1][0]
                    numOfCLUs = envelope[1][1]
                    AddMsgAndPrint("Submitting Request " + str(i) + " of " + splitThousands(len(failedRequests)) + " - " + str(numOfCLUs) + " CLUs")

                    # If request fails add to failed Requests for a 2nd attempt
                    if not getCLUgeometryByExtent(extent,cluFC,cluRESTurl):
                       AddMsgAndPrint("This reques failed again")
                       AddMsgAndPrint(envelope)

        # Filter CLUs by AOI boundary
        arcpy.MakeFeatureLayer_management(cluFC,"CLUFC_LYR")
        arcpy.SelectLayerByLocation_management("CLUFC_LYR", "INTERSECT", AOI, "", "NEW_SELECTION")

        newCLUfc = outputWS + os.sep + "clu_temp"
        arcpy.CopyFeatures_management("CLUFC_LYR",newCLUfc)

        arcpy.Delete_management(cluFC)
        arcpy.Delete_management("CLUFC_LYR")

        arcpy.env.workspace = outputWS
        arcpy.Rename_management(newCLUfc,"CLU_" + os.path.basename(AOI))

        AddMsgAndPrint("\nThere are " + splitThousands(arcpy.GetCount_management(cluFC)[0]) + " CLUs in your AOI.  Done!\n")

        # Add final CLU layer to either ArcPro or ArcMap
        if bArcGISPro:
            # Add the data to ArcPro
            aprx = arcpy.mp.ArcGISProject("CURRENT")

            # Find the map from which the AOI came from
            for maps in aprx.listMaps():
                for lyr in maps.listLayers():
                    if lyr.name == os.path.basename(AOI):
                       maps.addDataFromPath(cluFC)
                       break

        else:
            # could be executed from ArcCatalog
            try:
                mxd = arcpy.mapping.MapDocument("CURRENT")
                df = arcpy.mapping.ListDataFrames(mxd)[0]
                cluLayer = arcpy.mapping.Layer(cluFC)
                arcpy.mapping.AddLayer(df,cluLayer,"TOP")
            except:
                pass

    except:
        errorMsg()
