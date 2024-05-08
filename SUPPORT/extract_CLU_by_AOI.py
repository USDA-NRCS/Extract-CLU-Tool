# Name:   Extract CLUs by AOI
# Author: Adolfo.Diaz
#         GIS Specialist
#         National Soil Survey Center
#         USDA - NRCS
# e-mail: adolfo.diaz@usda.gov
# phone: 608.662.4422 ext. 216
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
# Also, all intermediate files are done 'IN_MEMORY' instead of written out.
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
# ==========================================================================================
# Modified 4/16/2020
# - Problem: There is a shift in the CLU output feature class when compared to a local CLU
#   shapefile that comes from FSA. The CLU WFS is in WGS84 and the output is written in the
#   same coordinate system as the user input AOI.
#   Solution: An environmental variable was introduced to handle geographic transformations
#   for tools that honor an output coordinate system environment. The geographic transformation
#   used is 'WGS_1984_(ITRF00)_To_NAD_1983'
# - The tool has been updated to fix the bSpatialRefUpdate. This issue only affected execution
#   in ArcMap.
#   Solution: boolean variable 'bSpatialRefUpdate' is used to determine whether the coordinate
#   system of the user-defined AOI is the same as the ArcMap dataframe. This variable was relocated
#   outside of nested statement.
# ==========================================================================================
# Modified 10/23/2020
# - Problem: Couldn't determine the # of WFS requests using ArcGIS Pro 2.5.2
#            It turns out SplitByAttributes_analysis tool no longer supports an 'in_memory'
#            target workspace, however, I found no documentation that would direclty
#            support this conclusion.  'in_memory' is legacy to ArcMap and 'memory'
#            has been adopted by ArcGIS pro
#            https://pro.arcgis.com/en/pro-app/help/analysis/geoprocessing/basics/the-in-memory-workspace.htm
#   Solution: Substitute the 'in_memory' target workspace SplitByAttributes_analysis tool
#             with the scratch workspace.  As a result, the scratch workspace was updated to
#             handle windows 10 variables and homepaths.
## ==========================================================================================
from json import dumps as json_dumps, loads as json_loads
from os import path
from random import randint
from sys import exit
from time import gmtime, sleep, strftime
from urllib.error import HTTPError
from urllib.parse import parse_qsl, urlencode
from urllib.request import urlopen

from arcpy import CreateScratchName, Describe, env, Exists, GetParameterAsText, GetSigninToken, ListFeatureClasses, \
    ListFields, ResetProgressor, SetProgressor, SetProgressorLabel, SetProgressorPosition, SpatialReference
from arcpy.analysis import SplitByAttributes
from arcpy.da import InsertCursor, SearchCursor
from arcpy.management import AddField, CalculateField, CopyFeatures, CreateFeatureclass, Delete, GetCount, MakeFeatureLayer, \
    Rename, SelectLayerByLocation, SubdividePolygon
from arcpy.mp import ArcGISProject

from utils import AddMsgAndPrint, errorMsg, getPortalTokenInfo


def submitFSquery(url, INparams):
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
        INparams = INparams.encode('ascii')
        resp = urlopen(url, INparams)  # A failure here will probably throw an HTTP exception
        responseStatus = resp.getcode()
        responseMsg = resp.msg
        jsonString = resp.read()

        # json --> Python; dictionary containing 1 key with a list of lists
        results = json_loads(jsonString)

        # Check for expired token; Update if expired and try again
        if 'error' in results.keys():
            if results['error']['message'] == 'Invalid Token':
                AddMsgAndPrint('\tRegenerating ArcGIS Token Information')

                # Get new ArcPro Token
                newToken = GetSigninToken()

                # Update the original portalToken
                global portalToken
                portalToken = newToken

                # convert encoded string into python structure and update token
                # by parsing the encoded query strting into list of (name, value pairs)
                # i.e [('f', 'json'),('token','U62uXB9Qcd1xjyX1)]
                # convert to dictionary and update the token in dictionary

                queryString = parse_qsl(params)

                requestDict = dict(queryString)
                requestDict.update(token=newToken['token'])

                newParams = urlencode(requestDict)
                newParams = newParams.encode('ascii')

                # update incoming parameters just in case a 2nd attempt is needed
                INparams = newParams

                resp = urlopen(url, newParams)  # A failure here will probably throw an HTTP exception
                responseStatus = resp.getcode()
                responseMsg = resp.msg
                jsonString = resp.read()

                results = json_loads(jsonString)

        # Check results before returning them; Attempt a 2nd request if results are bad.
        if 'error' in results.keys() or len(results) == 0:
            sleep(5)

            resp = urlopen(url, INparams)  # A failure here will probably throw an HTTP exception
            responseStatus = resp.getcode()
            responseMsg = resp.msg
            jsonString = resp.read()

            results = json_loads(jsonString)

            if 'error' in results.keys() or len(results) == 0:
                AddMsgAndPrint(f"\t2nd Request Attempt Failed - Error Code: {str(responseStatus)} -- {responseMsg} -- {str(results)}", 2)
                return False
            else:
                return results

        else:
             return results

    except HTTPError as e:
        if int(e.code) >= 500:
           #AddMsgAndPrint(f"\n\t\tHTTP ERROR: {str(e.code)} ----- Server side error. Probably exceed JSON imposed limit", 2)
           #AddMsgAndPrint(f"t\t{str(request)}"")
           pass
        elif int(e.code) >= 400:
           #AddMsgAndPrint(f"\n\t\tHTTP ERROR: {str(e.code)} ----- Client side error. Check the following SDA Query for errors:", 2)
           #AddMsgAndPrint(f"\t\t{getGeometryQuery}"")
           pass
        else:
           AddMsgAndPrint(f"HTTP ERROR = {str(e.code)}", 2)

    except:
        errorMsg()
        return False


def createListOfJSONextents(inFC, RESTurl):
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
        jsonDict = dict()

        # deconstructed AOI geometry in JSON
        jSONpolygon = [row[0] for row in SearchCursor(inFC, ['SHAPE@JSON'])][0]

        params = urlencode({'f': 'json',
                            'geometry': jSONpolygon,
                            'geometryType': 'esriGeometryPolygon',
                            'returnCountOnly': 'true',
                            'token': portalToken['token']})

        # Get geometry count of incoming fc
        countQuery = submitFSquery(RESTurl, params)

        if not countQuery:
           AddMsgAndPrint('Failed to get estimate of CLU count', 2)
           return False

        AddMsgAndPrint(f"\nThere are approximately {str(countQuery['count'])} CLUs within AOI")

        # if count is within max records allowed no need to proceed
        if countQuery['count'] <= maxRecordCount:
            jsonDict[path.basename(inFC)] = [jSONpolygon, countQuery['count']]

        # AOI bounding box will have to be continously split until polygons capture
        # CLU records below 1000 records.
        else:
            AddMsgAndPrint('Determining # of WFS requests')

            numOfAreas = int(countQuery['count'] / 800)  # How many times the input fc will be subdivided initially
            splitNum = 0                   # arbitrary number to keep track of unique files
            subDividedFCList = list()      # list containing recycled fcs to be split
            subDividedFCList.append(inFC)  # inFC will be the first one to be subdivided

            # iterate through each polygon in fc in list and d
            for fc in subDividedFCList:
                SetProgressorLabel(f"Determining # of WFS requests. Current #: {str(len(jsonDict))}")

                # Subdivide fc into 2
                subdivision_fc = path.join('in_memory', path.basename(CreateScratchName('subdivision', data_type='FeatureClass')))

                if splitNum > 0:
                   numOfAreas = 2

                SubdividePolygon(fc, subdivision_fc, 'NUMBER_OF_EQUAL_PARTS', numOfAreas, '', '', '', 'STACKED_BLOCKS')

                # first iteration will be the inFC and don't wnat to delete it
                if splitNum > 0:
                   Delete(fc)

                # Add new fld to capture unique name used for each subdivided polygon which the
                # splitByAttributes tool will use.
                newOIDfld = 'objectID_TEXT'
                expression = f"assignUniqueNumber(!{Describe(subdivision_fc).OIDFieldName}!)"
                randomNum = str(randint(1, 9999999999))

                # code block doesn't like indentations
                codeBlock = """
def assignUniqueNumber(oid):
    return \"request_\" + str(""" + str(randomNum) + """) + str(oid)"""

                if not len(ListFields(subdivision_fc, newOIDfld)) > 0:
                    AddField(subdivision_fc, newOIDfld, 'TEXT', '#', '#', '30')

                CalculateField(subdivision_fc, newOIDfld, expression, 'PYTHON3', codeBlock)
                splitNum += 1

                # Create a fc for each subdivided polygon
                # split by attributes was faster by 2 secs than split_analysis
                SplitByAttributes(subdivision_fc, outputWS, [newOIDfld])
                Delete(subdivision_fc)

                # Create a list of fcs that the split tool outputs

                splitFCList = ListFeatureClasses(f"request_{randomNum}*")

                # Assess each split FC to determine if it
                for splitFC in splitFCList:

                    splitFC = Describe(splitFC).catalogPath
                    SetProgressorLabel(f"Determining # of WFS requests. Current #: {str(len(jsonDict))}")

                    splitExtent = [row[0] for row in SearchCursor(splitFC, ['SHAPE@JSON'])][0]

                    params = urlencode({'f': 'json',
                                        'geometry': splitExtent,
                                        'geometryType': 'esriGeometryPolygon',
                                        'returnCountOnly': 'true',
                                        'token': portalToken['token']})

                    # Send geometry count request
                    countQuery = submitFSquery(RESTurl, params)

                    # request failed.....try once more
                    if not countQuery:
                        sleep(5)
                        countQuery = submitFSquery(RESTurl, params)

                        if not countQuery:
                           AddMsgAndPrint('\tFailed to get count request -- 3 attempts made -- Recycling request')
                           subDividedFCList.append(splitFC)
                           continue

                    # if count is within max records allowed add it dict
                    if countQuery['count'] <= maxRecordCount:
                        jsonDict[path.basename(splitFC)] = [splitExtent, countQuery['count']]
                        Delete(splitFC)

                    # recycle this fc back to be split into 2 polygons
                    else:
                        subDividedFCList.append(splitFC)

        if len(jsonDict) < 1:
            AddMsgAndPrint('\tCould not determine number of server requests. Exiting', 2)
            return False
        else:
            AddMsgAndPrint(f"\t{str(len(jsonDict))} server requests are needed")
            return jsonDict

    except:
        errorMsg()
        return False


def createOutputFC(metadata, outputWS, shape='POLYGON'):
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
        # output FC will the 'CLU_' as a prefix along with AOI name
        newFC = path.join(outputWS, f"CLU_{path.basename(input_aoi)}")

        AddMsgAndPrint(f"\nCreating New Feature Class: CLU_{path.basename(input_aoi)}")
        SetProgressorLabel(f"Creating New Feature Class: CLU_{path.basename(input_aoi)}")

        # set the spatial Reference to same as WFS
        # Probably WGS_1984_Web_Mercator_Auxiliary_Sphere
        # {'spatialReference': {'latestWkid': 3857, 'wkid': 102100}
        spatialReferences = metadata['extent']['spatialReference']
        if 'latestWkid' in [sr for sr in spatialReferences.keys()]:
            sr = spatialReferences['latestWkid']
        else:
            sr = spatialReferences['wkid']

        outputCS = SpatialReference(sr)

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
            if fldName.find('SHAPE_ST') > -1:
               continue

            if fldType == 'TEXT':
               fldLength = fieldInfo['length']
            elif fldType == 'DATE':
                 dateFields.append(fldName)
            else:
               fldLength = ''

            fieldDict[fldName] = (fldType, fldLength, fldAlias)

        # Delete newFC if it exists
        if Exists(newFC):
           Delete(newFC)
           AddMsgAndPrint(f"\t{path.basename(newFC)} already exists. Deleted")

        # Create empty polygon featureclass with coordinate system that matches AOI.
        CreateFeatureclass(outputWS, path.basename(newFC), shape, '', 'DISABLED', 'DISABLED', outputCS)

        # Add fields from fieldDict to mimic WFS
        SetProgressor('step', f"Adding fields to CLU_{path.basename(input_aoi)}", 0, len(fieldDict), 1)
        for field,params in fieldDict.items():
            try:
                fldLength = params[1]
                fldAlias = params[2]
            except:
                fldLength = 0
                pass

            SetProgressorLabel(f"Adding Field: {field}")
            AddField(newFC, field, params[0], '#', '#', fldLength, fldAlias)
            SetProgressorPosition()

        ResetProgressor()
        SetProgressorLabel('')
        return fieldDict, newFC

    except:
        errorMsg()
        AddMsgAndPrint(f"\tFailed to create scratch {newFC} Feature Class", 2)
        return False


def getCLUgeometryByExtent(JSONextent, fc, RESTurl):
    """ This funciton will will retrieve CLU geometry from the CLU WFS and assemble
        into the CLU fc along with the attributes associated with it.
        It is intended to receive requests that will return records that are
        below the WFS record limit"""
    try:
        params = urlencode({'f': 'json',
                            'geometry': JSONextent,
                            'geometryType': 'esriGeometryPolygon',
                            'returnGeometry': 'true',
                            'outFields': '*',
                            'token': portalToken['token']})

        # Send request to feature service; The following dict keys are returned:
        # ['objectIdFieldName', 'globalIdFieldName', 'geometryType', 'spatialReference', 'fields', 'features']
        geometry = submitFSquery(RESTurl, params)
        if not geometry:
           return False

        # Insert Geometry
        with InsertCursor(fc, [fld for fld in fields]) as cur:
            SetProgressor('step', 'Assembling Geometry', 0, len(geometry['features']), 1)

            # Iterenate through the 'features' key in geometry dict
            # 'features' contains geometry and attributes
            for rec in geometry['features']:

                SetProgressorLabel('Assembling Geometry')
                values = list()    # list of attributes

                polygon = json_dumps(rec['geometry'])   # u'geometry': {u'rings': [[[-89.407702228, 43.334059191999984], [-89.40769642800001, 43.33560779300001]}
                attributes = rec['attributes']          # u'attributes': {u'land_unit_id': u'73F53BC1-E3F8-4747-B51F-E598EE445E47'}}

                # 'clu_identifier' is the unique field that will be used to
                # maintain unique CLUs; If the CLU exists continue
                if attributes['clu_identifier'] in cluIdentifierList:
                   continue
                else:
                    cluIdentifierList.append(attributes['clu_identifier'])

                for fld in fields:
                    if fld == 'SHAPE@JSON':
                        continue

                    # DATE values need to be converted from Unix Epoch format
                    # to dd/mm/yyyy format so that it can be inserted into fc.
                    elif fldsDict[fld][0] == 'DATE':
                        dateVal = attributes[fld]
                        if not dateVal in (None, 'null', '', 'Null'):
                            epochFormat = float(attributes[fld]) # 1609459200000
                            # Convert to seconds from milliseconds and reformat
                            localFormat = strftime('%m/%d/%Y', gmtime(epochFormat/1000))   # 01/01/2021
                            values.append(localFormat)
                        else:
                            values.append(None)
                    else:
                        values.append(attributes[fld])

                # geometry goes at the the end
                values.append(polygon)
                cur.insertRow(values)
                SetProgressorPosition()

        ResetProgressor()
        SetProgressorLabel('')
        return True

    except:
        errorMsg()
        return False


if __name__ == '__main__':
    input_aoi = GetParameterAsText(0)
    outputWS = GetParameterAsText(1)
    
    try:
        AOIpath = Describe(input_aoi).catalogPath

        ### ESRI environment settings ###
        env.overwriteOutput = True
        env.outputCoordinateSystem = Describe(AOIpath).spatialReference
        env.geographicTransformations = 'WGS_1984_(ITRF00)_To_NAD_1983'

        nrcsPortal = 'https://gis.sc.egov.usda.gov/portal/'
        portalToken = getPortalTokenInfo(nrcsPortal)

        if not portalToken:
           AddMsgAndPrint('Could not generate Portal Token. Exiting!', 2)
           exit()

        # URL for Feature Service Metadata (Service Definition)
        cluRESTurl_Metadata = 'https://gis.sc.egov.usda.gov/appserver/rest/services/common_land_units/common_land_units/FeatureServer/0'

        # Used for admin or feature service info; Send POST request
        params = urlencode({'f': 'json','token': portalToken['token']})

        # request info about the feature service
        fsMetadata = submitFSquery(cluRESTurl_Metadata, params)

        # Create empty CLU FC with necessary fields
        fldsDict, cluFC = createOutputFC(fsMetadata, outputWS)

        # Isolate the fields that were inserted into new fc
        fields = fldsDict.keys()

        # Convert to a list b/c Python 3.6 doesn't support .append
        fields = list(fields)
        fields.append('SHAPE@JSON')

        # Get the Max record count the REST service can return
        if not 'maxRecordCount' in fsMetadata:
           AddMsgAndPrint('\t\tCould not determine FS maximum record count: Setting default to 1,000 records', 1)
           maxRecordCount = 1000
        else:
           maxRecordCount = fsMetadata['maxRecordCount']

        cluRESTurl = f"{cluRESTurl_Metadata}/query"

        # Get a dictionary of extents to send to WFS
        # {'request_42': ['{"xmin":-90.15,"ymin":37.19,"xmax":-90.036,"ymax":37.26,"spatialReference":{"wkid":4326,"latestWkid":4326}}', 691]}
        geometryEnvelopes = createListOfJSONextents(input_aoi, cluRESTurl)

        if not geometryEnvelopes:
            exit()

        cluIdentifierList = list()  # Unique list of CLUs used to avoid duplicates
        failedRequests = dict()     # copy of geometryEnvelopes items that failed
        i = 1                       # request number

        for envelope in geometryEnvelopes.items():
            extent = envelope[1][0]
            numOfCLUs = envelope[1][1]
            AddMsgAndPrint(f"Submitting Request {str(i)} of {str(len(geometryEnvelopes))} - {str(numOfCLUs)} CLUs")

            # If request fails add to failed Requests for a 2nd attempt
            if not getCLUgeometryByExtent(extent, cluFC, cluRESTurl):
               failedRequests[envelope[0]] = envelope[1]

            i+=1

        # Process failed requests as a 2nd attempt.
        if len(failedRequests) > 1:

           # All Requests failed; Not trying 2nd attempt
           if len(failedRequests) == len(geometryEnvelopes):
              AddMsgAndPrint('ALL WFS requests failed...exiting!')
              exit()

           else:
                AddMsgAndPrint(f"There were {str(len(failedRequests))} failed requests. Attempting to re-download")
                i = 1                       # request number
                for envelope in failedRequests.items():
                    extent = envelope[1][0]
                    numOfCLUs = envelope[1][1]
                    AddMsgAndPrint(f"Submitting Request {str(i)} of {str(len(failedRequests))} - {str(numOfCLUs)} CLUs")

                    # If request fails add to failed Requests for a 2nd attempt
                    if not getCLUgeometryByExtent(extent, cluFC, cluRESTurl):
                       AddMsgAndPrint('This reques failed again')
                       AddMsgAndPrint(envelope)

        # Filter CLUs by AOI boundary
        MakeFeatureLayer(cluFC, 'CLUFC_LYR')
        SelectLayerByLocation('CLUFC_LYR', 'INTERSECT', input_aoi, '', 'NEW_SELECTION')

        newCLUfc = path.join(outputWS, 'clu_temp')
        CopyFeatures('CLUFC_LYR', newCLUfc)

        Delete(cluFC)
        Delete('CLUFC_LYR')

        env.workspace = outputWS
        Rename(newCLUfc, f"CLU_{path.basename(input_aoi)}")

        AddMsgAndPrint(f"\nThere are {str(GetCount(cluFC)[0])} CLUs in your AOI. Done!\n")

        aprx = ArcGISProject('CURRENT')
        for maps in aprx.listMaps():
            for lyr in maps.listLayers():
                if lyr.name == path.basename(input_aoi):
                    maps.addDataFromPath(cluFC)
                    break

    except:
        errorMsg()
