"""
KSP Datathon — Synthetic FIR Data Generator (Component 1)
Schema-accurate. Fixed seed. Builds 3 seeded connection sets + ground_truth.json.
Grounded in the real Karnataka Police ER diagram.
"""
import csv, json, random, os
from datetime import date, datetime, timedelta
from faker import Faker
from reference_data import *
from kannada_names import *

SEED = 20260706
random.seed(SEED)
fake = Faker("en_IN"); Faker.seed(SEED)

OUT = os.path.dirname(os.path.abspath(__file__))
N_FIRS = 500
YEAR = 2026

# ---------- global row stores ----------
rows = {k: [] for k in [
    "CaseMaster","Accused","Victim","ComplainantDetails","ArrestSurrender",
    "Act","Section","ActSectionAssociation","CrimeHead","CrimeSubHead",
    "District","State","Unit","UnitType","Employee","Rank","Designation",
    "CaseStatusMaster","GravityOffence","CaseCategory","ReligionMaster",
    "CasteMaster","OccupationMaster","Court"]}

# ground truth we assert as we build
GT = {"identity_mappings": [], "seeded_connections": {}, "entity_to_fir": []}

# ---------- reference tables ----------
for sid, name in STATE.items(): rows["State"].append({"StateID": sid, "StateName": name, "Active": 1})
for did, d in DISTRICTS.items():
    rows["District"].append({"DistrictID": did, "DistrictName": d["name"], "StateID": d["state_id"], "Active": 1})
for utid, n in UNIT_TYPES.items(): rows["UnitType"].append({"UnitTypeID": utid, "UnitTypeName": n, "Active": 1})
for did, d in DISTRICTS.items():
    for uid, uname in d["stations"].items():
        rows["Unit"].append({"UnitID": uid, "UnitName": uname, "TypeID": 1,
                             "StateID": d["state_id"], "DistrictID": did, "Active": 1})
for cid, (code, name) in CASE_CATEGORIES.items():
    rows["CaseCategory"].append({"CaseCategoryID": cid, "CodeDigit": code, "LookupValue": name})
for gid, n in GRAVITY.items(): rows["GravityOffence"].append({"GravityOffenceID": gid, "LookupValue": n})
for hid, n in CRIME_HEADS.items(): rows["CrimeHead"].append({"CrimeHeadID": hid, "CrimeGroupName": n, "Active": 1})
for shid, sh in CRIME_SUBHEADS.items():
    rows["CrimeSubHead"].append({"CrimeSubHeadID": shid, "CrimeHeadID": sh["head"], "CrimeHeadName": sh["name"]})
for sid, n in CASE_STATUS.items(): rows["CaseStatusMaster"].append({"CaseStatusID": sid, "CaseStatusName": n})
for rid, n in RELIGIONS.items(): rows["ReligionMaster"].append({"ReligionID": rid, "ReligionName": n})
for cid, n in CASTES.items(): rows["CasteMaster"].append({"caste_master_id": cid, "caste_master_name": n})
for oid, n in OCCUPATIONS.items(): rows["OccupationMaster"].append({"OccupationID": oid, "OccupationName": n})
for rid, n in RANKS.items(): rows["Rank"].append({"RankID": rid, "RankName": n, "Hierarchy": rid, "Active": 1})
for did, n in DESIGNATIONS.items(): rows["Designation"].append({"DesignationID": did, "DesignationName": n, "Active": 1})
for code, a in ACTS.items():
    rows["Act"].append({"ActCode": code, "ActDescription": a["desc"], "ShortName": a["short"], "Active": a["active"]})
for (ac, sc, desc, act) in SECTIONS:
    rows["Section"].append({"ActCode": ac, "SectionCode": sc, "SectionDescription": desc, "Active": act})

# employees (IOs) per station
emp_id = 7000
station_ios = {}
for did, d in DISTRICTS.items():
    for uid in d["stations"]:
        ios = []
        for _ in range(2):
            emp_id += 1
            rows["Employee"].append({"EmployeeID": emp_id, "DistrictID": did, "UnitID": uid,
                "RankID": random.choice([3,4]), "DesignationID": 1,
                "KGID": f"KG{emp_id}", "FirstName": random.choice(ROMAN_MALE),
                "EmployeeDOB": str(fake.date_of_birth(minimum_age=28, maximum_age=55)),
                "GenderID": 1, "AppointmentDate": str(fake.date_between('-20y','-2y'))})
            ios.append(emp_id)
        station_ios[uid] = ios

# courts per district
court_id = 8000
district_courts = {}
for did, d in DISTRICTS.items():
    court_id += 1
    rows["Court"].append({"CourtID": court_id, "CourtName": f"{d['name']} District Court",
                          "DistrictID": did, "StateID": 1, "Active": 1})
    district_courts[did] = court_id

# ---------- helpers ----------
def crime_no(cat_digit, district_id, unit_id, year, serial):
    return f"{cat_digit}{district_id:04d}{unit_id:04d}{year}{serial:05d}"

def rand_latlng(did):
    base = {1:(12.97,77.59),2:(12.30,76.65),3:(15.85,74.50),4:(12.91,74.85),5:(17.33,76.83)}
    la,lo = base[did]; return round(la+random.uniform(-0.05,0.05),6), round(lo+random.uniform(-0.05,0.05),6)

_issued_phones=set()
def phone():
    while True:
        p="+91"+str(random.randint(6000000000,9999999999))
        if p not in _issued_phones: _issued_phones.add(p); return p
def phone_messy(p): return p[3:6] + " " + p[6:9] + " " + p[9:]  # spaced 10-digit form
_issued_vehicles=set()
def vehicle(did):
    while True:
        seq=f"{random.randint(0,9999):04d}"
        v=f"KA-{did:02d}-{random.choice(['AB','MN','XY','CD'])}-{seq}"
        if v not in _issued_vehicles: _issued_vehicles.add(v); return v
def upi(name): return name.lower().replace(" ","").replace(".","")[:8] + "@" + random.choice(["okaxis","oksbi","okhdfc","paytm"])

serials = {}
def next_serial(unit_id, cat):
    k=(unit_id,cat,YEAR); serials[k]=serials.get(k,0)+1; return serials[k]

case_id=0; accused_id=0; victim_id=0; comp_id=0; arrest_id=0

def new_name(gender_id, script_chance=0.25):
    if gender_id==1:
        if random.random()<script_chance: return random.choice(KANNADA_MALE)
        return random.choice(ROMAN_MALE)+" "+random.choice(ROMAN_SURNAME)
    else:
        if random.random()<script_chance: return random.choice(KANNADA_FEMALE)
        return random.choice(ROMAN_FEMALE)+" "+random.choice(ROMAN_SURNAME)

def make_case(did, unit_id, cat=1, subhead=1, gravity=2, when=None, brief="", status=1):
    global case_id
    case_id+=1
    cat_digit = CASE_CATEGORIES[cat][0]
    serial = next_serial(unit_id,cat)
    cn = crime_no(cat_digit, did, unit_id, YEAR, serial)
    if when is None: when = fake.date_between('-300d','-10d')
    inc_from = datetime.combine(when, datetime.min.time()) + timedelta(hours=random.randint(0,23))
    inc_to = inc_from + timedelta(hours=random.randint(1,6))
    la,lo = rand_latlng(did)
    io = random.choice(station_ios[unit_id])
    rows["CaseMaster"].append({
        "CaseMasterID": case_id, "CrimeNo": cn, "CaseNo": f"{YEAR}{serial:05d}",
        "CrimeRegisteredDate": str(when), "PolicePersonID": io, "PoliceStationID": unit_id,
        "CaseCategoryID": cat, "GravityOffenceID": gravity, "CrimeMajorHeadID": CRIME_SUBHEADS[subhead]["head"],
        "CrimeMinorHeadID": subhead, "CaseStatusID": status, "CourtID": district_courts[did],
        "IncidentFromDate": inc_from.strftime("%Y-%m-%d %H:%M:%S"),
        "IncidentToDate": inc_to.strftime("%Y-%m-%d %H:%M:%S"),
        "InfoReceivedPSDate": inc_to.strftime("%Y-%m-%d %H:%M:%S"),
        "latitude": la, "longitude": lo, "BriefFacts": brief})
    # act-section: BNS burglary sections for burglary; some legacy IPC on older cases
    if subhead==1: secs=[("BNS","331"),("BNS","305")]
    elif subhead==2: secs=[("BNS","303")]
    elif subhead==3: secs=[("BNS","310")]
    elif subhead==5: secs=[("BNS","318")]
    else: secs=[("BNS","305")]
    for i,(ac,sc) in enumerate(secs):
        rows["ActSectionAssociation"].append({"CaseMasterID": case_id,"ActID": ac,"SectionID": sc,
                                              "ActOrderID":1,"SectionOrderID":i+1})
    return case_id, unit_id, did

def add_accused(cid, name, age, gender, person_label="A1"):
    global accused_id
    accused_id+=1
    rows["Accused"].append({"AccusedMasterID": accused_id,"CaseMasterID": cid,"AccusedName": name,
                            "AgeYear": age,"GenderID": gender,"PersonID": person_label})
    return accused_id

def add_victim(cid):
    global victim_id
    victim_id+=1; g=random.choice([1,2])
    rows["Victim"].append({"VictimMasterID": victim_id,"CaseMasterID": cid,"VictimName": new_name(g),
                           "AgeYear": random.randint(18,75),"GenderID": g,"VictimPolice": 0})

def add_complainant(cid):
    global comp_id
    comp_id+=1; g=random.choice([1,2])
    rows["ComplainantDetails"].append({"ComplainantID": comp_id,"CaseMasterID": cid,
        "ComplainantName": new_name(g),"AgeYear": random.randint(18,75),
        "OccupationID": random.choice(list(OCCUPATIONS)),"ReligionID": random.choice(list(RELIGIONS)),
        "CasteID": random.choice(list(CASTES)),"GenderID": g})

def add_arrest(cid, amid, did, unit_id):
    global arrest_id
    arrest_id+=1
    rows["ArrestSurrender"].append({"ArrestSurrenderID": arrest_id,"CaseMasterID": cid,
        "ArrestSurrenderTypeID": 1,"ArrestSurrenderDate": str(fake.date_between('-200d','-5d')),
        "ArrestSurrenderStateId": 1,"ArrestSurrenderDistrictId": did,"PoliceStationID": unit_id,
        "IOID": random.choice(station_ios[unit_id]),"CourtID": district_courts[did],
        "AccusedMasterID": amid,"IsAccused": 1,"IsComplainantAccused": 0})

# ================= SEEDED CONNECTION SET A: Mysuru burglary cluster =================
# 14 burglary FIRs in Mysuru; 3 accused share ONE phone across 5 FIRs; 1 UPI links 2 of them;
# near-repeat spatial cluster within ~400m over ~42 days; consistent MO.
mysuru_stations = list(DISTRICTS[2]["stations"].keys())
clusterA_phone = phone()
clusterA_upi = upi("rameshgowda")
clusterA_center = (12.315, 76.655)  # tight cluster near Mysuru East
clusterA_start = date(2026,3,1)
clusterA = {"phone": clusterA_phone, "upi": clusterA_upi, "fir_ids": [], "shared_phone_firs": [],
            "upi_firs": [], "accused_ids": []}

# three accused identities that recur
A1_name="Ramesh Gowda"; A2_name="Suresh Naik"; A3_name="ಮಂಜುನಾಥ್"
clusterA_names=[A1_name,A2_name,A3_name]
clusterA_ages=[random.randint(28,45) for _ in range(3)]   # FIXED age per true person
clusterA_person_phones=[phone() for _ in range(3)]   # each true person's OWN recurring phone
clusterA_accused_by_person={0:[],1:[],2:[]}

for i in range(14):
    unit=random.choice(mysuru_stations)
    day=clusterA_start+timedelta(days=int(i*3))  # spread across ~42 days
    la=round(clusterA_center[0]+random.uniform(-0.0025,0.0025),6)  # ~<400m
    lo=round(clusterA_center[1]+random.uniform(-0.0025,0.0025),6)
    has_phone = i<5      # first 5 FIRs carry the shared phone
    has_upi = i in (1,3) # 2 of them carry the shared UPI
    # MO consistent: night-time ground-floor glass-breaking
    who = clusterA_names[i%3]
    person_phone = clusterA_person_phones[i%3]
    phone_txt = f" The accused was traced to mobile number {phone_messy(person_phone) if i%2 else person_phone}."
    if has_phone:
        phone_txt += f" A co-offender was contacted on {clusterA_phone}."
    upi_txt = (f" Stolen valuables were later liquidated; a transfer to UPI ID {clusterA_upi} was identified."
               if has_upi else "")
    brief=(f"On the night of {day.strftime('%d-%m-%Y')}, unknown persons broke into a ground-floor "
           f"residence by breaking the rear window glass while the occupants were away. Gold ornaments "
           f"and cash were stolen. Suspect identified as {who}.{phone_txt}{upi_txt} "
           f"Investigation continuing under night house-breaking provisions.")
    cid,u,dd=make_case(2,unit,cat=1,subhead=1,gravity=1,when=day,brief=brief,status=1)
    # override lat/lng to cluster tightly
    rows["CaseMaster"][-1]["latitude"]=la; rows["CaseMaster"][-1]["longitude"]=lo
    amid=add_accused(cid, who, clusterA_ages[i%3], 1)   # consistent age for this true person
    add_complainant(cid); add_victim(cid)
    clusterA["fir_ids"].append(cid)
    clusterA_accused_by_person[i%3].append(amid)
    GT["entity_to_fir"].append({"type":"phone","value":person_phone,"case_id":cid})
    if has_phone:
        clusterA["shared_phone_firs"].append(cid)
        GT["entity_to_fir"].append({"type":"phone","value":clusterA_phone,"case_id":cid})
    if has_upi:
        clusterA["upi_firs"].append(cid)
        GT["entity_to_fir"].append({"type":"upi","value":clusterA_upi,"case_id":cid})

# record identity groupings for the 3 recurring cluster accused
for p in range(3):
    ids=clusterA_accused_by_person[p]
    if len(ids)>1:
        GT["identity_mappings"].append({"true_person":f"CLUSTERA_PERSON_{p}","accused_ids":ids,
                                        "name_used":clusterA_names[p]})
    clusterA["accused_ids"].extend(ids)
GT["seeded_connections"]["set_A_mysuru_cluster"]={
    "description":"14 burglary FIRs, shared phone across 5, shared UPI across 2, near-repeat spatial cluster",
    "phone":clusterA_phone,"upi":clusterA_upi,
    "fir_ids":clusterA["fir_ids"],"shared_phone_fir_ids":clusterA["shared_phone_firs"],
    "shared_upi_fir_ids":clusterA["upi_firs"]}

# ================= SEEDED CONNECTION SET B: cross-district shared vehicle =================
# ONE accused in a Bengaluru Urban FIR and a Belagavi FIR, SAME vehicle in both BriefFacts, different IOs.
setB_vehicle=vehicle(1)
setB_name="Prakash Reddy"; setB_age=31
blr_unit=random.choice(list(DISTRICTS[1]["stations"].keys()))
bgv_unit=random.choice(list(DISTRICTS[3]["stations"].keys()))
briefB1=(f"A robbery was reported near a commercial complex. Witnesses noted a white car bearing "
         f"registration {setB_vehicle} leaving the scene at speed. Suspect described matching {setB_name}. "
         f"CCTV footage under examination.")
cidB1,_,_=make_case(1,blr_unit,cat=1,subhead=3,gravity=1,brief=briefB1,status=1)
amidB1=add_accused(cidB1,setB_name,setB_age,1); add_complainant(cidB1); add_victim(cidB1)
briefB2=(f"A house-breaking was reported. A vehicle seen in the vicinity carried the number {setB_vehicle}. "
         f"The same individual, {setB_name}, was named by a local informant. Case under investigation.")
cidB2,_,_=make_case(3,bgv_unit,cat=1,subhead=1,gravity=1,brief=briefB2,status=1)
amidB2=add_accused(cidB2,setB_name,setB_age,1); add_complainant(cidB2); add_victim(cidB2)
GT["identity_mappings"].append({"true_person":"SETB_PERSON_PRAKASH","accused_ids":[amidB1,amidB2],"name_used":setB_name})
GT["seeded_connections"]["set_B_cross_district_vehicle"]={
    "description":"Same accused + same vehicle across Bengaluru Urban and Belagavi FIRs, different IOs",
    "vehicle":setB_vehicle,"fir_ids":[cidB1,cidB2],"accused_ids":[amidB1,amidB2]}
GT["entity_to_fir"].append({"type":"vehicle","value":setB_vehicle,"case_id":cidB1})
GT["entity_to_fir"].append({"type":"vehicle","value":setB_vehicle,"case_id":cidB2})

# ================= SEEDED CONNECTION SET C: Kannada name-variant identity =================
# ONE person, three name spellings across three FIRs.
setC=KANNADA_VARIANT_IDENTITY
setC_accused_ids=[]
setC_fir_ids=[]
setC_units=[random.choice(list(DISTRICTS[d]["stations"].keys())) for d in (1,2,4)]
setC_shared_phone=phone()
setC_shared_vehicle=vehicle(2)
for idx,variant in enumerate(setC["variants"]):
    unit=setC_units[idx]; did=[1,2,4][idx]
    brief=(f"An accused person recorded in station papers as '{variant}' was named in connection with a "
           f"house theft. The individual, aged about {setC['age']}, is reported to operate across localities. "
           f"The suspect was contacted on mobile number {setC_shared_phone}. "
           f"A two-wheeler bearing {setC_shared_vehicle} was linked to the suspect. Identity verification pending.")
    cid,_,_=make_case(did,unit,cat=1,subhead=2,gravity=2,brief=brief,status=1)
    amid=add_accused(cid,variant,setC["age"],setC["gender_id"])
    add_complainant(cid); add_victim(cid)
    setC_accused_ids.append(amid); setC_fir_ids.append(cid)
GT["identity_mappings"].append({"true_person":setC["true_person_label"],
    "accused_ids":setC_accused_ids,"name_variants":setC["variants"],
    "note":"Same real person, three transliteration/script variants — the core ER test case"})
for _cid in setC_fir_ids:
    GT["entity_to_fir"].append({"type":"phone","value":setC_shared_phone,"case_id":_cid})
    GT["entity_to_fir"].append({"type":"vehicle","value":setC_shared_vehicle,"case_id":_cid})
GT["seeded_connections"]["set_C_kannada_variant_identity"]={
    "description":"One person written 3 ways (ರಾಮಯ್ಯ.ಕೆ / Ramaiah K / ರಾಮು) across 3 FIRs",
    "name_variants":setC["variants"],"fir_ids":setC_fir_ids,"accused_ids":setC_accused_ids}

# ================= BACKGROUND / NOISE CASES to reach ~500 =================
# includes decoys: other people also named "Ramesh"-ish to make ER non-trivial
def add_decoy_ramesh(did,unit):
    # a DIFFERENT real person who also happens to be a Ramesh, ~34, to stress ER precision
    brief=("A theft complaint was filed at the local market. The named suspect, Ramesh, aged about 34, "
           "is a resident of a nearby locality. No prior linkage established. Under enquiry.")
    cid,_,_=make_case(did,unit,cat=1,subhead=2,gravity=2,brief=brief,status=1)
    amid=add_accused(cid,"Ramesh",34,1); add_complainant(cid); add_victim(cid)
    return cid,amid

decoy_ids=[]
for _ in range(6):
    did=random.choice(list(DISTRICTS)); unit=random.choice(list(DISTRICTS[did]["stations"].keys()))
    cid,amid=add_decoy_ramesh(did,unit); decoy_ids.append(amid)

# HARD near-match decoys: plausibly-confusable DIFFERENT people (the real ER precision test).
# Similar names + close ages + same district, but different people with NO shared entity.
hard_decoy_ids=[]
hard_decoy_sets=[
    # (name_a, age_a, name_b, age_b, district) — a weak resolver would wrongly merge these
    ("Manjunath Gowda", 41, "Manjunatha Gowda", 42, 2),   # spelling variant, 1yr apart, same district
    ("Suresh Kumar", 35, "Suresh Kumara", 36, 1),          # near-identical name, close age
    ("Ramesh Naik", 29, "Ramesh Naika", 30, 3),            # transliteration-length variant
    ("Prakash B", 47, "Prakash Bhat", 48, 4),              # abbreviation vs full, close age
    ("Nagaraj R", 52, "Nagaraja R", 53, 2),                # Kannada-style ending variant
]
for (na,aa,nb,ab,did) in hard_decoy_sets:
    unit=random.choice(list(DISTRICTS[did]["stations"].keys()))
    briefA=(f"A house-breaking was reported. The suspect, {na}, aged about {aa}, is under enquiry. "
            f"No phone or vehicle was recovered from the scene. Investigation continues.")
    cidA,_,_=make_case(did,unit,cat=1,subhead=1,gravity=2,brief=briefA,status=1)
    amidA=add_accused(cidA,na,aa,1); add_complainant(cidA); add_victim(cidA)
    unit2=random.choice(list(DISTRICTS[did]["stations"].keys()))
    briefB=(f"A theft case names {nb}, aged around {ab}, as the accused. No distinguishing "
            f"evidence such as a mobile number or vehicle was found. Enquiry pending.")
    cidB,_,_=make_case(did,unit2,cat=1,subhead=2,gravity=2,brief=briefB,status=1)
    amidB=add_accused(cidB,nb,ab,1); add_complainant(cidB); add_victim(cidB)
    hard_decoy_ids.append((amidA,amidB))
GT["seeded_connections"]["hard_near_match_decoys"]={
    "description":"5 PAIRS of plausibly-confusable DIFFERENT people (similar name+age+district, "
                  "NO shared entity). A weak resolver merges these; a correct one must NOT. "
                  "These pairs are the precision test — they must stay SEPARATE.",
    "must_not_merge_pairs":hard_decoy_ids}
GT["seeded_connections"]["decoy_rameshes"]={
    "description":"6 DIFFERENT people all named 'Ramesh' age 34 — must NOT be merged with each other or with the variant identity",
    "accused_ids":decoy_ids}

while case_id < N_FIRS:
    did=random.choice(list(DISTRICTS)); unit=random.choice(list(DISTRICTS[did]["stations"].keys()))
    subhead=random.choice([1,1,2,2,3,4,5]); gravity=random.choice([1,2])
    n_acc=random.choice([1,1,1,2])
    embed_phone=random.random()<0.5; embed_veh=random.random()<0.25; embed_upi=random.random()<0.15
    p=phone(); v=vehicle(did)
    nm=new_name(1)
    ptxt=f" A mobile number {p if random.random()<0.5 else phone_messy(p)} was linked to the suspect." if embed_phone else ""
    vtxt=f" A two-wheeler bearing {v} was seen nearby." if embed_veh else ""
    utxt=f" A suspicious transfer to {upi(nm.split()[0] if ' ' in nm else 'suspect')} was noted." if embed_upi else ""
    brief=(f"A {CRIME_SUBHEADS[subhead]['name'].lower()} was reported in the jurisdiction. "
           f"Preliminary enquiry names {nm} as a suspect.{ptxt}{vtxt}{utxt} Investigation is ongoing.")
    cid,u,dd=make_case(did,unit,cat=1,subhead=subhead,gravity=gravity,brief=brief,
                       status=random.choice([1,1,2,3,4]))
    amid=add_accused(cid,nm,random.randint(19,60),1)
    if n_acc==2: add_accused(cid,new_name(1),random.randint(19,60),1,"A2")
    add_complainant(cid); add_victim(cid)
    if random.random()<0.4: add_arrest(cid,amid,dd,u)
    if embed_phone: GT["entity_to_fir"].append({"type":"phone","value":p,"case_id":cid})
    if embed_veh: GT["entity_to_fir"].append({"type":"vehicle","value":v,"case_id":cid})

# ---------- write CSVs ----------
def write_csv(name):
    data=rows[name]
    if not data:
        open(os.path.join(OUT,f"{name}.csv"),"w").close(); return 0
    keys=list(data[0].keys())
    with open(os.path.join(OUT,f"{name}.csv"),"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=keys); w.writeheader(); w.writerows(data)
    return len(data)

counts={n:write_csv(n) for n in rows}

# ---------- write ground truth ----------
GT["meta"]={"seed":SEED,"n_firs":counts["CaseMaster"],"generated":datetime.now().isoformat()}
with open(os.path.join(OUT,"ground_truth.json"),"w",encoding="utf-8") as f:
    json.dump(GT,f,indent=2,ensure_ascii=False)

print("=== GENERATION COMPLETE ===")
print(f"Seed: {SEED}")
for n in ["CaseMaster","Accused","Victim","ComplainantDetails","ArrestSurrender",
          "Act","Section","ActSectionAssociation"]:
    print(f"  {n}: {counts[n]}")
print(f"Identity mappings in ground truth: {len(GT['identity_mappings'])}")
print(f"Entity->FIR links in ground truth: {len(GT['entity_to_fir'])}")
print(f"Seeded connection sets: {list(GT['seeded_connections'].keys())}")
