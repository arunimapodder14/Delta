from gee_service import GEEService
from biomass_ml import BiomassModel
from pdf_report import generate_pdf_report
def test_pipeline():
    print("Initializing services...")
    gee = GEEService(use_sandbox=True)
    biomass = BiomassModel()
    
    # Test coordinates
    coords = [[88.85, 21.90], [89.05, 21.90], [89.05, 22.05], [88.85, 22.05], [88.85, 21.90]]
    
    print("Running GEE Sandbox analyzer...")
    analysis = gee.analyze_area(coords)
    assert analysis['area_ha'] > 0, "Area calculation failed"
    assert 0.0 <= analysis['current_ndvi'] <= 1.0, "NDVI index out of range"
    print(f"  [OK] Location detected: {analysis.get('location_name')}")
    print(f"  [OK] Area: {analysis['area_ha']} ha, NDVI: {analysis['current_ndvi']}")
    
    print("Running ML Biomass model...")
    carbon = biomass.predict_biomass_and_carbon(
        analysis['current_ndvi'], 
        analysis['current_ndwi'], 
        analysis['area_ha']
    )
    assert carbon['total_carbon_tc'] > 0, "Carbon stock calculation failed"
    assert carbon['total_co2e_tons'] > 0, "CO2 equivalent calculation failed"
    print(f"  [OK] Predicted Canopy Height: {carbon['canopy_height_m']} m")
    print(f"  [OK] Total Carbon Stock: {carbon['total_carbon_tc']:,} tC")
    print(f"  [OK] CO2 Equivalent: {carbon['total_co2e_tons']:,} tCO2e")
    
    print("Running PDF Report compiler...")
    mock_meta = {
        "type": "baha_mou",
        "standard": "Verified Carbon Standard (VCS)",
        "trees": "12 Million",
        "species": "14 native species"
    }
    pdf_bytes = generate_pdf_report("Test Site", analysis, carbon, mock_meta)
    assert len(pdf_bytes) > 0, "PDF generation resulted in empty output"
    print(f"  [OK] PDF compilation successfully wrote {len(pdf_bytes)} bytes")
    
    print("\n[SUCCESS] All pipeline checks passed successfully!")
if __name__ == "__main__":
    test_pipeline()
