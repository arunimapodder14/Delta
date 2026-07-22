"""
train_biomass_model.py

ONE-TIME, OFFLINE training script - run this manually from the terminal:

    python train_biomass_model.py

This is NOT part of the live Streamlit app. It:
  1. Fetches REAL GEDI L4A biomass footprints across a wide Sundarbans
     bounding box (India + Bangladesh side - same continuous mangrove
     ecosystem), not just the two demo project sites.
  2. Samples REAL Sentinel-2 NDVI/NDWI/EVI, SRTM elevation, AND real GEDI L2A
     canopy height at each of those footprint locations, along with real
     lat/lng. Canopy height is included because it does not suffer from the
     optical-index saturation problem that limits NDVI/NDWI/EVI alone at
     high vegetation density.
  3. Trains a GradientBoostingRegressor to predict biomass (Mg/ha) DIRECTLY
     from those 5 real features.
  4. Evaluates using a SPATIAL BLOCK split (not a random split) - nearby
     points are grouped into geographic blocks, and whole blocks are held
     out for testing, giving a more honest accuracy estimate than a random
     split would.
  5. Saves the trained model to mangrove_biomass_model.pkl, which
     biomass_ml.py loads at app startup instead of retraining every launch.

Requires: earthengine-api, scikit-learn, joblib, numpy
"""

import ee
import numpy as np
import joblib
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import r2_score, mean_absolute_error

# ----------------------------------------------------
# CONFIG
# ----------------------------------------------------
GEE_PROJECT = 'delta-carbon-project'
MODEL_OUTPUT_PATH = 'mangrove_biomass_model.pkl'
NUM_SAMPLES = 30000          # attempted draws (many get filtered by mask overlap)
RANDOM_STATE = 42
SPATIAL_BLOCK_SIZE_DEG = 0.15   # ~15km blocks for the spatial train/test split
TEST_BLOCK_FRACTION = 0.25      # fraction of spatial blocks held out for testing

# Feature order - MUST match the order used in biomass_ml.py at inference time.
FEATURE_NAMES = ['ndvi', 'ndwi', 'evi', 'elevation', 'canopy_height']


def spatial_block_split(lats, lngs, block_size_deg, test_fraction, seed):
    """
    Groups points into geographic grid blocks, then holds out entire blocks
    for testing (not individual points). This prevents spatially-adjacent
    points from leaking across the train/test boundary, which would
    otherwise inflate accuracy metrics artificially.

    Returns (train_indices, test_indices, n_blocks, n_test_blocks).
    """
    rng = np.random.default_rng(seed)

    block_ids = [
        (int(np.floor(lat / block_size_deg)), int(np.floor(lng / block_size_deg)))
        for lat, lng in zip(lats, lngs)
    ]
    unique_blocks = list(set(block_ids))
    rng.shuffle(unique_blocks)

    n_test_blocks = max(1, int(len(unique_blocks) * test_fraction))
    test_blocks = set(unique_blocks[:n_test_blocks])

    train_idx, test_idx = [], []
    for i, bid in enumerate(block_ids):
        if bid in test_blocks:
            test_idx.append(i)
        else:
            train_idx.append(i)

    return np.array(train_idx), np.array(test_idx), len(unique_blocks), len(test_blocks)


def main():
    print("Initializing Earth Engine...")
    ee.Initialize(project=GEE_PROJECT)
    print("Connected.\n")

    SUNDARBANS_REGION = ee.Geometry.Rectangle([88.00, 21.40, 89.90, 22.60])

    print("Building real GEDI L4A biomass layer (quality-masked)...")
    gedi_agbd = (ee.ImageCollection('LARSE/GEDI/GEDI04_A_002_MONTHLY')
                 .filterBounds(SUNDARBANS_REGION)
                 .map(lambda img: img.updateMask(img.select('l4_quality_flag').eq(1))
                                     .updateMask(img.select('degrade_flag').eq(0)))
                 .select('agbd')
                 .mean()
                 .rename('agbd'))

    print("Building real GEDI L2A canopy height layer (rh95)...")
    gedi_height = (ee.ImageCollection('LARSE/GEDI/GEDI02_A_002_MONTHLY')
                   .filterBounds(SUNDARBANS_REGION)
                   .select('rh95')
                   .mean()
                   .rename('canopy_height'))

    print("Building real Sentinel-2 NDVI/NDWI/EVI composite (last 4 years, all seasons)...")
    s2_col = (ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
              .filterBounds(SUNDARBANS_REGION)
              .filterDate('2022-01-01', '2026-01-01')
              .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 60)))

    s2_composite = s2_col.median()
    ndvi = s2_composite.normalizedDifference(['B8', 'B4']).rename('ndvi')
    ndwi = s2_composite.normalizedDifference(['B3', 'B8']).rename('ndwi')
    evi = s2_composite.expression(
        '2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))',
        {
            'NIR': s2_composite.select('B8'),
            'RED': s2_composite.select('B4'),
            'BLUE': s2_composite.select('B2'),
        }
    ).rename('evi')

    print("Building real SRTM elevation layer...")
    elevation = ee.Image('USGS/SRTMGL1_003').select('elevation').rename('elevation')

    print("Stacking bands and sampling at real GEDI footprint locations...\n")
    combined = (gedi_agbd
                .addBands(ndvi)
                .addBands(ndwi)
                .addBands(evi)
                .addBands(elevation)
                .addBands(gedi_height)
                .updateMask(gedi_agbd.mask())
                .updateMask(gedi_height.mask()))  # require both real AGBD and real height at each point

    samples_fc = combined.sample(
        region=SUNDARBANS_REGION,
        scale=25,
        numPixels=NUM_SAMPLES,
        seed=RANDOM_STATE,
        geometries=True,
        tileScale=4
    )

    print("Retrieving sampled data from Earth Engine (this may take a minute)...")
    sample_list = samples_fc.getInfo()['features']
    print(f"Retrieved {len(sample_list)} raw samples.\n")

    X_rows, y_rows, lat_rows, lng_rows = [], [], [], []
    for feat in sample_list:
        props = feat['properties']
        required = ['agbd', 'ndvi', 'ndwi', 'evi', 'elevation', 'canopy_height']
        if all(props.get(k) is not None for k in required):
            X_rows.append([
                props['ndvi'], props['ndwi'], props['evi'],
                props['elevation'], props['canopy_height']
            ])
            y_rows.append(props['agbd'])
            coords = feat['geometry']['coordinates']
            lng_rows.append(coords[0])
            lat_rows.append(coords[1])

    X = np.array(X_rows)
    y = np.array(y_rows)
    lats = np.array(lat_rows)
    lngs = np.array(lng_rows)

    print(f"Valid samples after filtering (requires real AGBD + real canopy height): {len(y)}")
    if len(y) < 30:
        print("WARNING: fewer than 30 valid samples - model quality will be unreliable. "
              "Note: requiring real canopy height too will reduce sample count vs. before, "
              "since it adds a second sparse GEDI layer to intersect against.")
    print(f"Biomass (agbd) range in samples: {y.min():.1f} - {y.max():.1f} Mg/ha\n")

    print("Splitting into train/test sets using SPATIAL BLOCKS (not random split)...")
    train_idx, test_idx, n_blocks, n_test_blocks = spatial_block_split(
        lats, lngs, SPATIAL_BLOCK_SIZE_DEG, TEST_BLOCK_FRACTION, RANDOM_STATE
    )
    print(f"Total spatial blocks: {n_blocks} | Held out for testing: {n_test_blocks}")
    print(f"Train points: {len(train_idx)} | Test points: {len(test_idx)}\n")

    if len(test_idx) < 5:
        print("WARNING: very few test points after spatial split - accuracy numbers below "
              "will be noisy.")

    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]

    print(f"Training GradientBoostingRegressor on REAL data (features: {FEATURE_NAMES})...")
    gbr = GradientBoostingRegressor(
        n_estimators=150,
        max_depth=3,
        learning_rate=0.05,
        random_state=RANDOM_STATE
    )
    gbr.fit(X_train, y_train)

    print("\n--- Validation Results (spatial held-out block test set) ---")
    predictions = gbr.predict(X_test)
    r2 = r2_score(y_test, predictions)
    mae = mean_absolute_error(y_test, predictions)
    print(f"R^2 score: {r2:.3f}")
    print(f"MAE:       {mae:.2f} Mg/ha")

    print("\nFeature importances:")
    for name, importance in zip(FEATURE_NAMES, gbr.feature_importances_):
        print(f"  {name:15s}: {importance:.3f}")

    print("\nSample predictions vs actual (up to 5 held-out points):")
    for pred, actual in list(zip(predictions, y_test))[:5]:
        print(f"  Predicted: {pred:7.1f} Mg/ha  |  Actual: {actual:7.1f} Mg/ha")

    out_of_range = np.sum((predictions < 15) | (predictions > 300))
    print(f"\nPredictions outside plausible Sundarbans mangrove AGB range (15-300 Mg/ha): "
          f"{out_of_range}/{len(predictions)}")

    print(f"\nSaving trained model to {MODEL_OUTPUT_PATH} ...")
    joblib.dump(gbr, MODEL_OUTPUT_PATH)
    print("Done. biomass_ml.py will load this file automatically on next app launch.")


if __name__ == "__main__":
    main()