#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:
#
# Author:      Adolfo.Diaz
#
# Created:     29/07/2020
# Copyright:   (c) Adolfo.Diaz 2020
# Licence:     <your licence>
#-------------------------------------------------------------------------------

## ==============================================================================================================================
def AddMsgAndPrint(msg, severity=0):
    # prints message to screen if run as a python script
    # Adds tool message to the geoprocessor
    #
    #Split the message on \n first, so that if it's multiple lines, a GPMessage will be added for each line
    try:

        print(msg)
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


if __name__ == '__main__':

    try:

        import sys, string, os, traceback
        import urllib, re, time, json, random
        import arcpy

        from importlib import reload

        sys.dont_write_bytecode = True
        scriptPath = os.path.dirname(sys.argv[0])
        sys.path.append(scriptPath)

        import extract_CLU_by_Tract_WCTool
        reload(extract_CLU_by_Tract_WCTool)

        adminState = arcpy.GetParameterAsText(0)
        adminCounty = arcpy.GetParameterAsText(1)
        tractNumber = arcpy.GetParameterAsText(2)
        outSpatialRef = arcpy.GetParameterAsText(3)
        outputWS = arcpy.GetParameterAsText(4)

##        adminState = "29"
##        adminCounty = "017"
##        tractNumber = 1207
##        outSpatialRef = arcpy.GetParameterAsText(3)
##        outputWS = r'E:\ACPF_subsetData\acpf071401070404.gdb'

        junk = extract_CLU_by_Tract_WCTool.start(adminState,adminCounty,tractNumber,outSpatialRef,outputWS)
        AddMsgAndPrint(junk)

    except:
        errorMsg()