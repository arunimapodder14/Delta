from fpdf import FPDF
from datetime import datetime
import io
class EcosystemReport(FPDF):
    def header(self):
        # Header banner
        self.set_font('Helvetica', 'B', 15)
        self.set_text_color(16, 130, 80)  # Dark Forest Green
        self.cell(0, 10, 'Blue Carbon Ecosystem Monitoring Report', border=0, ln=1, align='L')
        
        # Subtitle
        self.set_font('Helvetica', 'I', 9)
        self.set_text_color(100, 100, 100)
        self.cell(0, 5, 'Automated Satellite & AI Biophysical Synthesis', border=0, ln=1, align='L')
        
        # Divider line
        self.set_draw_color(16, 130, 80)
        self.set_line_width(0.5)
        self.line(10, 24, 200, 24)
        self.ln(8)
    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        # Position right-aligned page number
        self.cell(0, 10, f'Page {self.page_no()}/{{nb}}  |  Generated on {datetime.now().strftime("%Y-%m-%d %H:%M")}  |  Blue Carbon Monitoring Node', border=0, align='C')
def generate_pdf_report(project_name, analysis_data, carbon_data, project_meta=None):
    """
    Generates a structured, beautifully formatted PDF report containing ecosystem
    monitoring metrics, carbon stocks, health stress data, and alerts.
    Returns:
        bytes: Raw PDF file bytes to be served in Streamlit download button.
    """
    pdf = EcosystemReport()
    pdf.alias_nb_pages()
    pdf.add_page()
    
    # ----------------------------------------------------
    # SECTION 1: General Project Information
    # ----------------------------------------------------
    pdf.set_font('Helvetica', 'B', 12)
    pdf.set_text_color(30, 41, 59) # Slate 800
    pdf.cell(0, 8, '1. Project & Location Metadata', ln=1)
    
    pdf.set_font('Helvetica', '', 10)
    pdf.set_fill_color(248, 250, 252) # Slate 50
    
    # Render table-like metadata
    metadata = [
        ('Project Identifier:', project_name),
        ('Region Name:', analysis_data.get('location_name', 'Unknown')),
        ('Protected Area Size:', f"{analysis_data.get('area_ha', 0)} hectares (ha)"),
        ('Analysis Boundary:', 'Custom user-defined polygon (GeoJSON)')
    ]
    
    if project_meta:
        metadata.extend([
            ('Registry Standard:', project_meta.get('standard', 'N/A')),
            ('Trees Planted:', project_meta.get('trees', 'N/A')),
            ('Species Composition:', project_meta.get('species', 'N/A'))
        ])
    
    for label, val in metadata:
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(45, 6, f'  {label}', border=1, fill=True)
        pdf.set_font('Helvetica', '', 9)
        pdf.cell(145, 6, f' {val}', border=1, ln=1)
        
    pdf.ln(5)
    
    # ----------------------------------------------------
    # SECTION 2: Biomass & Carbon Stock Estimates
    # ----------------------------------------------------
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, '2. Biomass & Soil Carbon Accounting (AI Models)', ln=1)
    
    # Highlight box for Total CO2
    pdf.set_fill_color(240, 253, 244) # Green 50
    pdf.set_draw_color(187, 247, 208) # Green 200
    pdf.rect(10, pdf.get_y(), 190, 16, style='DF')
    
    pdf.set_font('Helvetica', 'B', 10)
    pdf.set_text_color(22, 101, 52) # Green 800
    pdf.cell(0, 8, f'  Estimated Total Carbon Stocks (CO2 Equivalent): {carbon_data.get("total_co2e_tons", 0):,} tCO2e', ln=1)
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f'  Average Carbon Density: {carbon_data.get("co2e_per_ha", 0):,} tCO2e/ha  |  Annual Carbon Capture: {carbon_data.get("annual_sequestration_tco2e", 0):,} tCO2e/yr', ln=1)
    pdf.ln(6)
    
    # Detail Carbon Pools Table
    pdf.set_text_color(30, 41, 59)
    pdf.set_draw_color(200, 200, 200)
    
    # Headers
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240) # Slate 200
    pdf.cell(60, 6, 'Carbon Reservoir Pool', border=1, fill=True)
    pdf.cell(65, 6, 'Estimated Carbon (tC)', border=1, fill=True)
    pdf.cell(65, 6, 'Percentage of Total (%)', border=1, ln=1, fill=True)
    
    # Rows
    agc = carbon_data.get('aboveground_carbon_tc', 0)
    bgc = carbon_data.get('belowground_carbon_tc', 0)
    soc = carbon_data.get('soil_organic_carbon_tc', 0)
    tot = carbon_data.get('total_carbon_tc', 1) # prevent zero division
    
    pools = [
        ('Aboveground Biomass (Trees, Branches)', agc, (agc/tot)*100),
        ('Belowground Biomass (Prop Roots, Rhizosphere)', bgc, (bgc/tot)*100),
        ('Soil Organic Carbon (Top 1-meter sediment)', soc, (soc/tot)*100),
    ]
    
    pdf.set_font('Helvetica', '', 9)
    for name, tc, pct in pools:
        pdf.cell(60, 6, f' {name}', border=1)
        pdf.cell(65, 6, f' {tc:,.1f} tC', border=1)
        pdf.cell(65, 6, f' {pct:.1f} %', border=1, ln=1)
        
    pdf.set_font('Helvetica', 'B', 9)
    pdf.cell(60, 6, ' Combined Pools Total', border=1)
    pdf.cell(65, 6, f' {tot:,.1f} tC', border=1)
    pdf.cell(65, 6, ' 100.0 %', border=1, ln=1)
    
    pdf.ln(5)
    
    # ----------------------------------------------------
    # SECTION 3: Biophysical Index Health Status
    # ----------------------------------------------------
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, '3. Biophysical Vegetation Index Dashboard', ln=1)
    
    pdf.set_font('Helvetica', '', 9)
    indices = [
        ('NDVI (Normalized Difference Vegetation Index)', f"{analysis_data.get('current_ndvi', 0):.3f}", 'Healthy density ranges between 0.65 and 0.85.'),
        ('NDWI (Normalized Difference Water Index)', f"{analysis_data.get('current_ndwi', 0):.3f}", 'Waterlogged wetland ranges between 0.20 and 0.50.'),
        ('Ecosystem ET Stress Index', f"{analysis_data.get('current_et_stress', 0):.2f}", '0.00 (Unstressed) to 1.00 (Severe Transpiration Blockage).')
    ]
    
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_fill_color(226, 232, 240)
    pdf.cell(75, 6, 'Index / Sensor metric', border=1, fill=True)
    pdf.cell(25, 6, 'Current Value', border=1, fill=True)
    pdf.cell(90, 6, 'Scientific Interpretation', border=1, ln=1, fill=True)
    
    pdf.set_font('Helvetica', '', 9)
    for label, val, desc in indices:
        pdf.cell(75, 6, f' {label}', border=1)
        pdf.cell(25, 6, f' {val}', border=1, align='C')
        pdf.cell(90, 6, f' {desc}', border=1, ln=1)
        
    pdf.ln(5)
    
    # ----------------------------------------------------
    # SECTION 4: Degradation & Forest Loss Alerts
    # ----------------------------------------------------
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 8, '4. Satellite Deforestation & Canopy Loss Alert Logs', ln=1)
    
    alerts = analysis_data.get('deforestation_alerts', [])
    
    if not alerts:
        pdf.set_font('Helvetica', 'I', 9.5)
        pdf.set_text_color(16, 120, 70)
        pdf.cell(0, 6, '  [OK] No active canopy loss or deforestation alerts detected in this area over the past 365 days.', ln=1)
        pdf.set_text_color(30, 41, 59)
    else:
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_fill_color(254, 226, 226) # Red 100
        pdf.set_text_color(153, 27, 27) # Red 800
        pdf.cell(30, 6, 'Date Identified', border=1, fill=True)
        pdf.cell(60, 6, 'GPS Coordinate (Lat, Lng)', border=1, fill=True)
        pdf.cell(50, 6, 'Estimated Canopy Loss', border=1, fill=True)
        pdf.cell(50, 6, 'Severity Rank', border=1, ln=1, fill=True)
        
        pdf.set_font('Helvetica', '', 9)
        pdf.set_text_color(30, 41, 59)
        for alt in alerts[:5]: # Display top 5 alerts
            pdf.cell(30, 6, f' {alt.get("date")}', border=1)
            pdf.cell(60, 6, f' {alt.get("latitude")}, {alt.get("longitude")}', border=1)
            pdf.cell(50, 6, f' {alt.get("area_loss_sqm"):,.1f} sqm', border=1)
            pdf.cell(50, 6, f' {alt.get("severity")}', border=1, ln=1)
            
        if len(alerts) > 5:
            pdf.set_font('Helvetica', 'I', 8)
            pdf.cell(0, 6, f'  * Note: {len(alerts) - 5} additional alerts are omitted from the executive PDF. View live portal for full logs.', ln=1)
            
    pdf.ln(8)
    
    # ----------------------------------------------------
    # SECTION 5: Research Disclaimer & Watermark
    # ----------------------------------------------------
    pdf.set_draw_color(16, 130, 80)
    pdf.set_fill_color(240, 253, 244)
    pdf.rect(10, pdf.get_y(), 190, 22, style='DF')
    
    pdf.set_y(pdf.get_y() + 2)
    pdf.set_font('Helvetica', 'B', 8.5)
    pdf.set_text_color(22, 101, 52)
    pdf.cell(0, 5, '  RESEARCH DISCLAIMER:', ln=1)
    pdf.set_font('Helvetica', '', 8)
    pdf.cell(0, 4, '  This report provides estimated data values based on public remote sensing and mathematical models (IPCC Guidelines).', ln=1)
    pdf.cell(0, 4, '  These metrics do not constitute official financial certifications or legally binding carbon credit verifications.', ln=1)
    
    # Output PDF stream
    pdf_buffer = io.BytesIO()
    pdf_out = pdf.output(dest='S')
    # In python-fpdf2, output(dest='S') returns a bytearray or byte string depending on version
    if isinstance(pdf_out, str):
        pdf_buffer.write(pdf_out.encode('latin1'))
    else:
        pdf_buffer.write(pdf_out)
        
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()
