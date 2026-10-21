"""
Example: building WellSky TEDS records with WellSkyTEDS.py.

Every value here is made up. Run it with:

    python example_build_records.py

It writes a KDADS_[license]_yyyyMMddHHmm.xml file and wellsky_predicted_errors.csv
into an example_output folder beside this script. Swap in your own data and output
folder (one approved for PHI) when you run it for real.
"""

from pathlib import Path

from WellSkyTEDS import Client, Episode, Substance, WellSkyTEDS


output = Path(__file__).resolve().parent / "example_output"

# One WellSkyTEDS collects everything for a run. The output folder is created if it doesn't exist.
teds = WellSkyTEDS(path=output)


# ----------------------------------------------------------------------
# Way 1: a whole client at once, from plain dicts.
# Handy when each client's data is already in rows or dicts.
# ----------------------------------------------------------------------
teds.add_record(
    client={
        "source_id": "80000001"          # the client's ID in your EHR
        ,"last_name": "Demo"
        ,"first_name": "Robin"
        ,"dob": "09231998"               # MMDDYYYY text, or a datetime.date
        ,"sex": "1"
        ,"race": "05"
        ,"hispanic_origin": "05"
        ,"gender_identity": "1"
        ,"sexual_orientation": "01"
        ,"county": "Reno"
        ,"state": "Kansas"
    }
    ,episodes=[{
        "license": "00987654"            # the location's license exactly as issued; names the file and is sent as ProviderID
        ,"admit_date": "04082024"
        ,"treatment_setting": "07"
        ,"client_type": "2"
        ,"referral_source": "01"
        ,"criminal_justice_referral": "96"
        ,"education": "12"
        ,"employment_status": "01"
        ,"not_in_labor_force": "96"
        ,"pregnant": "6"
        ,"veteran_status": "2"
        ,"living_arrangement": "03"
        ,"yearly_income": "18000"
        ,"federal_poverty_level": "2"
        ,"people_in_household": "2"
        ,"children_in_home": "2"
        ,"children_at_risk": "00"
        ,"income_source": "01"
        ,"payment_source": "04"
        ,"days_waiting": "003"
        ,"arrests": "00"
        ,"self_help": "01"
        ,"gambling_withdrawal": "2"
        ,"gambling_hidden": "2"
        ,"gambling_financial_trouble": "2"
        ,"tobacco_use": "2"
        ,"tb_positive": "1"
        ,"tb_education": "2"
        ,"tb_case_management": "2"
        ,"hiv": "2"
        ,"mh_treatment": "2"
        ,"co_occurring": "2"
        ,"psych_medication": "2"
        ,"su_history": "2"
        ,"mh_history": "2"
        ,"prior_sud_treatment": "2"
        ,"moud": "2"
        ,"diagnosis": "F10.20"
        ,"substances": [
            {"rank": "P", "substance": "02", "detailed_drug_code": "0201", "route": "01", "frequency": "05", "age_first_use": "15", "discharge_substance": "02", "discharge_frequency": "01"}
            ,{"rank": "S", "substance": "04", "detailed_drug_code": "0401", "route": "02", "frequency": "03", "age_first_use": "16", "discharge_substance": "04", "discharge_frequency": "01"}
        ]
        ,"discharge": {
            "discharge_date": "05202024"
            ,"discharge_reason": "01"
            ,"last_contact_date": "05172024"
            ,"employment_status": "01"
            ,"not_in_labor_force": "96"
            ,"living_arrangement": "03"
            ,"arrests": "00"
            ,"self_help": "02"
        }
    }]
)


# ----------------------------------------------------------------------
# Way 2: one object at a time, then attach them.
# Handy when clients, admissions and substances come from different files,
# as they often do when clients, admissions and substances are stored separately.
# ----------------------------------------------------------------------
client = Client(source_id="90000002", last_name="Sample", first_name="Lee", dob="07141985", sex="2", race="04"
                ,hispanic_origin="05", gender_identity="2", sexual_orientation="98", county="Sedgwick")

episode = Episode(license="00934567", admit_date="06032024", treatment_setting="06", client_type="2", referral_source="07"
                  ,criminal_justice_referral="03", education="14", employment_status="03", pregnant="2", veteran_status="2"
                  ,living_arrangement="03", yearly_income="0", federal_poverty_level="2", people_in_household="1"
                  ,children_in_home="2", children_at_risk="00", income_source="21", payment_source="04", arrests="00"
                  ,self_help="97", gambling_withdrawal="2", gambling_hidden="2", gambling_financial_trouble="2"
                  ,tobacco_use="1", tobacco_type="01", tobacco_30_days="1", tb_positive="1", tb_education="2"
                  ,tb_case_management="2", hiv="2", mh_treatment="1", co_occurring="1", psych_medication="1"
                  ,su_history="2", mh_history="1", prior_sud_treatment="1", prior_sud_episodes="2"
                  ,mh_treatment_episodes="01", moud="2", diagnosis="F15.20")
episode.add_substance(Substance(rank="P", substance="10", detailed_drug_code="1001", route="04", frequency="03", age_first_use="19"))
client.add_episode(episode)

# Still in treatment, so no set_discharge(). Check this client on its own before adding it:
for issue in client.predict_errors() + episode.predict_errors():
    print(issue["severity"], issue["element"], issue["message"])

teds.add_client(client)


# ----------------------------------------------------------------------
# Check everything, then write the XML and the predicted error report.
# ----------------------------------------------------------------------
summary = teds.execute()
print(f"{summary['errors']} predicted error(s), {summary['warnings']} warning(s). Files: {', '.join(summary['files'])}")
