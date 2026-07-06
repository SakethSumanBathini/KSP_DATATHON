"""
Component 2 — Schema definitions grounded in the real Karnataka Police ER diagram.
Defines table DDL (types, PKs, FKs) and the expected CSV->table column contract.
"""

# Each entry: table -> (create SQL, source CSV filename, expected columns [contract])
TABLES = {
    "State": (
        """CREATE TABLE State (StateID INTEGER PRIMARY KEY, StateName TEXT NOT NULL, Active INTEGER)""",
        "State.csv", ["StateID","StateName","Active"]),
    "District": (
        """CREATE TABLE District (DistrictID INTEGER PRIMARY KEY, DistrictName TEXT NOT NULL,
            StateID INTEGER, Active INTEGER, FOREIGN KEY(StateID) REFERENCES State(StateID))""",
        "District.csv", ["DistrictID","DistrictName","StateID","Active"]),
    "UnitType": (
        """CREATE TABLE UnitType (UnitTypeID INTEGER PRIMARY KEY, UnitTypeName TEXT, Active INTEGER)""",
        "UnitType.csv", ["UnitTypeID","UnitTypeName","Active"]),
    "Unit": (
        """CREATE TABLE Unit (UnitID INTEGER PRIMARY KEY, UnitName TEXT, TypeID INTEGER,
            StateID INTEGER, DistrictID INTEGER, Active INTEGER,
            FOREIGN KEY(DistrictID) REFERENCES District(DistrictID),
            FOREIGN KEY(StateID) REFERENCES State(StateID))""",
        "Unit.csv", ["UnitID","UnitName","TypeID","StateID","DistrictID","Active"]),
    "CaseCategory": (
        """CREATE TABLE CaseCategory (CaseCategoryID INTEGER PRIMARY KEY, CodeDigit INTEGER, LookupValue TEXT)""",
        "CaseCategory.csv", ["CaseCategoryID","CodeDigit","LookupValue"]),
    "GravityOffence": (
        """CREATE TABLE GravityOffence (GravityOffenceID INTEGER PRIMARY KEY, LookupValue TEXT)""",
        "GravityOffence.csv", ["GravityOffenceID","LookupValue"]),
    "CrimeHead": (
        """CREATE TABLE CrimeHead (CrimeHeadID INTEGER PRIMARY KEY, CrimeGroupName TEXT, Active INTEGER)""",
        "CrimeHead.csv", ["CrimeHeadID","CrimeGroupName","Active"]),
    "CrimeSubHead": (
        """CREATE TABLE CrimeSubHead (CrimeSubHeadID INTEGER PRIMARY KEY, CrimeHeadID INTEGER,
            CrimeHeadName TEXT, FOREIGN KEY(CrimeHeadID) REFERENCES CrimeHead(CrimeHeadID))""",
        "CrimeSubHead.csv", ["CrimeSubHeadID","CrimeHeadID","CrimeHeadName"]),
    "CaseStatusMaster": (
        """CREATE TABLE CaseStatusMaster (CaseStatusID INTEGER PRIMARY KEY, CaseStatusName TEXT)""",
        "CaseStatusMaster.csv", ["CaseStatusID","CaseStatusName"]),
    "ReligionMaster": (
        """CREATE TABLE ReligionMaster (ReligionID INTEGER PRIMARY KEY, ReligionName TEXT)""",
        "ReligionMaster.csv", ["ReligionID","ReligionName"]),
    "CasteMaster": (
        """CREATE TABLE CasteMaster (caste_master_id INTEGER PRIMARY KEY, caste_master_name TEXT)""",
        "CasteMaster.csv", ["caste_master_id","caste_master_name"]),
    "OccupationMaster": (
        """CREATE TABLE OccupationMaster (OccupationID INTEGER PRIMARY KEY, OccupationName TEXT)""",
        "OccupationMaster.csv", ["OccupationID","OccupationName"]),
    "Rank": (
        """CREATE TABLE Rank (RankID INTEGER PRIMARY KEY, RankName TEXT, Hierarchy INTEGER, Active INTEGER)""",
        "Rank.csv", ["RankID","RankName","Hierarchy","Active"]),
    "Designation": (
        """CREATE TABLE Designation (DesignationID INTEGER PRIMARY KEY, DesignationName TEXT, Active INTEGER)""",
        "Designation.csv", ["DesignationID","DesignationName","Active"]),
    "Court": (
        """CREATE TABLE Court (CourtID INTEGER PRIMARY KEY, CourtName TEXT, DistrictID INTEGER,
            StateID INTEGER, Active INTEGER, FOREIGN KEY(DistrictID) REFERENCES District(DistrictID))""",
        "Court.csv", ["CourtID","CourtName","DistrictID","StateID","Active"]),
    "Employee": (
        """CREATE TABLE Employee (EmployeeID INTEGER PRIMARY KEY, DistrictID INTEGER, UnitID INTEGER,
            RankID INTEGER, DesignationID INTEGER, KGID TEXT, FirstName TEXT, EmployeeDOB TEXT,
            GenderID INTEGER, AppointmentDate TEXT,
            FOREIGN KEY(UnitID) REFERENCES Unit(UnitID),
            FOREIGN KEY(DistrictID) REFERENCES District(DistrictID))""",
        "Employee.csv", ["EmployeeID","DistrictID","UnitID","RankID","DesignationID","KGID",
                         "FirstName","EmployeeDOB","GenderID","AppointmentDate"]),
    "Act": (
        """CREATE TABLE Act (ActCode TEXT PRIMARY KEY, ActDescription TEXT, ShortName TEXT, Active INTEGER)""",
        "Act.csv", ["ActCode","ActDescription","ShortName","Active"]),
    "Section": (
        """CREATE TABLE Section (ActCode TEXT, SectionCode TEXT, SectionDescription TEXT, Active INTEGER,
            PRIMARY KEY(ActCode, SectionCode), FOREIGN KEY(ActCode) REFERENCES Act(ActCode))""",
        "Section.csv", ["ActCode","SectionCode","SectionDescription","Active"]),
    "CaseMaster": (
        """CREATE TABLE CaseMaster (CaseMasterID INTEGER PRIMARY KEY, CrimeNo TEXT, CaseNo TEXT,
            CrimeRegisteredDate TEXT, PolicePersonID INTEGER, PoliceStationID INTEGER,
            CaseCategoryID INTEGER, GravityOffenceID INTEGER, CrimeMajorHeadID INTEGER,
            CrimeMinorHeadID INTEGER, CaseStatusID INTEGER, CourtID INTEGER,
            IncidentFromDate TEXT, IncidentToDate TEXT, InfoReceivedPSDate TEXT,
            latitude REAL, longitude REAL, BriefFacts TEXT,
            FOREIGN KEY(PoliceStationID) REFERENCES Unit(UnitID),
            FOREIGN KEY(CaseCategoryID) REFERENCES CaseCategory(CaseCategoryID),
            FOREIGN KEY(CaseStatusID) REFERENCES CaseStatusMaster(CaseStatusID),
            FOREIGN KEY(PolicePersonID) REFERENCES Employee(EmployeeID))""",
        "CaseMaster.csv", ["CaseMasterID","CrimeNo","CaseNo","CrimeRegisteredDate","PolicePersonID",
            "PoliceStationID","CaseCategoryID","GravityOffenceID","CrimeMajorHeadID","CrimeMinorHeadID",
            "CaseStatusID","CourtID","IncidentFromDate","IncidentToDate","InfoReceivedPSDate",
            "latitude","longitude","BriefFacts"]),
    "Accused": (
        """CREATE TABLE Accused (AccusedMasterID INTEGER PRIMARY KEY, CaseMasterID INTEGER,
            AccusedName TEXT, AgeYear INTEGER, GenderID INTEGER, PersonID TEXT,
            FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID))""",
        "Accused.csv", ["AccusedMasterID","CaseMasterID","AccusedName","AgeYear","GenderID","PersonID"]),
    "Victim": (
        """CREATE TABLE Victim (VictimMasterID INTEGER PRIMARY KEY, CaseMasterID INTEGER,
            VictimName TEXT, AgeYear INTEGER, GenderID INTEGER, VictimPolice INTEGER,
            FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID))""",
        "Victim.csv", ["VictimMasterID","CaseMasterID","VictimName","AgeYear","GenderID","VictimPolice"]),
    "ComplainantDetails": (
        """CREATE TABLE ComplainantDetails (ComplainantID INTEGER PRIMARY KEY, CaseMasterID INTEGER,
            ComplainantName TEXT, AgeYear INTEGER, OccupationID INTEGER, ReligionID INTEGER,
            CasteID INTEGER, GenderID INTEGER,
            FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
            FOREIGN KEY(OccupationID) REFERENCES OccupationMaster(OccupationID),
            FOREIGN KEY(ReligionID) REFERENCES ReligionMaster(ReligionID),
            FOREIGN KEY(CasteID) REFERENCES CasteMaster(caste_master_id))""",
        "ComplainantDetails.csv", ["ComplainantID","CaseMasterID","ComplainantName","AgeYear",
            "OccupationID","ReligionID","CasteID","GenderID"]),
    "ArrestSurrender": (
        """CREATE TABLE ArrestSurrender (ArrestSurrenderID INTEGER PRIMARY KEY, CaseMasterID INTEGER,
            ArrestSurrenderTypeID INTEGER, ArrestSurrenderDate TEXT, ArrestSurrenderStateId INTEGER,
            ArrestSurrenderDistrictId INTEGER, PoliceStationID INTEGER, IOID INTEGER, CourtID INTEGER,
            AccusedMasterID INTEGER, IsAccused INTEGER, IsComplainantAccused INTEGER,
            FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID),
            FOREIGN KEY(AccusedMasterID) REFERENCES Accused(AccusedMasterID),
            FOREIGN KEY(ArrestSurrenderDistrictId) REFERENCES District(DistrictID))""",
        "ArrestSurrender.csv", ["ArrestSurrenderID","CaseMasterID","ArrestSurrenderTypeID",
            "ArrestSurrenderDate","ArrestSurrenderStateId","ArrestSurrenderDistrictId","PoliceStationID",
            "IOID","CourtID","AccusedMasterID","IsAccused","IsComplainantAccused"]),
    "ActSectionAssociation": (
        """CREATE TABLE ActSectionAssociation (CaseMasterID INTEGER, ActID TEXT, SectionID TEXT,
            ActOrderID INTEGER, SectionOrderID INTEGER,
            FOREIGN KEY(CaseMasterID) REFERENCES CaseMaster(CaseMasterID))""",
        "ActSectionAssociation.csv", ["CaseMasterID","ActID","SectionID","ActOrderID","SectionOrderID"]),
}

# Load order respects FK dependencies (parents before children)
LOAD_ORDER = ["State","District","UnitType","Unit","CaseCategory","GravityOffence","CrimeHead",
    "CrimeSubHead","CaseStatusMaster","ReligionMaster","CasteMaster","OccupationMaster","Rank",
    "Designation","Court","Employee","Act","Section","CaseMaster","Accused","Victim",
    "ComplainantDetails","ArrestSurrender","ActSectionAssociation"]
