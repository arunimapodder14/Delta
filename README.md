Blue Carbon Ecosystem Monitoring Platform
This platform is a 100% Python Streamlit application designed to monitor mangrove forest biomass, assess vegetation stress, and log degradation anomalies using NASA/ESA satellite data and machine learning.

🚀 Core Features
Interactive Mapping: Draw custom polygon boundaries or select predefined locations:
Baha' Mou Mangrove Restoration Project, Sundarbans (~1,200 ha in South 24 Parganas, VCS Registry, 12 Million trees).
Sundari Mangrove Restoration Project, Kakdwip (~4,000 ha, VCS Registry, 14 Million trees).
AI Carbon Accounting: Uses a Random Forest regression model calibrated against NASA GEDI LiDAR canopy height data to estimate aboveground, belowground, and soil organic carbon stocks in tons of CO2 equivalent (tCO2e).
Ecosystem Stress Tracking: Monitored via Evapotranspiration (ET) from MODIS/061/MOD16A2 and Land Surface Temperature (LST) anomaly models.
Degradation Detection (deforestAlert): Automated spatial scanning identifies and flags localized forest cover loss events.
Status PDF Generator: Compiles project maps, carbon metrics, health statistics, and alert logs into a professional downloadable document.
