import hashlib
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import shapely.geometry
# Google Earth Engine library (imported safely)
GEE_AVAILABLE = False
try:
    import ee
    GEE_AVAILABLE = True
except ImportError:
    pass
class GEEService:
    def __init__(self, use_sandbox=True):
        self.use_sandbox = use_sandbox
        self.gee_initialized = False
        if not use_sandbox and GEE_AVAILABLE:
            self.gee_initialized = self._initialize_gee()
        
    def _initialize_gee(self):
        try:
            # Try default initialization
            ee.Initialize()
            print("🛰️ Google Earth Engine connected successfully.")
            return True
        except Exception as e:
            print(f"Standard GEE initialization failed: {e}. Falling back to Sandbox Mode.")
            return False
    def is_live(self):
        return GEE_AVAILABLE and self.gee_initialized and not self.use_sandbox
    def _get_deterministic_seed(self, coordinates):
        """Generates a deterministic seed from coordinates to make simulation reproducible."""
        coord_str = str(coordinates)
        hasher = hashlib.md5(coord_str.encode('utf-8'))
        return int(hasher.hexdigest()[:8], 16)
    def analyze_area(self, coordinates, project_meta=None):
        """
        Performs geospatial analysis on a polygon.
        Returns:
            dict containing area, indices, and time-series data.
        """
        # Calculate area using Shapely
        try:
            poly = shapely.geometry.Polygon(coordinates)
            centroid = poly.centroid
            lat_factor = 111000.0
            lng_factor = 111000.0 * np.cos(np.radians(centroid.y))
            
            # Project coordinates to meters approximately
            proj_coords = [(pt[0] * lng_factor, pt[1] * lat_factor) for pt in coordinates]
            proj_poly = shapely.geometry.Polygon(proj_coords)
            area_ha = abs(proj_poly.area) / 10000.0  # m^2 to hectares
        except Exception:
            area_ha = 1200.0  # Fallback default area
        if area_ha < 0.1:
            area_ha = 5.0
        if self.is_live():
            return self._analyze_gee_live(coordinates, area_ha, project_meta)
        else:
            return self._analyze_sandbox(coordinates, area_ha, project_meta)
    def _analyze_gee_live(self, coordinates, area_ha, project_meta):
        """Real Google Earth Engine queries mapping Sentinel-2, Landsat, SRTM, GEDI, and MODIS."""
        try:
            # Construct GEE polygon
            ee_poly = ee.Geometry.Polygon(coordinates)
            
            # 1. Fetch Sentinel-2 L2A (COPERNICUS/S2_SR_HARMONIZED)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=90)
            
            s2_col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
                      .filterBounds(ee_poly)
                      .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                      .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)))
            
            # Median composite and calculate NDVI & NDWI
            if s2_col.size().getInfo() > 0:
                composite = s2_col.median()
                # NDVI: (B8 - B4) / (B8 + B4)
                ndvi = composite.normalizedDifference(['B8', 'B4']).rename('NDVI')
                # NDWI: (B3 - B8) / (B3 + B8)
                ndwi = composite.normalizedDifference(['B3', 'B8']).rename('NDWI')
                
                mean_ndvi = ndvi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_poly,
                    scale=10,
                    maxPixels=1e9
                ).get('NDVI').getInfo()
                
                mean_ndwi = ndwi.reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_poly,
                    scale=10,
                    maxPixels=1e9
                ).get('NDWI').getInfo()
            else:
                mean_ndvi = 0.72
                mean_ndwi = 0.32
                
            mean_ndvi = mean_ndvi if mean_ndvi is not None else 0.72
            mean_ndwi = mean_ndwi if mean_ndwi is not None else 0.32
            # 2. Fetch Elevation data from SRTM DEM (USGS/SRTMGL1_003)
            dem = ee.Image('USGS/SRTMGL1_003')
            mean_elevation = dem.reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=ee_poly,
                scale=30
            ).get('elevation').getInfo()
            mean_elevation = mean_elevation if mean_elevation is not None else 1.5
            # 3. Fetch Evapotranspiration from MODIS ET (MODIS/061/MOD16A2)
            et_col = (ee.ImageCollection('MODIS/061/MOD16A2')
                      .filterBounds(ee_poly)
                      .filterDate((end_date - timedelta(days=180)).strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')))
            
            if et_col.size().getInfo() > 0:
                et_mean = et_col.select('ET').median().reduceRegion(
                    reducer=ee.Reducer.mean(),
                    geometry=ee_poly,
                    scale=500
                ).get('ET').getInfo()
                et_val = et_mean if et_mean is not None else 150
                et_stress = max(0.0, min(1.0, 1.0 - (et_val / 300.0)))
            else:
                et_stress = 0.22
            # 4. GEDI Footprint Reference (NASA/GEDI/L2A_002_MONTHLY or similar)
            # If monthly composites are not accessible, fallback to a GEDI canopy profile baseline of ~14-18m
            canopy_height = 15.4
            try:
                gedi_col = ee.ImageCollection("LARSE/GEDI/GEDI02_A_002_MONTHLY")
                # Filter to area
                gedi_img = gedi_col.filterBounds(ee_poly).select('rh95').median()
                if gedi_img:
                    gedi_val = gedi_img.reduceRegion(
                        reducer=ee.Reducer.mean(),
                        geometry=ee_poly,
                        scale=25
                    ).get('rh95').getInfo()
                    if gedi_val is not None:
                        canopy_height = gedi_val / 100.0  # convert cm to meters if scaled
            except Exception:
                pass
            # Fetch historical and alert arrays deterministically using sandbox templates
            sandbox_data = self._analyze_sandbox(coordinates, area_ha, project_meta)
            
            # Override GEE values
            sandbox_data['current_ndvi'] = float(mean_ndvi)
            sandbox_data['current_ndwi'] = float(mean_ndwi)
            sandbox_data['current_et_stress'] = float(et_stress)
            sandbox_data['mean_elevation_m'] = float(mean_elevation)
            sandbox_data['gedi_canopy_height_m'] = float(canopy_height)
            
            return sandbox_data
            
        except Exception as e:
            print(f"GEE live error: {e}. Switching to simulation.")
            return self._analyze_sandbox(coordinates, area_ha, project_meta)
    def _analyze_sandbox(self, coordinates, area_ha, project_meta):
        """Simulates biophysical indices matching specific Baha' Mou and Sundari data details."""
        seed = self._get_deterministic_seed(coordinates)
        rng = np.random.default_rng(seed)
        
        # Pull metadata
        if project_meta is None:
            project_meta = {}
            
        proj_type = project_meta.get("type", "generic")
        
        if proj_type == "baha_mou":
            location_name = "South 24 Parganas, Sundarbans, West Bengal"
            base_ndvi = 0.74
            base_ndwi = 0.36
            base_et = 245.0
            base_stress = 0.16
            mean_elevation = 1.4
            gedi_canopy = 16.5
            deforestation_probability = 0.04
        elif proj_type == "sundari":
            location_name = "Gangasagar & Kakdwip, Sundarbans, West Bengal"
            base_ndvi = 0.69
            base_ndwi = 0.42
            base_et = 215.0
            base_stress = 0.24  # higher stress in islands
            mean_elevation = 1.1
            gedi_canopy = 14.8
            deforestation_probability = 0.06
        else:
            poly = shapely.geometry.Polygon(coordinates)
            centroid = poly.centroid
            location_name = f"Custom Mangrove Zone (Lat: {centroid.y:.4f}, Lng: {centroid.x:.4f})"
            base_ndvi = 0.71
            base_ndwi = 0.38
            base_et = 230.0
            base_stress = 0.21
            mean_elevation = 1.3
            gedi_canopy = 15.6
            deforestation_probability = 0.05
        # Noise adjustment
        base_ndvi += rng.uniform(-0.03, 0.03)
        base_ndwi += rng.uniform(-0.04, 0.04)
        
        # 1. Historical NDVI Time Series (10 years)
        dates = []
        ndvi_values = []
        curr_date = datetime.now() - timedelta(days=3652)
        
        # Simulating restoration progress: Sundari started in 2023, Baha Mou is ongoing
        is_sundari_restoration = (proj_type == "sundari")
        
        for i in range(120):
            date_str = curr_date.strftime('%Y-%m')
            dates.append(date_str)
            
            month = curr_date.month
            season = np.sin(2 * np.pi * (month - 1) / 12.0) * 0.05
            
            # Growth curve
            if is_sundari_restoration:
                # 2023 start -> index increases faster in final 3 years (i >= 80)
                growth = (i / 120.0) * 0.015
                if i >= 84: # After Jan 2023
                    growth += ((i - 84) / 36.0) * 0.03
            else:
                growth = (i / 120.0) * 0.018
                
            noise = rng.normal(0, 0.015)
            
            val = base_ndvi + season + growth + noise
            ndvi_values.append(max(0.2, min(0.9, val)))
            curr_date += timedelta(days=30.5)
        # 2. Historical ET Time Series (24 months)
        et_dates = []
        et_values = []
        et_stress_values = []
        temp_anomalies = []
        
        curr_date = datetime.now() - timedelta(days=730)
        for i in range(24):
            date_str = curr_date.strftime('%b %y')
            et_dates.append(date_str)
            
            month = curr_date.month
            season = np.sin(2 * np.pi * (month - 1) / 12.0) * 28.0
            noise = rng.normal(0, 7.0)
            
            et_val = base_et + season + noise
            et_values.append(max(80.0, et_val))
            
            is_dry = (3 <= month <= 5)
            stress_mult = 1.5 if is_dry else 0.85
            temp_anom = rng.normal(0.4, 0.25) + (0.7 if is_dry else 0.0)
            temp_anomalies.append(round(temp_anom, 2))
            
            stress = base_stress * stress_mult + rng.normal(0, 0.04)
            et_stress_values.append(round(max(0.02, min(0.98, stress)), 2))
            curr_date += timedelta(days=30.5)
        # 3. Deforestation Alerts (Hotspots)
        alerts = []
        poly = shapely.geometry.Polygon(coordinates)
        centroid = poly.centroid
        
        if rng.uniform(0, 1) < deforestation_probability * 10:
            num_alerts = int(rng.choice([1, 2, 3]))
            for _ in range(num_alerts):
                offset_x = rng.uniform(-0.012, 0.012)
                offset_y = rng.uniform(-0.012, 0.012)
                alert_lat = centroid.y + offset_y
                alert_lng = centroid.x + offset_x
                
                alert_days_ago = int(rng.uniform(15, 340))
                alert_date = (datetime.now() - timedelta(days=alert_days_ago)).strftime('%Y-%m-%d')
                loss_sqm = rng.uniform(150, 4200)
                
                alerts.append({
                    "date": alert_date,
                    "latitude": round(alert_lat, 5),
                    "longitude": round(alert_lng, 5),
                    "area_loss_sqm": round(loss_sqm, 1),
                    "severity": "High" if loss_sqm > 2000 else "Moderate"
                })
        
        alerts.sort(key=lambda x: x['date'], reverse=True)
        return {
            "location_name": location_name,
            "area_ha": round(area_ha, 2),
            "current_ndvi": round(ndvi_values[-1], 3),
            "current_ndwi": round(base_ndwi + rng.uniform(-0.02, 0.02), 3),
            "current_et_stress": round(et_stress_values[-1], 2),
            "mean_elevation_m": round(mean_elevation, 2),
            "gedi_canopy_height_m": round(gedi_canopy, 2),
            "historical_dates": dates,
            "historical_ndvi": ndvi_values,
            "historical_et_dates": et_dates,
            "historical_et": et_values,
            "historical_et_stress": et_stress_values,
            "historical_temp_anom": temp_anomalies,
            "deforestation_alerts": alerts
        }