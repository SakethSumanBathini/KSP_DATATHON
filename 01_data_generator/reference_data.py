"""
Reference/lookup data for the KSP synthetic FIR generator.
All values grounded in the real Karnataka Police ER schema.
"""

# Five real Karnataka districts (DistrictID -> name) with real station names
DISTRICTS = {
    1: {"name": "Bengaluru Urban", "state_id": 1,
        "stations": {6001: "Cubbon Park PS", 6002: "Shivajinagar PS", 6003: "Ulsoor PS",
                     6004: "High Grounds PS", 6005: "Cottonpet PS", 6006: "Vijayanagar PS"}},
    2: {"name": "Mysuru", "state_id": 1,
        "stations": {6101: "Nazarbad PS", 6102: "Jayalakshmipuram PS", 6103: "Mysuru North PS",
                     6104: "Mysuru East PS", 6105: "Vijayanagar Mysuru PS"}},
    3: {"name": "Belagavi", "state_id": 1,
        "stations": {6201: "Belagavi City PS", 6202: "Tilakwadi PS", 6203: "Udyambag PS"}},
    4: {"name": "Mangaluru", "state_id": 1,
        "stations": {6301: "Mangaluru East PS", 6302: "Mangaluru West PS", 6303: "Bunder PS"}},
    5: {"name": "Kalaburagi", "state_id": 1,
        "stations": {6401: "Kalaburagi Urban PS", 6402: "Kalaburagi Rural PS", 6403: "Aland PS"}},
}

STATE = {1: "Karnataka"}

# Case categories (CaseCategoryID -> (code_digit, name)); code_digit is first digit of CrimeNo
CASE_CATEGORIES = {1: (1, "FIR"), 2: (3, "UDR"), 3: (8, "Zero FIR"), 4: (4, "PAR")}

# Gravity of offence
GRAVITY = {1: "Heinous", 2: "Non-Heinous"}

# Crime major heads and sub-heads
CRIME_HEADS = {
    1: "Crimes Against Property",
    2: "Crimes Against Body",
    3: "Economic Offences",
}
CRIME_SUBHEADS = {
    1: {"head": 1, "name": "Burglary / House-breaking"},
    2: {"head": 1, "name": "Theft"},
    3: {"head": 1, "name": "Robbery"},
    4: {"head": 2, "name": "Hurt"},
    5: {"head": 3, "name": "Cheating"},
}

# Case status
CASE_STATUS = {1: "Under Investigation", 2: "Charge Sheeted", 3: "Closed", 4: "Undetected"}

# Acts: BOTH BNS (current) and IPC (legacy, superseded). Real transition: BNS in force 01-Jul-2024.
ACTS = {
    "BNS": {"desc": "Bharatiya Nyaya Sanhita, 2023", "short": "BNS", "active": 1},
    "IPC": {"desc": "Indian Penal Code, 1860", "short": "IPC", "active": 0},
}

# Sections. BNS burglary-relevant sections + their IPC equivalents (IPC marked inactive).
# (ActCode, SectionCode, description, active)
SECTIONS = [
    ("BNS", "305", "Theft in dwelling house / house-breaking related theft", 1),
    ("BNS", "306", "Snatching", 1),
    ("BNS", "310", "Robbery", 1),
    ("BNS", "331", "House-trespass / house-breaking", 1),
    ("BNS", "303", "Theft", 1),
    ("BNS", "111", "Organised crime", 1),
    ("BNS", "318", "Cheating", 1),
    # Legacy IPC equivalents (Active=0)
    ("IPC", "380", "Theft in dwelling house (legacy)", 0),
    ("IPC", "457", "House-breaking by night (legacy)", 0),
    ("IPC", "392", "Robbery (legacy)", 0),
    ("IPC", "420", "Cheating (legacy)", 0),
]

RELIGIONS = {1: "Hindu", 2: "Muslim", 3: "Christian", 4: "Jain", 5: "Other"}
CASTES = {1: "General", 2: "OBC", 3: "SC", 4: "ST", 5: "Other"}
OCCUPATIONS = {1: "Farmer", 2: "Government Employee", 3: "Business", 4: "Daily Wage Labourer",
               5: "Student", 6: "Private Employee", 7: "Unemployed", 8: "Retired"}
GENDERS = {1: "M", 2: "F", 3: "T"}

RANKS = {1: "Constable", 2: "Head Constable", 3: "Sub-Inspector", 4: "Inspector", 5: "DSP"}
DESIGNATIONS = {1: "Investigating Officer", 2: "SHO", 3: "Beat Officer"}
UNIT_TYPES = {1: "Police Station", 2: "Circle Office", 3: "District HQ"}
ARREST_TYPES = {1: "Arrest", 2: "Voluntary Surrender"}
