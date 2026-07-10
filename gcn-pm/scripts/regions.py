"""Shared region + ribbon/SBC groupings for the gcn-pm skill.

REGIONS: per-region order used by generate_xcc.py / generate_rtpengine.py.
RIBBON_SBCS: SBC hostnames grouped by ribbon, used by generate_sbc.py.
"""

REGIONS = [
    ("EU-South-1", "eu-south-1"),
    ("EU-West-3", "eu-west-3"),
    ("US-East-1", "us-east-1"),
    ("US-West-2", "us-west-2"),
    ("AP1 - Singapore", "ap-southeast-1"),
    ("AP2 - Sydney", "ap-southeast-2"),
    ("SA-East-1", "sa-east-1"),
    ("CA-Central-1", "ca-central-1"),
]
REGION_TOKENS = {tok for _, tok in REGIONS}

RIBBON_SBCS = [
    ("Ribbon EU", [("EU-South-1", "PRDEUS1RSBC"), ("EU-West-3", "PRDEUW3RSBC")]),
    ("Ribbon US", [("US-East-1", "prduse1rsbc"), ("US-West-2", "prdusw2rsbc")]),
    ("Ribbon APAC", [("AP1 - Singapore", "PRDAPS1RSBC"), ("AP2 - Sydney", "PRDAPS2RSBC")]),
    ("Ribbon LATAM", [("LATAM-AZ1 (São Paulo)", "PRDSAE1RSBC1"),
                      ("LATAM-AZ2 (São Paulo)", "PRDSAE1RSBC2")]),
]
