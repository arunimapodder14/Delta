import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Draw
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime

# Import local modules
from gee_service import GEEService, validate_mangrove_habitat, locate_real_mangrove_center
from biomass_ml import BiomassModel
from pdf_report import generate_pdf_report
from analytics import (
    prepare_ndvi_ndwi_trend_chart,
    prepare_carbon_trend_chart,
    get_verification_checklist,
    get_readiness_score,
    get_credit_readiness_status
)

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
# Baha' Mou: real program (Mouli community mangrove honey collective), but no
# published GPS/boundary exists publicly. Uses Gosaba CD block centroid as a
# starting reference point, then relocated onto real nearby mapped mangrove
# (see locate_real_mangrove_center) when GEE is live. Flagged as "approximate"
# via project_meta's data_confidence field.
BAHA_MOU_REFERENCE = (22.1652, 88.8079)  # Gosaba CD block centroid

# Real CD Block centroids (verified via Wikipedia/Census of India), covering
# the Sundari project's operating region across South & North 24 Parganas.
# Each is relocated onto real nearby mapped mangrove when GEE is live.
SUNDARBANS_BLOCKS = {
    "Sagar": (21.6528, 88.0753),
    "Namkhana": (21.7699, 88.2315),
    "Patharpratima": (21.7941, 88.3555),
    "Gosaba": (22.1652, 88.8079),
    "Kakdwip": (21.8791, 88.1913),
    "Mathurapur I": (22.1217, 88.4053),
    "Basanti": (22.1983, 88.7139),
    "Kultali": (22.0866, 88.5937),
    "Hingalganj": (22.4708, 88.9773),
    "Sandeshkhali I": (22.3600, 88.9000),
    "Sandeshkhali II": (22.3600, 88.9000),  # approximate — sources gave near-identical rounded coords for I & II
}


def block_to_polygon(lat, lng, half_width_deg=0.04):
    """Builds a small rectangle around a centroid for GEE analysis."""
    return [
        [lng - half_width_deg, lat - half_width_deg],
        [lng + half_width_deg, lat - half_width_deg],
        [lng + half_width_deg, lat + half_width_deg],
        [lng - half_width_deg, lat + half_width_deg],
        [lng - half_width_deg, lat - half_width_deg],
    ]


def resolve_coords(reference_lat, reference_lng, gee_service):
    """
    Given an administrative/reference centroid, relocates onto real nearby
    mapped mangrove when GEE is live; falls back to the raw reference point
    otherwise (sandbox mode, or no mangrove found within search radius).
    """
    relocated = None
    if gee_service.is_live():
        relocated = locate_real_mangrove_center(reference_lat, reference_lng)
    final_lat, final_lng = relocated if relocated else (reference_lat, reference_lng)
    return block_to_polygon(final_lat, final_lng)


# ----------------------------------------------------
# INITIALIZE SESSION STATE
# ----------------------------------------------------
if 'gee_service' not in st.session_state:
    st.session_state.gee_service = GEEService(use_sandbox=False)
if 'biomass_model' not in st.session_state:
    st.session_state.biomass_model = BiomassModel()
if 'selected_coords' not in st.session_state:
    st.session_state.selected_coords = resolve_coords(*BAHA_MOU_REFERENCE, st.session_state.gee_service)
if 'project_name' not in st.session_state:
    st.session_state.project_name = "Baha' Mou Project"
if 'project_meta' not in st.session_state:
    st.session_state.project_meta = {
        "type": "baha_mou",
        "standard": "Verified Carbon Standard (VCS)",
        "trees": "12 Million",
        "species": "14 native species (Sundari, Garjan, Kankra, etc.)",
        "data_confidence": "approximate"
    }
if 'last_analyzed_coords' not in st.session_state:
    st.session_state.last_analyzed_coords = None
if 'analysis' not in st.session_state:
    st.session_state.analysis = None
if 'carbon' not in st.session_state:
    st.session_state.carbon = None
if 'habitat_valid' not in st.session_state:
    st.session_state.habitat_valid = True
if 'habitat_reasons' not in st.session_state:
    st.session_state.habitat_reasons = []
if 'force_refresh' not in st.session_state:
    st.session_state.force_refresh = False

# ----------------------------------------------------
# SIDEBAR CONTROLS
# ----------------------------------------------------
with st.sidebar:
    st.image("https://img.icons8.com/color/96/000000/sprout.png", width=64)
    st.markdown("### Ecosystem Node Control")

    # Mode switch
    use_sandbox = st.toggle("Deterministic Sandbox Mode", value=False, help="Use offline simulation instead of live Google Earth Engine.")
    if use_sandbox != st.session_state.gee_service.use_sandbox:
        st.session_state.gee_service = GEEService(use_sandbox=use_sandbox)

    st.divider()

    # Project selector
    project_options = [
        "Baha' Mou Mangrove Restoration Project, Sundarbans",
        "Sundari Mangrove Restoration Project, Kakdwip",
        "Draw custom area on Map"
    ]

    selected_proj = st.selectbox("Select Monitoring Site", options=project_options)

    if selected_proj == "Baha' Mou Mangrove Restoration Project, Sundarbans":
        st.session_state.selected_coords = resolve_coords(*BAHA_MOU_REFERENCE, st.session_state.gee_service)
        st.session_state.project_name = "Baha' Mou Project"
        st.session_state.project_meta = {
            "type": "baha_mou",
            "standard": "Verified Carbon Standard (VCS)",
            "trees": "12 Million",
            "species": "14 native species (Sundari, Garjan, Kankra, etc.)",
            "data_confidence": "approximate"
        }

    elif selected_proj == "Sundari Mangrove Restoration Project, Kakdwip":
        selected_block = st.selectbox(
            "Select Project Block",
            options=list(SUNDARBANS_BLOCKS.keys()),
            help="Choose a specific CD Block within the Sundari project's coverage area."
        )
        ref_lat, ref_lng = SUNDARBANS_BLOCKS[selected_block]
        st.session_state.selected_coords = resolve_coords(ref_lat, ref_lng, st.session_state.gee_service)
        st.session_state.project_name = f"Sundari Project - {selected_block}"
        st.session_state.project_meta = {
            "type": "sundari",
            "standard": "Verified Carbon Standard (VCS)",
            "trees": "14 Million",
            "species": "Native Sundari & associate species",
            "data_confidence": "verified",
            "block_name": selected_block
        }

    else:
        st.session_state.project_name = "Custom Area Site"
        st.session_state.project_meta = {
            "type": "generic",
            "standard": "N/A (Evaluation Zone)",
            "trees": "N/A",
            "species": "N/A",
            "data_confidence": "unverified"
        }

    # Run analysis status
    is_gee_live = st.session_state.gee_service.is_live()
    if is_gee_live:
        st.success("🛰️ Connected to Live Earth Engine")
    else:
        st.info("🎲 Active: Offline Simulation Engine")

    # Manual refresh — bypasses cache to force a fresh live fetch for the
    # currently selected project/block.
    if st.button("🔄 Refresh Data", help="Force a fresh satellite data fetch, bypassing any cached result."):
        st.session_state.force_refresh = True
        st.session_state.last_analyzed_coords = None  # forces the analysis block below to re-run
        st.rerun()

    st.divider()
    st.markdown("### Selected Site Details")
    meta = st.session_state.project_meta
    st.markdown(f"""
    * **Registry Standard**: {meta['standard']}
    * **Trees Planted**: {meta['trees']}
    * **Species Composition**: {meta['species']}
    """)

    # Data confidence disclaimer — tells the user how trustworthy this
    # project's boundary is, separate from whether the satellite data itself
    # is live/real.
    confidence = meta.get("data_confidence", "unverified")
    if confidence == "verified":
        st.success("📍 Site boundary based on verified administrative coordinates.")
    elif confidence == "approximate":
        st.warning(
            "📍 **Approximate boundary** — this project's exact GPS footprint is "
            "not publicly published. Coordinates are relocated onto real nearby "
            "mapped mangrove as a regional stand-in. Satellite indices "
            "(NDVI/NDWI/carbon) are real and live, but reflect this approximate "
            "area, not a confirmed project boundary."
        )
    else:
        st.info("📍 Custom-drawn area — boundary accuracy depends on the user's manual selection.")

    st.divider()

    st.markdown("""
    **Quick Guide:**
    * Tab 1: View the selected project boundary on the map.
    * Tab 2/3: Analyze biomass, carbon, and stress curves.
    * Tab 4: Verify deforestation history.
    * Tab 5: Review the pre-verification checklist and download the report.
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
        st.session_state.analysis = st.session_state.gee_service.analyze_area(
            st.session_state.selected_coords,
            st.session_state.project_meta,
            force_refresh=st.session_state.force_refresh
        )
        st.session_state.force_refresh = False  # reset after use

        # Habitat plausibility gate — checks real mangrove coverage first
        # (when available from GEE), falls back to NDVI/NDWI/elevation
        # heuristics otherwise.
        is_valid, reasons = validate_mangrove_habitat(
            st.session_state.analysis.get('current_ndvi'),
            st.session_state.analysis.get('current_ndwi'),
            st.session_state.analysis.get('mean_elevation_m'),
            mangrove_fraction=st.session_state.analysis.get('mangrove_coverage_fraction')
        )
        st.session_state.habitat_valid = is_valid
        st.session_state.habitat_reasons = reasons

        if is_valid:
            # Fetch biomass and carbon estimations — pass real GEDI-measured
            # biomass through when available, so the model uses it directly
            # instead of the fallback allometric prediction.
            st.session_state.carbon = st.session_state.biomass_model.predict_biomass_and_carbon(
                ndvi=st.session_state.analysis['current_ndvi'],
                ndwi=st.session_state.analysis['current_ndwi'],
                area_ha=st.session_state.analysis['area_ha'],
                real_agbd_per_ha=st.session_state.analysis.get('gedi_measured_agb_per_ha'),
                canopy_height_m=st.session_state.analysis.get('gedi_canopy_height_m', 15.4)
            )
        else:
            st.session_state.carbon = None

        st.session_state.last_analyzed_coords = st.session_state.selected_coords

# Extract shorthand values
analysis = st.session_state.analysis
carbon = st.session_state.carbon

# Habitat gate — block downstream tabs cleanly if this area isn't plausible
# mangrove/coastal wetland habitat, instead of showing a misleading report.
if not st.session_state.habitat_valid:
    st.error("🚫 This area does not appear to be viable mangrove/coastal wetland habitat, so carbon estimates cannot be reliably generated.")
    for reason in st.session_state.habitat_reasons:
        st.markdown(f"- {reason}")
    st.info("Try selecting one of the preset projects/blocks, or draw a polygon over a known coastal mangrove/wetland zone.")
    st.stop()

if analysis.get('is_cached'):
    st.caption("ℹ️ Showing the most recently available real satellite analysis for this area (cached result).")

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
                st.session_state.project_meta = {
                    "type": "generic",
                    "standard": "N/A (Evaluation Zone)",
                    "trees": "N/A",
                    "species": "N/A",
                    "data_confidence": "unverified"
                }
                st.rerun()

# ----------------------------------------------------
# TAB 2: BIOMASS & CARBON ANALYTICS
# ----------------------------------------------------
with tab_carbon:
    st.markdown("### Mangrove Biomass & Carbon Density Estimates")

    # Data source transparency — shows whether biomass came from real GEDI
    # measurement or the fallback allometric model.
    data_source = carbon.get('data_source', 'unknown')
    if data_source == "gedi_measured":
        st.caption("Biomass source: **Real GEDI L4A measured data**")
    elif data_source == "model_real_trained":
        st.caption("Biomass source: **ML model (trained on real GEDI + Sentinel-2 data)** — no GEDI footprint in this area")
    elif data_source == "model_synthetic_fallback":
        st.caption("Biomass source: **Fallback model (synthetic training data)** — run train_biomass_model.py for real-trained predictions")

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
        st.markdown("##### 5-Year Baseline vs. Current (NDVI & NDWI)")

        trend_chart = prepare_ndvi_ndwi_trend_chart(analysis)

        if trend_chart["available"]:
            fig_trend = go.Figure()
            fig_trend.add_trace(go.Scatter(
                x=trend_chart["labels"], y=trend_chart["ndvi_values"],
                mode='lines+markers', name='NDVI',
                line=dict(color='#10b981', width=3)
            ))
            fig_trend.add_trace(go.Scatter(
                x=trend_chart["labels"], y=trend_chart["ndwi_values"],
                mode='lines+markers', name='NDWI',
                line=dict(color='#3b82f6', width=3)
            ))
            fig_trend.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Year"),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Index Value"),
                margin=dict(l=10, r=10, t=10, b=10),
                height=300,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_trend, width="stretch")
            if trend_chart["note"]:
                st.caption(f"⚠️ {trend_chart['note']}")
            else:
                st.caption("🛰️ Real Sentinel-2 dry-season composites")
        else:
            st.info(trend_chart["note"])

        st.markdown("##### Carbon Stock Trend (Indicative)")

        carbon_trend = prepare_carbon_trend_chart(analysis, carbon)

        if carbon_trend["available"]:
            fig_carbon_trend = go.Figure()
            fig_carbon_trend.add_trace(go.Scatter(
                x=carbon_trend["labels"], y=carbon_trend["values"],
                mode='lines+markers', fill='tozeroy',
                line=dict(color='#8b5cf6', width=3),
                fillcolor='rgba(139, 92, 246, 0.1)'
            ))
            fig_carbon_trend.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                xaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="Year"),
                yaxis=dict(gridcolor='rgba(255,255,255,0.05)', title="tCO2e"),
                margin=dict(l=10, r=10, t=10, b=10),
                height=280,
                showlegend=False
            )
            st.plotly_chart(fig_carbon_trend, width="stretch")
            st.caption(f"📈 {carbon_trend['note']}")
        else:
            st.info(carbon_trend["note"])

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
        st.plotly_chart(fig_pie, width="stretch")

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
        st.plotly_chart(fig_et, width="stretch")

# ----------------------------------------------------
# TAB 4: DEFORESTATION ALERTS
# ----------------------------------------------------
with tab_alerts:
    st.markdown("### Deforestation & Canopy-Loss Alert Log")

    detection_method = analysis.get('deforestation_detection_method', 'simulated')
    if detection_method == "real":
        st.caption("🛰️ Detection method: Real Sentinel-2 NDVI change analysis")
    else:
        st.caption("⚠️ Detection method: Simulated (live detection unavailable for this run)")

    alerts = analysis['deforestation_alerts']

    if not alerts:
        st.success("🟢 No canopy degradation or deforestation hotspots detected within the boundaries in the last 365 days.")
    else:
        st.warning(f"⚠️ Detected {len(alerts)} canopy loss/deforestation hotspots in the last 365 days.")
        st.markdown("##### Alert Locations")
        alert_lats = [a['latitude'] for a in alerts]
        alert_lngs = [a['longitude'] for a in alerts]
        map_center = [sum(alert_lats) / len(alert_lats), sum(alert_lngs) / len(alert_lngs)]

        alert_map = folium.Map(location=map_center, zoom_start=12, tiles='CartoDB dark_matter')
        severity_color = {"High": "#f43f5e", "Moderate": "#f59e0b"}

        for alt in alerts:
            folium.CircleMarker(
                location=[alt['latitude'], alt['longitude']],
                radius=8,
                color=severity_color.get(alt['severity'], "#94a3b8"),
                fill=True,
                fill_color=severity_color.get(alt['severity'], "#94a3b8"),
                fill_opacity=0.7,
                popup=f"{alt['severity']} — {alt['area_loss_sqm']:.1f} sqm ({alt['date']})"
            ).add_to(alert_map)

        st_folium(alert_map, width=1200, height=350, key="alerts_map")
        st.divider()

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
    st.markdown("### Ecosystem Status Summary")
    st.markdown(
        "Remote-sensing MRV evidence pack — indicative monitoring summary for review by "
        "governments, NGOs, and carbon marketplace stakeholders."
    )

    st.divider()

    checklist = get_verification_checklist(
        analysis, carbon, st.session_state.project_meta,
        is_live=st.session_state.gee_service.is_live()
    )

    st.markdown("##### Credit Readiness")

    readiness = get_credit_readiness_status(checklist, carbon)
    status_style = {
        "Ready": ("✅", "success"),
        "Needs Review": ("🟡", "warning"),
        "Not Ready": ("🚫", "error")
    }
    icon, style = status_style.get(readiness["status"], ("⚠️", "warning"))

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.metric("Status", f"{icon} {readiness['status']}")
    with col_b:
        st.metric("Evidence Completeness", f"{readiness['score_pct']:.0f}%")
    with col_c:
        st.metric("Gross Indicative CO2e", f"{readiness['gross_co2e']:,} tCO2e" if readiness['gross_co2e'] else "N/A")

    getattr(st, style)(readiness["summary_note"])
    st.caption("Net tCO2e (post-buffer/deduction) will be added once accredited deduction methodology is applied.")

    st.divider()

    st.markdown("##### Pre-Verification Checklist")
    st.caption(
        "Each item below is derived directly from the monitoring evidence collected for "
        "this project. This checklist supports — but does not replace — formal verification."
    )

    

    status_icon = {"pass": "✅", "warning": "⚠️", "fail": "🚫"}

    for entry in checklist:
        icon = status_icon.get(entry["status"], "⚠️")
        st.markdown(f"{icon} **{entry['item']}**")
        st.caption(entry["note"])

    st.divider()

    col_rep1, col_rep2 = st.columns(2)
    with col_rep1:
        st.markdown("##### Included in PDF Evidence Pack:")
        st.markdown("""
        * ✓ Bounding box GPS Coordinates & Area (ha)
        * ✓ GEDI LiDAR canopy heights / measured biomass
        * ✓ Carbon Sinks Breakdown (AGC, BGC, SOC)
        * ✓ Evapotranspiration (ET) stress indices
        * ✓ Deforestation alert log
        * ✓ Pre-verification checklist findings
        """)
    with col_rep2:
        st.markdown("##### Generate Report")

        # Run report generation
        pdf_bytes = generate_pdf_report(
            st.session_state.project_name,
            analysis,
            carbon,
            st.session_state.project_meta,
            checklist=checklist
        )

        proj_clean = st.session_state.project_name.replace(' ', '_').replace('-', '_')
        date_str = datetime.now().strftime('%Y%m%d')
        report_filename = f"MRV_Evidence_Pack_{proj_clean}_{date_str}.pdf"

        st.download_button(
            label="⬇Download Indicative MRV Evidence Pack (PDF)",
            data=pdf_bytes,
            file_name=report_filename,
            mime="application/pdf"
        )