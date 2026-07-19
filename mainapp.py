import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
# Import local modules
from gee_service import GEEService
from biomass_ml import BiomassModel
from pdf_report import generate_pdf_report
# ----------------------------------------------------
# STREAMLIT CONFIGURATION & CUSTOM THEME INJECTION
# ----------------------------------------------------
st.set_page_config(
    page_title="Blue Carbon Ecosystem Monitor",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)
# Inject custom CSS for premium Glassmorphic Dark UI
st.markdown("""
<style>
    /* Google Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=Plus+Jakarta+Sans:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    
    /* Background colors */
    .stApp {
        background: radial-gradient(circle at 10% 20%, #0d1527 0%, #070913 90%);
        color: #e2e8f0;
    }
    
    /* Custom metric card wrapper styling */
    div[data-testid="stMetric"] {
        background: rgba(15, 23, 42, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 8px 24px 0 rgba(0, 0, 0, 0.25);
        backdrop-filter: blur(8px);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: rgba(16, 185, 129, 0.3);
    }
    
    /* Labels and values color override */
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
        font-size: 0.85rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    div[data-testid="stMetricValue"] {
        color: #10b981 !important;
        font-family: 'Outfit', sans-serif;
        font-weight: 600;
        font-size: 1.8rem !important;
    }
    
    /* Styling headers */
    h1, h2, h3 {
        font-family: 'Outfit', sans-serif;
        font-weight: 700;
    }
    
    /* Glowing main title */
    .main-title {
        background: linear-gradient(135deg, #10b981 30%, #3b82f6 90%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 2.8rem;
        font-weight: 700;
        margin-bottom: 5px;
    }
    
    /* Custom info boxes */
    .info-box {
        background: rgba(59, 130, 246, 0.1);
        border: 1px solid rgba(59, 130, 246, 0.2);
        border-radius: 8px;
        padding: 12px 16px;
        color: #93c5fd;
        font-size: 0.9rem;
        margin-bottom: 20px;
    }
    
    /* Active tabs indicators */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: rgba(15, 23, 42, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 8px 8px 0px 0px;
        color: #94a3b8;
        padding: 8px 16px;
    }
    .stTabs [aria-selected="true"] {
        background-color: rgba(16, 185, 129, 0.15) !important;
        border-color: rgba(16, 185, 129, 0.3) !important;
        color: #10b981 !important;
    }
</style>
""", unsafe_allow_html=True)
# ----------------------------------------------------
# CONSTANTS & LOCATION TEMPLATES
# ----------------------------------------------------
BAHA_MOU_COORDS = [[88.83, 21.84], [88.86, 21.84], [88.86, 21.87], [88.83, 21.87], [88.83, 21.84]]
SUNDARI_COORDS = [[88.10, 21.70], [88.16, 21.70], [88.16, 21.76], [88.10, 21.76], [88.10, 21.70]]
# ----------------------------------------------------
# INITIALIZE SESSION STATE
# ----------------------------------------------------
if 'gee_service' not in st.session_state:
    st.session_state.gee_service = GEEService(use_sandbox=True)
if 'biomass_model' not in st.session_state:
    st.session_state.biomass_model = BiomassModel()
if 'selected_coords' not in st.session_state:
    st.session_state.selected_coords = BAHA_MOU_COORDS
if 'project_name' not in st.session_state:
    st.session_state.project_name = "Baha' Mou Project"
if 'project_meta' not in st.session_state:
    st.session_state.project_meta = {
        "type": "baha_mou",
        "standard": "Verified Carbon Standard (VCS)",
        "trees": "12 Million",
        "species": "14 native species (Sundari, Garjan, Kankra, etc.)"
    }
if 'last_analyzed_coords' not in st.session_state:
    st.session_state.last_analyzed_coords = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = None
if 'carbon' not in st.session_state:
    st.session_state.carbon = None
# ----------------------------------------------------
# SIDEBAR CONTROLS
# ----------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/sprout.png", width=64)
    st.markdown("### Ecosystem Node Control")
    
    # Mode switch
    use_sandbox = st.toggle("Deterministic Sandbox Mode", value=True, help="Toggle GEE connection. Sandbox is faster and runs offline.")
    if use_sandbox != st.session_state.gee_service.use_sandbox:
        st.session_state.gee_service = GEEService(use_sandbox=use_sandbox)
        
    st.divider()
    
    # Project selector
    project_options = [
        "Baha’ Mou Mangrove Restoration Project, Sundarbans",
        "Sundari Mangrove Restoration Project, Kakdwip",
        "Draw custom area on Map"
    ]
    
    selected_proj = st.selectbox("Select Monitoring Site", options=project_options)
    
    if selected_proj == "Baha’ Mou Mangrove Restoration Project, Sundarbans":
        st.session_state.selected_coords = BAHA_MOU_COORDS
        st.session_state.project_name = "Baha' Mou Project"
        st.session_state.project_meta = {
            "type": "baha_mou",
            "standard": "Verified Carbon Standard (VCS)",
            "trees": "12 Million",
            "species": "14 native species (Sundari, Garjan, Kankra, etc.)"
        }
    elif selected_proj == "Sundari Mangrove Restoration Project, Kakdwip":
        st.session_state.selected_coords = SUNDARI_COORDS
        st.session_state.project_name = "Sundari Project"
        st.session_state.project_meta = {
            "type": "sundari",
            "standard": "Verified Carbon Standard (VCS)",
            "trees": "14 Million",
            "species": "Native Sundari & associate species"
        }
    else:
        st.session_state.project_name = "Custom Area Site"
        st.session_state.project_meta = {
            "type": "generic",
            "standard": "N/A (Evaluation Zone)",
            "trees": "N/A",
            "species": "N/A"
        }
        
    st.text_input("Project Label", key="project_name")
    
    # Run analysis status
    is_gee_live = st.session_state.gee_service.is_live()
    if is_gee_live:
        st.success("🛰️ Connected to Live Earth Engine")
    else:
        st.info("🎲 Active: Offline Simulation Engine")
        
    st.divider()
    st.markdown("### Selected Site Details")
    meta = st.session_state.project_meta
    st.markdown(f"""
    * **Registry Standard**: {meta['standard']}
    * **Trees Planted**: {meta['trees']}
    * **Species Composition**: {meta['species']}
    """)
    st.divider()
    
    st.markdown("""
    **Quick Guide:**
    * Tab 1: Draw custom bounds or view preset coordinate layers.
    * Tab 2/3: Analyze biomass, carbon, and stress curves.
    * Tab 4: Verify deforestation history.
    * Tab 5: Download the compiled report.
    """)
# ----------------------------------------------------
# MAIN COMPONENT LAYOUT
# ----------------------------------------------------
st.markdown('<div class="main-title">Blue Carbon Ecosystem Monitor</div>', unsafe_allow_html=True)
st.markdown("##### Continuous Biophysical Tracking & Carbon Density Estimation using Remote Sensing")
st.write("")
# Trigger analysis if coordinates changed or first run
coords_changed = (st.session_state.last_analyzed_coords != st.session_state.selected_coords)
if coords_changed or st.session_state.analysis is None:
    with st.spinner("Compiling Earth Engine collections and running models..."):
        # Fetch satellite indexes
        st.session_state.analysis = st.session_state.gee_service.analyze_area(st.session_state.selected_coords, st.session_state.project_meta)
        # Fetch biomass and carbon estimations
        st.session_state.carbon = st.session_state.biomass_model.predict_biomass_and_carbon(
            ndvi=st.session_state.analysis['current_ndvi'],
            ndwi=st.session_state.analysis['current_ndwi'],
            area_ha=st.session_state.analysis['area_ha']
        )
        st.session_state.last_analyzed_coords = st.session_state.selected_coords
# Extract shorthand values
analysis = st.session_state.analysis
carbon = st.session_state.carbon
# Layout Page Tabs
tab_map, tab_carbon, tab_health, tab_alerts, tab_report = st.tabs([
    "🗺️ Interactive Monitoring Map",
    "📊 Biomass & Carbon Analytics",
    "🌱 Vegetation Stress & Health",
    "⚠️ Deforestation Alerts",
    "📄 Ecosystem Summary Report"
])
# ----------------------------------------------------
# TAB 1: INTERACTIVE MONITORING MAP
# ----------------------------------------------------
with tab_map:
    st.markdown("### Interactive Satellite Observation Map")
    st.markdown('<div class="info-box">Select coordinates or draw a boundary using the polygon tool on the left of the map to monitor a new mangrove zone.</div>', unsafe_allow_html=True)
    
    # Calculate map centroid for centering
    poly_coords = st.session_state.selected_coords
    latitudes = [pt[1] for pt in poly_coords]
    longitudes = [pt[0] for pt in poly_coords]
    center_lat = sum(latitudes) / len(latitudes)
    center_lng = sum(longitudes) / len(longitudes)
    
    # Initialize Folium Map
    m = folium.Map(location=[center_lat, center_lng], zoom_start=11, tiles='CartoDB dark_matter')
    
    # Draw existing polygon on map
    geojson_poly = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [poly_coords]
        },
        "properties": {
            "name": st.session_state.project_name
        }
    }
    
    folium.GeoJson(
        geojson_poly,
        style_function=lambda x: {
            'fillColor': '#10b981',
            'color': '#10b981',
            'weight': 2.5,
            'fillOpacity': 0.15
        }
    ).add_to(m)
    
    # Add drawing plugin
    draw = Draw(
        export=False,
        filename='drawn_polygon.geojson',
        position='topleft',
        draw_options={
            'polyline': False,
            'rectangle': True,
            'circle': False,
            'marker': False,
            'circlemarker': False,
            'polygon': True
        }
    )
    draw.add_to(m)
    
    # Render folium map in streamlit
    map_data = st_folium(m, width=1200, height=500, key="monitoring_map")
    
    # Check if user drew a new polygon
    if map_data and map_data.get('last_active_drawing'):
        geom = map_data['last_active_drawing'].get('geometry')
        if geom and geom.get('type') == 'Polygon':
            drawn_coords = geom['coordinates'][0]
            # Convert back to standard [lng, lat] coordinate list format
            formatted_coords = [[round(pt[0], 5), round(pt[1], 5)] for pt in drawn_coords]
            
            # Check if this drawn shape is different from what we have
            if formatted_coords != st.session_state.selected_coords:
                st.session_state.selected_coords = formatted_coords
                st.session_state.project_name = "Custom Area Site"
                st.rerun()
# ----------------------------------------------------
# TAB 2: BIOMASS & CARBON ANALYTICS
# ----------------------------------------------------
with tab_carbon:
    st.markdown("### Mangrove Biomass & Carbon Density Estimates")
    
    # Stats Row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Area Monitored", f"{analysis['area_ha']:,} ha", help="Calculated area of the boundary polygon.")
    with col2:
        st.metric("Estimated Total Carbon", f"{carbon['total_carbon_tc']:,} tC", help="Total Organic Carbon (AGC + BGC + SOC).")
    with col3:
        st.metric("CO₂ Equivalent", f"{carbon['total_co2e_tons']:,} tCO₂e", help="Carbon Dioxide equivalent sequestered.")
    with col4:
        st.metric("Annual Sequestration", f"{carbon['annual_sequestration_tco2e']:,} tCO₂/yr", help="Estimated annual carbon uptake.")
        
    st.divider()
    
    col_chart, col_details = st.columns([2, 1])
    
    with col_chart:
        st.markdown("##### 10-Year Historical Carbon Accumulation Trend")
        
        # Calculate carbon history based on historical NDVI trend
        hist_dates = analysis['historical_dates']
        hist_ndvi = analysis['historical_ndvi']
        
        # Carbon accumulation scales with NDVI and area
        hist_co2 = []
        base_co2 = carbon['total_co2e_tons'] * 0.82
        for idx, ndvi in enumerate(hist_ndvi):
            # Accumulate growth trend over months
            acc_factor = 1.0 + (idx / len(hist_ndvi)) * 0.15
            val = base_co2 * acc_factor * (ndvi / analysis['current_ndvi'])
            hist_co2.append(round(val, 1))
            
        fig_growth = go.Figure()
        fig_growth.add_trace(go.Scatter(
            x=hist_dates,
            y=hist_co2,
            mode='lines',
            fill='tozeroy',
            line=dict(color='#10b981', width=3),
            fillcolor='rgba(16, 185, 129, 0.1)'
        ))
        fig_growth.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Year-Month"),
            yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Carbon Stock (tCO2e)"),
            margin=dict(l=10, r=10, t=10, b=10),
            height=350,
            showlegend=False
        )
        st.plotly_chart(fig_growth, use_container_width=True)
        
    with col_details:
        st.markdown("##### Carbon Pool Distributions")
        
        # Pie chart for carbon pools
        pool_labels = ["Aboveground Carbon", "Belowground Carbon", "Soil Organic Carbon"]
        pool_values = [
            carbon['aboveground_carbon_tc'],
            carbon['belowground_carbon_tc'],
            carbon['soil_organic_carbon_tc']
        ]
        
        fig_pie = px.pie(
            names=pool_labels,
            values=pool_values,
            color_discrete_sequence=['#10b981', '#3b82f6', '#8b5cf6'],
            hole=0.4
        )
        fig_pie.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=5, r=5, t=5, b=5),
            height=250,
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
        )
        st.plotly_chart(fig_pie, use_container_width=True)
        
        # Details text
        st.caption("Soil organic carbon represents up to 75% of mangrove sinks due to slow decomposition rates in waterlogged salt soils.")
# ----------------------------------------------------
# TAB 3: VEGETATION STRESS & HEALTH
# ----------------------------------------------------
with tab_health:
    st.markdown("### Ecosystem Stress & Health Monitoring")
    
    col_metrics, col_plot = st.columns([1, 2])
    
    with col_metrics:
        # Index status indicators
        st.markdown("##### Biophysical Canopy Indexes")
        
        # Format NDVI status
        ndvi = analysis['current_ndvi']
        if ndvi > 0.70:
            ndvi_status = "Dense Canopy"
        elif ndvi > 0.55:
            ndvi_status = "Moderate Canopy"
        else:
            ndvi_status = "Sparse/Stressed"
            
        # Format ET Stress status
        stress = analysis['current_et_stress']
        if stress < 0.20:
            stress_status = "Stagnant (Unstressed)"
        elif stress < 0.40:
            stress_status = "Low Stress Anomaly"
        elif stress < 0.60:
            stress_status = "Moderate Canopy Stress"
        else:
            stress_status = "Severe Moisture Deficit"
            
        st.metric("NDVI Index", f"{ndvi:.3f}", delta=ndvi_status, delta_color="normal" if ndvi > 0.55 else "inverse")
        st.metric("NDWI (Water Index)", f"{analysis['current_ndwi']:.3f}", delta="Waterlogged Substrate", delta_color="normal")
        st.metric("Evapotranspiration Stress", f"{stress:.2f}", delta=stress_status, delta_color="inverse" if stress > 0.40 else "normal")
        
    with col_plot:
        st.markdown("##### 2-Year Monthly Evapotranspiration vs Temperature Anomaly")
        
        # Plotly dual-axis chart showing transpiration & temperature fluctuations
        et_dates = analysis['historical_et_dates']
        et_vals = analysis['historical_et']
        temp_anoms = analysis['historical_temp_anom']
        
        fig_et = go.Figure()
        
        # ET bars
        fig_et.add_trace(go.Bar(
            x=et_dates,
            y=et_vals,
            name="Evapotranspiration (mm/month)",
            marker=dict(color='rgba(59, 130, 246, 0.4)', line=dict(color='#3b82f6', width=1.5)),
            yaxis="y1"
        ))
        
        # Temp line
        fig_et.add_trace(go.Scatter(
            x=et_dates,
            y=temp_anoms,
            name="LST Temp Anomaly (°C)",
            line=dict(color='#f43f5e', width=2.5),
            yaxis="y2"
        ))
        
        fig_et.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            xaxis=dict(gridcolor='rgba(255,255,255,0.05)'),
            yaxis=dict(
                gridcolor='rgba(255,255,255,0.05)',
                title=dict(text="Evapotranspiration (mm/month)", font=dict(color="#3b82f6")),
                tickfont=dict(color="#3b82f6")
            ),
            yaxis2=dict(
                title=dict(text="LST Temperature Anomaly (°C)", font=dict(color="#f43f5e")),
                tickfont=dict(color="#f43f5e"),
                overlaying="y",
                side="right"
            ),
            margin=dict(l=10, r=10, t=10, b=10),
            height=350,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig_et, use_container_width=True)
# ----------------------------------------------------
# TAB 4: DEFORESTATION ALERTS
# ----------------------------------------------------
with tab_alerts:
    st.markdown("### deforestAlert Logs (Canopy Loss Detection)")
    
    alerts = analysis['deforestation_alerts']
    
    if not alerts:
        st.success("🟢 No canopy degradation or deforestation hotspots detected within the boundaries in the last 365 days.")
    else:
        st.warning(f"⚠️ Detected {len(alerts)} canopy loss/deforestation hotspots in the last 365 days.")
        
        # Show alerts inside styled rows
        for alt in alerts:
            with st.container():
                st.markdown(f"""
                <div style="background: rgba(244, 63, 94, 0.08); border: 1px solid rgba(244, 63, 94, 0.25); border-radius: 8px; padding: 12px 20px; margin-bottom: 12px;">
                    <span style="background-color: #f43f5e; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: bold; text-transform: uppercase;">{alt['severity']} SEVERITY</span>
                    <span style="margin-left: 15px; color: #94a3b8; font-size: 0.9rem;">Detected: <b>{alt['date']}</b></span>
                    <br/><br/>
                    <b>Location Coordinates:</b> Latitude {alt['latitude']}, Longitude {alt['longitude']}
                    <br/>
                    <b>Ecosystem Footprint Loss:</b> {alt['area_loss_sqm']} sqm (square meters) of canopy cover cleared.
                </div>
                """, unsafe_allow_html=True)
# ----------------------------------------------------
# TAB 5: ECOSYSTEM SUMMARY REPORT
# ----------------------------------------------------
with tab_report:
    st.markdown("### Compile Ecosystem Status Summary")
    st.markdown("Download a certified biophysical data package compiling current satellite monitoring indices, carbon storage levels, and canopy loss logs.")
    
    st.divider()
    
    col_rep1, col_rep2 = st.columns(2)
    with col_rep1:
        st.markdown("##### Included in PDF Status Report:")
        st.markdown("""
        * ✓ Bounding box GPS Coordinates & Area (ha)
        * ✓ GEDI LiDAR predicted Canopy Heights
        * ✓ Carbon Sinks Breakdown (AGC, BGC, SOC)
        * ✓ Evapotranspiration (ET) stress indices
        * ✓ Complete deforestation history logs
        """)
    with col_rep2:
        st.markdown("##### Generate Report")
        
        # Run report generation
        pdf_bytes = generate_pdf_report(
            st.session_state.project_name,
            analysis,
            carbon,
            st.session_state.project_meta
        )
        
        proj_clean = st.session_state.project_name.replace(' ', '_')
        date_str = datetime.now().strftime('%Y%m%d')
        report_filename = f"Ecosystem_Status_Report_{proj_clean}_{date_str}.pdf"
        
        st.download_button(
            label="⬇️ Download PDF Status Report",
            data=pdf_bytes,
            file_name=report_filename,
            mime="application/pdf"
        )
