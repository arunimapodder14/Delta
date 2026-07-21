import numpy as np
from sklearn.ensemble import RandomForestRegressor


class BiomassModel:
    def __init__(self):
        self.model = self._train_model()

    def _train_model(self):
        """
        Trains a quick Random Forest regressor on synthetic calibration data that maps
        optical vegetation indices and elevation to GEDI LiDAR canopy heights.
        Done at runtime for self-contained, zero-dependency model instantiation.

        NOTE: This model is used only as a FALLBACK when real GEDI L4A biomass
        measurements are not available for a given polygon (e.g. no GEDI footprint
        fell inside the drawn area). Whenever real measured data is available,
        predict_biomass_and_carbon() uses it directly instead of this model.
        """
        # Features: [NDVI, NDWI, EVI, Elevation_m]
        # Target: GEDI Canopy Height (meters)
        rng = np.random.default_rng(42)
        n_samples = 800

        # Synthesize realistic features
        ndvi = rng.uniform(0.1, 0.85, n_samples)
        ndwi = rng.uniform(-0.2, 0.6, n_samples)
        # EVI generally tracks NDVI but is less saturated
        evi = ndvi * 0.85 + rng.normal(0, 0.05, n_samples)
        # Coastal mangroves grow at low elevations (0 to 10m)
        elevation = rng.uniform(0, 8.0, n_samples)

        X = np.stack([ndvi, ndwi, evi, elevation], axis=1)

        # Target formula: Higher canopy height with high NDVI, high NDWI (waterlogging), low elevation
        height = (12.0 * ndvi) + (6.0 * ndwi) - (0.4 * elevation) + 5.0
        # Add forestry noise
        height += rng.normal(0, 1.2, n_samples)
        height = np.clip(height, 1.5, 35.0)  # Mangroves range from dwarf (1.5m) to tall riverine (35m)

        # Train Random Forest Regressor
        rf = RandomForestRegressor(n_estimators=40, random_state=42)
        rf.fit(X, height)
        return rf

    def predict_biomass_and_carbon(self, ndvi, ndwi, area_ha, real_agbd_per_ha=None):
        """
        Predicts Aboveground Biomass (AGB) and estimates soil & belowground carbon.

        Args:
            ndvi: current NDVI index for the polygon
            ndwi: current NDWI index for the polygon
            area_ha: polygon area in hectares
            real_agbd_per_ha: optional real GEDI L4A measured Aboveground Biomass
                Density (Mg/ha) for this polygon. When provided, this is used
                directly instead of the fallback model prediction.

        Returns:
            dict containing carbon metrics for the polygon, including a
            "data_source" field indicating whether values came from real
            GEDI measurement ("gedi_measured") or the fallback allometric
            model ("allometric_estimate").
        """
        if real_agbd_per_ha is not None:
            # Real satellite-lidar-measured biomass is available — use it directly.
            agb_per_ha = real_agbd_per_ha
            predicted_height_m = None  # not modeled when using a direct measurement
            data_source = "gedi_measured"
        else:
            # No real measurement available for this polygon — fall back to the
            # NDVI/NDWI-based model prediction.
            evi = ndvi * 0.85
            elevation = 1.5  # standard delta elevation assumption for fallback case
            features = np.array([[ndvi, ndwi, evi, elevation]])

            # 1. Predict canopy height (m) using Random Forest model
            predicted_height_m = float(self.model.predict(features)[0])

            # 2. Convert Canopy Height to Aboveground Biomass (AGB) in Megagrams per hectare (Mg/ha)
            # Standard tropical mangrove allometry (e.g., Simard et al., AGB = 5.66 * Height + 12.0)
            agb_per_ha = (5.66 * predicted_height_m) + 12.0
            data_source = "allometric_estimate"

        total_agb = agb_per_ha * area_ha

        # 3. Calculate Aboveground Carbon (AGC)
        # IPCC standard carbon fraction of biomass is 0.47
        agc_per_ha = agb_per_ha * 0.47
        total_agc = agc_per_ha * area_ha

        # 4. Calculate Belowground Carbon (BGC) (Roots)
        # Root-to-shoot carbon ratio calibrated from Indian Sundarbans field study
        # (AGB:BGB ratio of 2.07 -> BGC/AGC ratio of ~0.483)
        bgc_per_ha = agc_per_ha * 0.483
        total_bgc = bgc_per_ha * area_ha

        # 5. Soil Organic Carbon (SOC) (up to 1m depth)
        # Mangrove soils are carbon sinks. They store ~200 - 800 Mg C / ha.
        # Deep organic soil stores more when waterlogged (higher NDWI).
        soc_per_ha = 320.0 + (350.0 * max(0.0, ndwi))
        total_soc = soc_per_ha * area_ha

        # 6. Sum Total Organic Carbon (TOC) in tons of Carbon (tC)
        total_carbon_tc = total_agc + total_bgc + total_soc
        carbon_per_ha = total_carbon_tc / area_ha

        # 7. Convert Carbon to Carbon Dioxide Equivalent (tCO2e)
        # 1 ton of Carbon = 3.67 tons of CO2 (molecular weight ratio 44/12)
        total_co2e = total_carbon_tc * 3.67
        co2e_per_ha = carbon_per_ha * 3.67

        # 8. Annual carbon sequestration capacity (tCO2e / year)
        # Healthy growing mangroves sequester ~6 to 15 tons of CO2e per hectare per year.
        sequestration_rate_per_ha_yr = 8.5 * ndvi
        total_sequestration_yr = sequestration_rate_per_ha_yr * area_ha

        return {
            "data_source": data_source,
            "canopy_height_m": round(predicted_height_m, 2) if predicted_height_m is not None else None,
            "agb_per_ha": round(agb_per_ha, 1),
            "total_agb_tons": round(total_agb, 1),

            "aboveground_carbon_tc": round(total_agc, 1),
            "belowground_carbon_tc": round(total_bgc, 1),
            "soil_organic_carbon_tc": round(total_soc, 1),

            "total_carbon_tc": round(total_carbon_tc, 1),
            "carbon_per_ha": round(carbon_per_ha, 1),

            "total_co2e_tons": round(total_co2e, 1),
            "co2e_per_ha": round(co2e_per_ha, 1),

            "annual_sequestration_tco2e": round(total_sequestration_yr, 1),
            "sequestration_rate_per_ha": round(sequestration_rate_per_ha_yr, 2)
        }