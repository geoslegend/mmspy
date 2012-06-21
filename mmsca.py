# -*- coding: utf-8 -*-  
"""
  This file is the main code of the conflictAnalysis tool developed in 
  the DSITE Group, Center for Applied Geosciences, University of Tuebingen, 
  Germany.
  The algorithm was created by Max Morio, and written in python by Oz Nahum
  and Max Morio.

  This program is free software; you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation; either version 2 of the License, or
  (at your option) any later version.
    
  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.
     
  You should have received a copy of the GNU General Public License
  along with this program; if not, write to the Free Software
  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
  MA 02110-1301, USA.
"""

from osgeo import ogr
from osgeo import osr
from osgeo import gdal
from osgeo import gdal_array
import os, ConfigParser, sys
import shutil
from matplotlib import nxutils
import numpy as np
import csv

class Project():
    """
    defines objects to hold project properties
    TODO:
    Document all project properties.
    
    LUTcolours - RGB colors for each land use.
    LUTName - Names list of all land uses.
    selcont - List of selected contaminants.
    
    #TEST project in the shell
    
    import mmsca
    proj = mmsca.project()
    proj = getconfig("DATA/Projekt.ini")
    
    #TEST Project in the main script confanalysis.py
    def parseArgs():
        ... omitted ...
        try:
            proj =  project()
            proj.getconfig(os.path.abspath(sys.argv[1])+'/Projekt.ini')
        except IOError:
            print "ERROR: Could not find the Projekt.ini under " \
            + os.path.abspath(sys.argv[1])
            sys.exit(1)
        ... omitted ...

    """
    def __init__(self):
        self.aktscenario = ""
        self.aktlayout = ""
        self.layoutdir = ""
        self.n_contaminants = 0
        self.aoiraster = ""
        self.LUTcolours = ['']
        self.LUTName = ['']
        self.scen_landuseratio = ['']
        self.selcont = ['']
        self.n_landuses = 0

    def getconfig(self, projectini):
        """
        read Project.ini and populat all the properties of a Project instance.
        """
        config = ConfigParser.RawConfigParser()
        config.readfp(open(projectini))
        self.aktscenario = config.get('DSS_project', 'AktSzenario')
        self.aktlayout = config.get('DSS_project', 'AktLayout')
        self.aoiraster = config.get('DSS_project', 'pathstandort')
        self.n_landuses = int(config.get('DSS_project', 'n_Landuses'))
        self.n_contaminants = int(config.get( self.aktscenario, 
                                                'anzahlschadstoffe'))
        self.scen_landuseratio *= self.n_landuses
        self.LUTName *= self.n_landuses
        self.LUTcolours *= self.n_landuses
        for i in range(1, self.n_landuses+1):
            idx = str(i)
            self.scen_landuseratio[i-1] = config.get(self.aktscenario, 
                                    'scen_landuseratio(' + idx + ')') 
            self.LUTName[i-1] = config.get('DSS_project',
                                           'LUTName(' + idx + ')')
            self.LUTcolours[i-1] = [
                config.get('DSS_project','LUTcoloursR(' + idx + ')'), \
                config.get('DSS_project','LUTcoloursG(' + idx + ')'), \
                config.get('DSS_project','LUTcoloursB(' + idx + ')')  ]
        # MAX: note here , len(selcont) = n_contaminants
        #      while in the original readprojectfile 
        #      len(selcont) = n_contaminants - 1
        self.selcont *= self.n_contaminants            
        for i in range(self.n_contaminants):
            idx = str(i+1)
            self.selcont[i] = config.get(self.aktscenario,
                                            'selcont(' + idx + ')') 
    def cleanup(self):
        """
        Clean up files from previous runs ...
        """
        suffixes = ['.cost', '.cosk', '.snh', '.WE', 'opttmep']
        mmsfiles2keep = ['']*len(suffixes)
        for idx, suffix in enumerate(suffixes):
            mmsfiles2keep[idx] = self.aktscenario+'/'+self.aktlayout \
            +'/'+self.aktlayout+suffix
        # make a copy of needed files in mmsfiles2keep
        for idx in mmsfiles2keep:
            if os.path.isfile(idx):
                fname = idx.replace(self.aktlayout + '/' + self.aktlayout, 
                self.aktlayout)
                shutil.copy2(idx, fname) 
            elif os.path.isdir(idx):
                dirname = idx.replace(self.aktlayout + '/opttemp', '/opttemp')
                shutil.copytree(idx, dirname)
        #delete the dir including files and subdirs
        shutil.rmtree(self.aktscenario + '/' + self.aktlayout, 
            ignore_errors=True)
        #create the layout dir, again
        if not os.path.isdir(self.aktscenario + '/' + self.aktlayout):
            os.mkdir(self.aktscenario + '/' + self.aktlayout)
        #move back the *.cost, *cosk , *snh and *WE files to 
        #the aktlayout dirproj=mmsca.project()
        for idx in mmsfiles2keep:
            fname = idx.replace(self.aktlayout + '/' + self.aktlayout, 
                self.aktlayout)
            dirname = idx.replace(self.aktlayout + '/opttemp', '/opttemp')
            if os.path.isfile(fname):
                shutil.copy2(fname, idx) 
            elif os.path.isdir(dirname):
                shutil.copytree(dirname, idx)


class ASCIIRaster():
    """
    Wrapper class to handle ASCII Rasters
    """
    def __init__(self):
        self.ncols      =  100
        self.nrows      =  100
        self.xllcorner  =   0
        self.yllcorner  =   0
        self.xurcorner  =   0
        self.yurcorner  =   0
        self.extent = []
        self.cellsize  =    10
        self.NODATA_value = -9999
        self.mask = np.array((0, 0))
        self.data = np.array((0, 0))
        self.rasterpoints = np.array((0, 0))
        self.Xrange = np.array((0, 0))
        self.Yrange = np.array((0, 0))
        self.boundingvertices = np.array((0, 0))

    def rader(self, filename):
        """
        read an asci file, store a numpy array containing all data
        """
        dataset = gdal.Open(filename)
        self.extent = dataset.GetGeoTransform()
        self.ncols = dataset.RasterXSize #ncols
        self.nrows = dataset.RasterYSize #nrows
        # This extents are correct for shape files
        # note for future, when reading shape files with shapelib
        # In [43]: mask.extent
        #Out[43]: (2.555355548813, 6.4083399774, 49.49721527098, 51.503826015)
        
        #In [44]: r.bbox
        #Out[44]: [2.5553558813, 49.49721527038, 6.4083399744, 51.503826015]
        # the elements 2 and 3 of extent ans bbox are swapped!
        self.xllcorner = self.extent[0]
        self.yllcorner = self.extent[2]
        self.xurcorner = self.extent[1] 
        self.yurcorner = self.extent[3]
        self.data = gdal_array.DatasetReadAsArray(dataset)
        
    def fillrasterpoints(self, xres, yres):
        """
        Create data points of each raster pixel, based on extents
        and X,Y resolution 
        
        If we have a grid with X from 0 to 2 and Y from 0 to 3:
        
         2.5| +     +      
          2 |
         1.5| +     +
          1 |
         .5 | +     +
            +----------        
              .5 1 1.5 2
          
        The pixel centers are: 
        p1x 0.5, p1y 0.5
        p2x 1.5, p2y 0.5
        p3x 0.5, p3y 1.51
        p4x 1.5, p4y 1.5
        p5x 0.5, p5y 2.5
        p6x 1.5, p6y 2.5
        ...
        """
        self.Xrange = np.arange(self.xllcorner+0.5*xres, 
                           self.xurcorner+0.5*xres,xres) 
        self.Yrange = np.arange(self.yllcorner+0.5*yres, 
                           self.yurcorner+0.5*yres,yres)
        xpts, ypts = np.meshgrid(self.Xrange, self.Yrange)
        self.rasterpoints = np.column_stack((xpts.flatten(), 
            ypts.flatten())) 
    
    def writer(self, dst_filename, array, topleft, ew_res, ns_res, 
        proj=31468): 
        """
        This is a generic GDAL function to write ASCII Rasters.
        Here it is an aid function called by ClipPollution and others.
        inputs:
        dst_filename - string - relative path to write the ASCII raster
        array - ndarray, numpy array - a data array to be written in to the file. 
        ewRes - East West Resolution
        nsRes - North South Resolution
        proj - projection (separate .prj file specifying the projection. 
               see  http://spatialreference.org/ref/epsg/31468/.
               The default is Gauss Kruger DHDN zone 4, relevant for
               North Eastern Germany.
        
        output:
        file - This function writes an ASCII raster file to the same path as 
        dst_filename.
        """
        gformat = "MEM"
        driver = gdal.GetDriverByName(gformat)
        dst_ds = driver.Create(dst_filename, len(array[0]), len(array), \
                1, gdal.GDT_Float32)
        extent = (topleft[0], ew_res, 0, topleft[1], 0, ns_res )
        dst_ds.SetGeoTransform(extent)
        srs = osr.SpatialReference()
        srs.ImportFromEPSG(proj) 
        dst_ds.SetProjection(srs.ExportToWkt())
        dst_ds.GetRasterBand(1).SetNoDataValue(-9999)
        dst_ds.GetRasterBand(1).WriteArray(array)
        aformat = 'AAIGrid'
        driver = gdal.GetDriverByName(aformat)
        dst_ds = driver.CreateCopy(dst_filename, dst_ds)
        dst_ds = None

class MaskRaster(ASCIIRaster):
    """
    Define a Mask raster containing Zero for points outside the area
    of interest, and One for points inside the area of interest.
    
    test usage:
    import time
    a = time.time()
    test = MaskRaster()
    test.getareofinterest("DATA/area_of_interest.shp")
    test.fillRasterPoints(10,10)
    test.getmask()
    test.Writer("test_mask.asc", test.mask, (test.extent[0], test.extent[3]),10,10)
    print "finished in:", time.time() - a , "sec"
    """
    def getareaofinterest(self, aoi_shp_file):
        """
        Read a shape file containing a a single polygon bounding an area of interest.
        """
        datasource = aoi_shp_file
        driver = ogr.GetDriverByName('ESRI Shapefile')
        datasource = driver.Open(datasource, 0)
        layer = datasource.GetLayer()
        self.extent = layer.GetExtent()
        print 'Extent des Bewertungsgebiets (area_of_interest):', self.extent
        print 'UL:', self.extent[0], self.extent[3]
        print 'LR:', self.extent[1], self.extent[2]
        self.xllcorner = self.extent[0]
        self.yllcorner = self.extent[2]
        self.xurcorner = self.extent[1] 
        self.yurcorner = self.extent[3]
        area = layer.GetFeature(0)
        geometry = area.GetGeometryRef()
        boundary_raw = str(geometry.GetBoundary())
        boundary = boundary_raw[12:-1]
        #some processing to convert boundary raw to a usefull form !
        #remove tail and head
        boundary = boundary.split(',')#convert the string to a list of strings
        #convert the string to a list of lists (couples of x y coordinates)   
        for idx, point in enumerate(boundary):
            #pointx, pointy = point.split()
            #boundary[x] = float(pointx), float(pointy)
            boundary[idx] = point.split()
        
        # THIS CODE is Correct only if AOI has one polygon
        #       We need a fix in case we have multiple polygons
        # np.set_printoptions(precision=18)
        self.boundingvertices = np.asarray(boundary, dtype = np.float64)
    
    def getmask(self, vertices):
        """
        getMask takes a list of points, and a list of vertices, 
        representing the polygon boundaries, and returns a Boolean 
        array with True for points inside the polygon and False for 
        points outside the polygon.
        !make this function use multithreading so we can go
        a bit faster !
        """
        self.mask = nxutils.points_inside_poly(self.rasterpoints, 
                    vertices)
        #self.mask.resize(self.Yrange.size, self.Xrange.size)
        #self.mask = np.flipud(self.mask)


class LandUseShp():
    """
    Get landuses from shapefile, create landuses raster
    """
    def __init__(self, shapefilepath, copyfile=None):
        self.filepath=shapefilepath
        driver = ogr.GetDriverByName('ESRI Shapefile')
        self.LandUses = []
        self.Codes = [] #Store Categories
        self.NPolygons = 1 # number of polygons in layer
        # driver.Open(path,0) -> open read only
        # driver.Open(path,1) -> open with update option
        if copyfile:
            self.copyfilepath=copyfile
            self.createcopy()
            self.dataSource = driver.Open(self.copyfilepath, 1)
        else: self.dataSource = driver.Open(shapefilepath, 0)
        self.layer = self.dataSource.GetLayer()
        self.NPolygons = self.layer.GetFeatureCount()
        # store vertices of each polygon      
        self.Boundaries = [""]*self.NPolygons   
        for polygon in range(self.NPolygons):
            area = self.layer.GetFeature(polygon)
            name = area.GetField(0)
            category = area.GetField(1)
            self.LandUses.append(name)
            self.Codes.append(category)
            geometry = area.GetGeometryRef()
            boundary_raw = str(geometry.GetBoundary())
            #remove tail and head
            boundary = boundary_raw[12:-1]
            boundary = boundary.split(',')
            #convert each coordinate from string to float
            for idx, point in enumerate(boundary):
                boundary[idx] = point.split()
            boundingvertices = np.asarray(boundary, dtype = np.float64)
            self.Boundaries[polygon] = boundingvertices
    
    def createcopy(self):
        """
        copy the shape file to output file path
        """
        # check if dirname exists, if not create it
        print "Shape file copied to :", self.copyfilepath
        dest_dir=os.path.dirname(self.copyfilepath)
        if not os.path.exists(dest_dir):
            print dest_dir
            os.makedirs(dest_dir)
        suffixes = ['shp', 'shx',  'dbf']
        for suffix in suffixes:
            shutil.copy2(self.filepath.replace("shp", suffix),
                 self.copyfilepath.replace("shp", suffix))
    def addfield(self,fieldname):
        """
        Add field to attribute table
        """
        field_TEXT  = ogr.FieldDefn(fieldname, ogr.OFTString) 
        field_TEXT.SetWidth(20)
        self.layer.CreateField(field_TEXT)
        rslt=self.layer.SyncToDisk()
        if rslt != 0:
            print "Error: Could not write new feature ", fieldname , \
                " to attribute table of ", self.copyfilepath
            sys.exit(1)
            
    def setvalues(self, fieldname ,value):
        """
        Set the property of a polygon.
        This function should  be used inside a loop, since 
        we iterate over the polygon, for example:
        In [42]: A.__class__
        Out[42]: mmsca.LandUseShp
        In [43]: for i in range(A.layer.GetFeatureCount()):
            A.setthresholds("Test", 222+i)
        This will set for each polygon the field "Test" to 222+i.
        """
        feature=self.layer.GetNextFeature()
        if feature:
            idx=feature.GetFieldIndex(fieldname)
            feature.SetField2(idx,value)
            self.layer.SetFeature(feature)
            self.layer.SyncToDisk()
        #feature=self.layer.GetNextFeature()
        else:
            #re-read features ...
            #self.layer.ResetReading()
            return None
            
        
    def rasterize(self, xres, yres, rasterfilepath=None):
        """
        raster object does not needs to be created outside
        """
        raster = MaskRaster()
        raster.extent = self.layer.GetExtent()
        raster.xllcorner = raster.extent[0]
        raster.yllcorner = raster.extent[2]
        raster.xurcorner = raster.extent[1] 
        raster.yurcorner = raster.extent[3]
        raster.fillrasterpoints(xres, yres)
        raster.data = np.zeros(raster.rasterpoints.shape[0])
        for boundary, code in zip(self.Boundaries, self.Codes):
            vmask = nxutils.points_inside_poly(raster.rasterpoints, boundary)
            raster.mask = np.column_stack([vmask, vmask])
            #deleted_indexes=np.where(raster.mask==True)
            #raster.rasterpoints=np.delete(raster.rasterpoints, 
            #                        np.where(raster.mask==True),0)
            raster.rasterpoints = np.ma.array(raster.rasterpoints, 
                    mask = raster.mask, fill_value = [0, 0])
            vmask = vmask*code
            #raster.mask = np.ma.masked_equal(raster.mask, 0)
            #raster.mask.set_fill_value(-9999)
            raster.data = raster.data + vmask
            raster.rasterpoints = raster.rasterpoints.filled()
            # insert to deleted indecies bogus points so next time
            # raster.mask is the same size as the previous step
        if rasterfilepath:
            """
            PROBLEM?: This still lives 0 intead of no data"
            """
            raster.data.resize(raster.Yrange.size, raster.Xrange.size)
            #raster.data.reshape(X)
            raster.data = np.flipud(raster.data)
            np.putmask(raster.data, raster.data == 0, -9999)
            raster.writer(rasterfilepath, raster.data, 
                    (raster.extent[0], raster.extent[3]), yres, yres)
        else: return raster

class ZielWerte():
    """
    Class to hold all the values from Zielwert.rtv
    """
    def __init__(self,proj):
        n_Landuses=proj.n_landuses
        try:
            infile_target =  'Zielwertset.rtv'
            infile_target = os.path.abspath(proj.aktscenario)+'/'+infile_target
            targetreader = csv.reader(open(infile_target, "r"))
        except IOError:
            print "Error: Could not find 'Zielwertset.rtv' under " \
            , os.path.abspath(aktscenario) 
            sys.exit(1)
        self.contnames = []
        self.compartments = []
        self.targets_LUT=[]
        self.contrasternames = []
        self.boolConflictType = []
        self.iContRealisations = []
        self.no_contaminants = int(targetreader.next()[0])
        print 'Anzahl Kontaminanten (B und GW): ', self.no_contaminants
        for row in targetreader:
            self.contnames.append(row[0])
            self.compartments.append(row[1])
            self.targets_LUT.append(row[2:n_Landuses+2])
            self.contrasternames.append(row[n_Landuses+2])
            self.boolConflictType.append(row[n_Landuses+3])
            self.iContRealisations.append(row[n_Landuses +4])
        #print self.contnames 
        #print self.compartments
        #print self.contrasternames 
        #print self.no_contaminants
        #print self.targets_LUT 
        #print self.boolConflictType
        #print self.iContRealisations 
        

if __name__ == "main":
    FILEPATH = "SzenarioA/ScALayout1.shp"
    A = LandUseShp(FILEPATH,"SzenarioA/ScALayout1/ScALayout1_bla.shp")
    A.addfield("Test")

#MAX TERMIN MONTAG 16:30 25.Juni


