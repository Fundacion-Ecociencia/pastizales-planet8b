import arcpy
from arcpy.sa import *
import os

# Habilitar extensiones
arcpy.env.overwriteOutput = True
arcpy.CheckOutExtension("Spatial")

# Rutas

input_fc = arcpy.GetParameterAsText(0)
output_fc = arcpy.GetParameterAsText(1)

arcpy.AddMessage("Inicio de la identificación")


# Validar carpeta de salida
if not os.path.exists(output_fc):
    os.makedirs(output_fc)

# Cargar raster
raster = arcpy.Raster(input_fc)

# Extraer bandas necesarias
green = ExtractBand(raster, 3)      # Banda 3 = Green
red = ExtractBand(raster, 4)        # Banda 4 = Red
redEdge = ExtractBand(raster, 7)    # Banda 7 = RedEdge
nir = ExtractBand(raster, 8)        # Banda 8 = NIR

# Calcular índices
ndvi = (nir - red) / (nir + red)
ndvi.save(os.path.join(output_fc, "NDVI.tif"))

ndre = (nir - redEdge) / (nir + redEdge)
ndre.save(os.path.join(output_fc, "NDRE.tif"))

ndwi = (green - nir) / (green + nir)
ndwi.save(os.path.join(output_fc, "NDWI.tif"))

# Generar máscaras para agua (NDWI > 0) y bosque (NDVI > 0.6)
agua = SetNull(ndwi <= 0, 1)
bosque = SetNull(ndvi <= 0.6, 1)

# Guardar máscaras
arcpy.CopyRaster_management(agua, os.path.join(output_fc, "agua.tif"))
arcpy.CopyRaster_management(bosque, os.path.join(output_fc, "bosque.tif"))

# Obtener estadísticas NDRE
min_ndre = float(arcpy.GetRasterProperties_management(ndre, "MINIMUM").getOutput(0).replace(",", "."))
max_ndre = float(arcpy.GetRasterProperties_management(ndre, "MAXIMUM").getOutput(0).replace(",", "."))
media_ndre = float(arcpy.GetRasterProperties_management(ndre, "MEAN").getOutput(0).replace(",", "."))

arcpy.AddMessage(f"NDRE stats -> Min: {min_ndre:.3f}, Mean: {media_ndre:.3f}, Max: {max_ndre:.3f}")

# Clasificación NDRE con clases fuera del umbral 0.41 - 0.59
remap_ndre = RemapRange([
    [min_ndre, 0.41, 1],   # Clase 1: NDRE bajo (< 0.41)
    [0.41, 0.45, 2],       # Clase 2: Bajo-medio
    [0.45, 0.50, 3],       # Clase 3: Medio ← Posible clase de pastizal
    [0.50, 0.55, 4],       # Clase 4: Medio-alto ← Posible clase de pastizal
    [0.55, 0.59, 5],       # Clase 5: Alto
    [0.59, max_ndre, 6]    # Clase 6: NDRE muy alto (> 0.59)
])

# Aplicar reclasificación
ndre_clasificado = Reclassify(ndre, "VALUE", remap_ndre)
arcpy.CopyRaster_management(ndre_clasificado, os.path.join(output_fc, "NDRE_clasificado.tif"))

# === EXPORTAR SOLO CLASE DE PASTIZALES ENTRE 0.41 Y 0.59 ===
# Crear máscara NDRE entre 0.41 y 0.59
pastizales_mask = SetNull((ndre < 0.41) | (ndre > 0.59), 1)
pastizales_raster = os.path.join(output_fc, "NDRE_pastizales.tif")
pastizales_mask.save(pastizales_raster)

# === CONVERTIR RASTER DE PASTIZALES A POLÍGONO ===
pastizales_vector = os.path.join(output_fc, "NDRE_pastizales.shp")
arcpy.RasterToPolygon_conversion(
    in_raster=pastizales_raster,
    out_polygon_features=pastizales_vector,
    simplify="NO_SIMPLIFY",
    raster_field="Value"
)

# === FILTRAR POLÍGONOS < 0.16 ha (1600 m²) ===
# Agregar campo de área en m²
arcpy.AddField_management(pastizales_vector, "AREA_M2", "DOUBLE")
arcpy.CalculateGeometryAttributes_management(
    pastizales_vector,
    [["AREA_M2", "AREA"]],
    area_unit="SQUARE_METERS"
)

# Crear capa temporal para filtrar
temp_layer = "pastizales_layer"
arcpy.MakeFeatureLayer_management(pastizales_vector, temp_layer)

# Seleccionar polígonos menores a 1600 m²
arcpy.SelectLayerByAttribute_management(temp_layer, "NEW_SELECTION", '"AREA_M2" < 1600')

# Eliminar polígonos pequeños
arcpy.DeleteFeatures_management(temp_layer)

# Guardar cambios y limpiar
arcpy.Delete_management(temp_layer)


# === AGREGAR VECTOR AL MAPA ACTUAL DE ARCGIS PRO ===
aprx = arcpy.mp.ArcGISProject("CURRENT")
mapa = aprx.activeMap
mapa.addDataFromPath(pastizales_vector)
arcpy.AddMessage("Shapefile de pastizales agregado al mapa.")


# Finalizar
arcpy.CheckInExtension("Spatial")
arcpy.AddMessage("Proceso completado con éxito. Raster y vector filtrados generados.")

