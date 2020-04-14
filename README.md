# Extract-CLU-Tool
Download this tool to extract USDA-FSA Common Land Units into a File Geodatabase feature class by area of interest

This tool will extract USDA-FSA Common Land Units (CLU) from the authoritative CLU Web Feature Service hosted on the USDA-NRCS Geoportal 10.6.1 based on an area of interest. The CLU dataset consists of digitized farm tract and field boundaries and associated attribute data.

## Usage:
   - This tool can be used in ArcGIS or ArcGIS Pro.
   - CLU Web Feature service used is https://gis.sc.egov.usda.gov/appserver/rest/services/common_land_units/common_land_units/FeatureServer/0/query

   - User must be logged into the NRCS GeoPortal: https://gis.sc.egov.usda.gov/portal/
   - Input Area of interest must be a polygon feature class.
   - Area of interest is continously subdivided until the REST request returns less than 1000 records. Subdivided polygons are not written out.
   - Output CLU feature class will be written to a user-defined File Geodatabase.
   - Output CLU feature class will use the AOI name as a suffix to "CLU_".
