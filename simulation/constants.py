"""
Constants for price calculation and seed generation
"""

# Macro factors weights
A_INF = 0.25  # Inflation weight
A_RATE = 0.30  # Interest rate weight
A_INC = 0.15  # Income weight
A_UNEMP = 0.10  # Unemployment weight
A_CONF = 0.05  # Confidence weight
A_POL = 0.05  # Policy weight

# Local factors weights
# Lowered to limit excessive price volatility
B_ACC = 0.05  # Access weight (lowered from 0.10 - moderate impact of accessibility)
B_ATTR = 0.05  # Attractiveness weight (lowered from 0.10 - local attractiveness)
B_NUI = 0.04  # Nuisance weight (lowered from 0.08 - impact of nuisances)
B_TENS = 0.06  # Tension weight (lowered from 0.12 - supply/demand tension)

# Property characteristics weights
# Raised to make renovations more profitable and reflect the growing importance of energy ratings (EPC/PEB)
W_EPC = 0.20  # EPC weight (raised from 0.15 - energy rating becomes critical under new standards)
W_STATE = 0.15  # State weight (raised from 0.12 - overall condition highly valued)
W_KITCHEN = 0.08  # Kitchen weight (raised from 0.06 - a modern kitchen matters)
W_BATH = 0.07  # Bath weight (raised from 0.06 - a quality bathroom is valued)

# Noise standard deviation
SIGMA_NOISE = 0.01

# Belgian zones
ZONES = [
    "Bruxelles-Centre",
    "Ixelles",
    "Uccle",
    "Schaerbeek",
    "Liège-Centre",
    "Liège-Sud",
    "Namur-Est",
    "Namur-Centre",
    "Gand-Centre",
    "Anvers-Nord",
    "Anvers-Sud",
    "Charleroi-Ville",
]

# Base price per m² by zone and type (€/m²)
BASE_PPM = {
    "Bruxelles-Centre": {"house": 4500, "apartment": 4200},
    "Ixelles": {"house": 4800, "apartment": 4500},
    "Uccle": {"house": 5200, "apartment": 4800},
    "Schaerbeek": {"house": 3800, "apartment": 3500},
    "Liège-Centre": {"house": 2800, "apartment": 2500},
    "Liège-Sud": {"house": 2400, "apartment": 2200},
    "Namur-Est": {"house": 3000, "apartment": 2700},
    "Namur-Centre": {"house": 2900, "apartment": 2600},
    "Gand-Centre": {"house": 3500, "apartment": 3200},
    "Anvers-Nord": {"house": 3200, "apartment": 2900},
    "Anvers-Sud": {"house": 3800, "apartment": 3500},
    "Charleroi-Ville": {"house": 2000, "apartment": 1800},
}

# Zone appreciation trends (% per quarter)
# Calibrated on Belgian historical data (2014-2024)
# Sources: Statbel, Notariat, UPsite
ZONE_TRENDS = {
    "Bruxelles-Centre": 0.006,  # +0.6% per quarter = +2.4%/yr (premium zone, strong demand)
    "Ixelles": 0.005,  # +0.5% per quarter = +2.0%/yr (trendy neighborhood, young population)
    "Uccle": 0.004,  # +0.4% per quarter = +1.6%/yr (upscale residential, families)
    "Schaerbeek": 0.003,  # +0.3% per quarter = +1.2%/yr (gradual gentrification)
    "Liège-Centre": 0.002,  # +0.2% per quarter = +0.8%/yr (modest growth)
    "Liège-Sud": 0.001,  # +0.1% per quarter = +0.4%/yr (working-class neighborhood)
    "Namur-Est": 0.002,  # +0.2% per quarter = +0.8%/yr (attractive suburban area)
    "Namur-Centre": 0.002,  # +0.2% per quarter = +0.8%/yr (stable city center)
    "Gand-Centre": 0.004,  # +0.4% per quarter = +1.6%/yr (dynamic university city)
    "Anvers-Nord": 0.001,  # +0.1% per quarter = +0.4%/yr (port area, slow transition)
    "Anvers-Sud": 0.003,  # +0.3% per quarter = +1.2%/yr (expanding residential neighborhood)
    "Charleroi-Ville": 0.000,  # +0.0% per quarter = stagnation (difficult economic reality)
}

# Renovation types
RENOVATIONS = [
    {
        "code": "INSULATION",
        "label": "Insulation + Windows",
        "cost": 15000,
        "durationQ": 2,
        "delta": {"epc": 0.20, "state": 0.05, "kitchen": 0, "bath": 0, "surfacePct": 0},
    },
    {
        "code": "HEATING",
        "label": "Heating system",
        "cost": 12000,
        "durationQ": 1,
        "delta": {"epc": 0.15, "state": 0.03, "kitchen": 0, "bath": 0, "surfacePct": 0},
    },
    {
        "code": "KITCHEN",
        "label": "Kitchen renovation",
        "cost": 20000,
        "durationQ": 2,
        "delta": {"epc": 0, "state": 0.05, "kitchen": 0.30, "bath": 0, "surfacePct": 0},
    },
    {
        "code": "BATHROOM",
        "label": "Bathroom renovation",
        "cost": 15000,
        "durationQ": 2,
        "delta": {"epc": 0, "state": 0.05, "kitchen": 0, "bath": 0.30, "surfacePct": 0},
    },
    {
        "code": "EXTENSION",
        "label": "Extension (+20% floor area)",
        "cost": 50000,
        "durationQ": 4,
        "delta": {"epc": -0.05, "state": 0.10, "kitchen": 0, "bath": 0, "surfacePct": 0.20},
    },
    {
        "code": "FINISHING",
        "label": "Full finishing",
        "cost": 10000,
        "durationQ": 1,
        "delta": {"epc": 0, "state": 0.15, "kitchen": 0.05, "bath": 0.05, "surfacePct": 0},
    },
]

# Initial portfolio cash
INITIAL_CASH = 1_000_000

# Seed parameters
NUM_PROPERTIES = 300
NUM_QUARTERS = 20
START_YEAR = 2020
START_QUARTER = 1

# Random seed for reproducibility
RANDOM_SEED = 42
