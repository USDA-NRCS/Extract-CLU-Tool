from os import path

from arcgis.gis import GIS
from arcgis.features import FeatureLayerCollection

from arcpy import Describe, env, GetParameterAsText, GetParameter, ListTransformations, SetParameterAsText, SpatialReference
from arcpy.management import Delete, Project, Rename
from arcpy.mp import ArcGISProject, LayerFile

from utils import AddMsgAndPrint, addLyrxByConnectionProperties, errorMsg, getPortalTokenInfo, importCLUMetadata


def extract_CLU(admin_state, admin_county, tract_list, out_gdb, out_sr):
    """
    Downloads and projects a CLU field layer from the NRCS Common Land Service layer for local use.

    Args:
        admin_state (str): State code string value from GetParameterAsText
        admin_county (str): County code string value from GetParameterAsText
        tract_list (list): Tract number list from multi input
        out_gdb (str): Path to output GBD, remember to include FD in path
        out_sr (SpatialReference): arcpy object defined by user's project
    
    Returns:
        If successful returns path to extracted/projected CLU layer, otherwise False
    """
    try:
        ### Locate Common Lan Unit Service in GeoPortal ###
        gis = GIS('pro')
        clu_fs_item = gis.content.get('4b91657af3ae4368ab1c1728c97b281e')
        clu_flc = FeatureLayerCollection.fromitem(clu_fs_item)
        clu_fl = clu_flc.layers[0]
        AddMsgAndPrint('Located Common Land Units Feature Service in GeoPortal')

        ### Build CLU Query ###
        state_query = f"ADMIN_STATE = {str(admin_state)} "
        if admin_state == '02': #Alaska uses county ANSI code
            county_query = f"AND COUNTY_ANSI_CODE = {str(admin_county)} "
        else:
            county_query = f"AND ADMIN_COUNTY = {str(admin_county)} "
        if len(tract_list) == 1:
            tract_query = f"AND TRACT_NUMBER = {str(tract_list[0])}"
        else:
            tract_query = f"AND TRACT_NUMBER IN {str(tuple(tract_list))}"
        query = state_query + county_query + tract_query
        
        AddMsgAndPrint(f"Querying USDA-NRCS GeoPortal for CLU fields where: {query}")
        clu_fset = clu_fl.query(where=query)
        clu_count = len(clu_fset)

        ### Validate Number of CLUs Returned ###
        if clu_count == 0:
            AddMsgAndPrint(f"\nThere were no CLU fields associated with tract number(s) {str(tract_list)}. Please review Admin State, County, and Tract Number entered.", 1)
            return False
        if clu_count > 1:
            AddMsgAndPrint(f"\nThere are {str(clu_count)} CLU fields associated with tract number(s) {str(tract_list)}")
        else:
            AddMsgAndPrint(f"\nThere is {str(clu_count)} CLU field associated with tract number(s) {str(tract_list)}")

        ### Save and Project Extracted CLU Layer to SR Input ###
        extracted_CLU_temp = clu_fset.save(out_gdb, 'Extracted_CLU')
        from_sr = Describe(extracted_CLU_temp).spatialReference
        transformation = ListTransformations(from_sr, out_sr)
        if len(transformation):
            transformation = transformation[0]
            msg_type = 1
        else:
            transformation = None
            msg_type = 0

        projected_CLU = f"{extracted_CLU_temp}_prj"
        Project(extracted_CLU_temp, projected_CLU, out_sr, transformation)
        Delete(extracted_CLU_temp)
        Rename(projected_CLU, projected_CLU[0:-4])
        extracted_CLU = projected_CLU[0:-4]

        AddMsgAndPrint('\nProjecting CLU Feature class', msg_type)
        AddMsgAndPrint(f"FROM: {str(from_sr.name)}", msg_type)
        AddMsgAndPrint(f"TO: {str(out_sr.name)}", msg_type)
        AddMsgAndPrint(f"Geographic Transformation used: {str(transformation)}", msg_type)

        return extracted_CLU

    except Exception:
        errorMsg()
        return False


if __name__ == '__main__':

    env.overwriteOutput = True

    ### Tool Input Parameters ###
    admin_state = GetParameterAsText(0)
    admin_county = GetParameterAsText(1)
    tract_list = GetParameterAsText(2)
    out_gdb = GetParameterAsText(3)
    out_sr = GetParameter(4)

    ### Validate Portal Connection ###
    nrcsPortal = 'https://gis.sc.egov.usda.gov/portal/'
    portalToken = getPortalTokenInfo(nrcsPortal)
    if not portalToken:
        AddMsgAndPrint('Could not generate Portal token. Please login to GeoPortal. Exiting...', 2)
        exit()

    ### Parse Input Tracts into List ###
    tract_list = tract_list.split(';')

    ### Set Local Paths ###
    base_dir = path.abspath(path.dirname(__file__)) #\SUPPORT
    clu_template = path.join(base_dir, 'SUPPORT.gdb', 'Site_CLU_template')
    extracted_clu_lyrx = LayerFile(path.join(base_dir, 'layer_files', 'Extracted_CLU.lyrx')).listLayers()[0]

    ### Get CLU and Update Metadata ###
    extracted_CLU = extract_CLU(admin_state, admin_county, tract_list, out_gdb, SpatialReference(out_sr.factoryCode))
    importCLUMetadata(clu_template, extracted_CLU)
    
    ### Add Extracted CLU to Map and Zoom ###
    try:
        aprx = ArcGISProject('CURRENT')
        map = aprx.listMaps()[0]
        lyr_name_list = [lyr.longName for lyr in map.listLayers()]
        addLyrxByConnectionProperties(map, lyr_name_list, extracted_clu_lyrx, out_gdb)
        clu_extent = Describe(extracted_CLU).extent
        clu_extent.XMin = clu_extent.XMin - 100
        clu_extent.XMax = clu_extent.XMax + 100
        clu_extent.YMin = clu_extent.YMin - 100
        clu_extent.YMax = clu_extent.YMax + 100
        map_view = aprx.activeView
        map_view.camera.setExtent(clu_extent)
    except:
        # No maps in project
        pass
    