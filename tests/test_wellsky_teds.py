"""
Unit tests for WellSkyTEDS.py. Every record here is made up.
Run from the WellSkyTEDS folder with: python -m pytest tests
"""

import datetime
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from WellSkyTEDS import Client, ConsoleMonitor, Episode, Substance, WellSkyPredictor, WellSkyRules, WellSkyTEDS, main  # noqa: E402

# A real WellSky export on test clients, when one is available: tests/sample_export.xml,
# or the file named by the WELLSKY_SAMPLE_XML environment variable.
SAMPLE = Path(os.environ.get("WELLSKY_SAMPLE_XML") or Path(__file__).resolve().parent / "sample_export.xml")
NOW = datetime.datetime(2026, 9, 14, 8, 15)


def client_values(**changes):
    """A complete, valid made-up client."""
    values = dict(source_id="80000001", last_name="Demo", first_name="Robin", dob="09231998", sex="1", race="05"
                  , hispanic_origin="05", gender_identity="1", sexual_orientation="01", county="Reno", state="Kansas")
    values.update(changes)
    return values


def episode_values(**changes):
    """A complete, valid made-up admission."""
    values = dict(license="00987654", admit_date="04082024", treatment_setting="07", client_type="2", referral_source="01"
                  , criminal_justice_referral="96", education="12", employment_status="01", not_in_labor_force="96"
                  , pregnant="6", veteran_status="2", living_arrangement="03", yearly_income="18000", federal_poverty_level="2"
                  , people_in_household="2", children_in_home="2", children_at_risk="00", income_source="01", payment_source="04"
                  , days_waiting="003", arrests="00", self_help="01", gambling_withdrawal="2", gambling_hidden="2"
                  , gambling_financial_trouble="2", tobacco_use="2", tb_positive="1", tb_education="2", tb_case_management="2"
                  , hiv="2", mh_treatment="2", co_occurring="2", psych_medication="2", su_history="2", mh_history="2"
                  , prior_sud_treatment="2", moud="2", diagnosis="F10.20")
    values.update(changes)
    return values


def substance_values():
    """A primary and a secondary substance, each with discharge values."""
    return [
        dict(rank="P", substance="02", detailed_drug_code="0201", route="01", frequency="05", age_first_use="15", discharge_substance="02", discharge_frequency="01")
        ,dict(rank="S", substance="04", detailed_drug_code="0401", route="02", frequency="03", age_first_use="16", discharge_substance="04", discharge_frequency="01")
    ]


def discharge_values(**changes):
    """A valid discharge."""
    values = dict(discharge_date="05202024", discharge_reason="01", last_contact_date="05172024", employment_status="01"
                  , not_in_labor_force="96", living_arrangement="03", arrests="00", self_help="02")
    values.update(changes)
    return values


def make_teds(tmp_path=None, **kwargs):
    """A WellSkyTEDS that logs quietly."""
    return WellSkyTEDS(path=tmp_path, now=NOW, monitor=ConsoleMonitor(verbose=False), **kwargs)


def add_full_record(teds, client=None, episode=None, substances=None, discharge=None):
    """Adds one made-up client with one discharged episode, using add_record()."""
    item = dict(episode or episode_values(), substances=substances if(substances is not None) else substance_values())
    item["discharge"] = discharge if(discharge is not None) else discharge_values()
    return teds.add_record(client or client_values(), [item])


def errors(issues, element=None):
    """Error-severity issues, optionally for one element."""
    return [i for i in issues if(i["severity"] == "Error" and (element is None or i["element"] == element))]


def warnings(issues, element=None):
    """Warning-severity issues, optionally for one element."""
    return [i for i in issues if(i["severity"] == "Warning" and (element is None or i["element"] == element))]


# ----------------------------------------------------------------------
# Building
# ----------------------------------------------------------------------
def test_a_complete_record_has_no_predicted_errors():
    teds = make_teds()
    add_full_record(teds)
    assert teds.predict_errors() == []


def test_both_ways_of_building_write_the_same_xml():
    whole = make_teds()
    add_full_record(whole)

    pieces = make_teds()
    client = Client(**client_values())
    episode = client.add_episode(Episode(**episode_values()))
    for values in substance_values():
        episode.add_substance(Substance(**values))
    episode.set_discharge(**discharge_values())
    pieces.add_client(client)

    assert whole.build_files() == pieces.build_files()


def test_xml_follows_the_sample_exports_shape():
    teds = make_teds()
    add_full_record(teds)
    files = teds.build_files()
    assert list(files) == ["KDADS_00987654_202609140815.xml"]
    text = files["KDADS_00987654_202609140815.xml"]
    assert text.startswith('<?xml version="1.0" encoding="UTF-8"?><KSTeds><StateCode>KS</StateCode><ReportingDate>09142026</ReportingDate><Client>')
    assert "\n" not in text
    root = ET.fromstring(text.encode())
    client = root.find("Client")
    assert [c.tag for c in client if(c.tag in ("Admission", "Discharge"))] == ["Admission", "Discharge"]
    # Blanks are written as empty tags.
    assert "<AKA />" in text and client.find("AKA").text is None
    admission, discharge = client.find("Admission"), client.find("Discharge")
    assert admission.find("ProviderID").text == "00987654"
    assert admission.find("ClientTransactionType").text == "A"
    assert discharge.find("ClientTransactionType").text == "D"
    # The default episode SourceID: setting + license + client ID + admission date.
    assert admission.find("SourceID").text == "07" + "00987654" + "80000001" + "04082024"
    assert discharge.find("SourceID").text == admission.find("SourceID").text
    assert discharge.find("TreatmentEvent/SourceID").text == admission.find("TreatmentEvent/SourceID").text
    assert discharge.find("TreatmentSetting").text == "07"
    assert discharge.find("TreatmentEvent/SecondaryFrequency").text == "01"
    assert discharge.find("ReferralSource") is None
    assert admission.find("DateOFDischarge") is None


def test_one_file_per_license_and_one_client_element_per_client():
    teds = make_teds()
    client = Client(**client_values(), rules=teds.rules)
    first = client.add_episode(Episode(**episode_values(), rules=teds.rules))
    second = client.add_episode(Episode(**episode_values(license="00923456", admit_date="02012024"), rules=teds.rules))
    for episode in (first, second):
        episode.add_substance(Substance(**substance_values()[0]))
    teds.add_client(client)
    files = teds.build_files()
    assert sorted(files) == ["KDADS_00923456_202609140815.xml", "KDADS_00987654_202609140815.xml"]
    two = make_teds()
    two_client = Client(**client_values())
    for admit in ("04082024", "02012024"):
        two_client.add_episode(Episode(**episode_values(admit_date=admit))).add_substance(Substance(**substance_values()[0]))
    two.add_client(two_client)
    root = ET.fromstring(two.build_files()["KDADS_00987654_202609140815.xml"].encode())
    # All of one client's records sit in one <Client>, as WellSky's provider instructions require.
    assert len(root.findall("Client")) == 1
    assert [a.find("DateOfAdmission").text for a in root.find("Client").findall("Admission")] == ["04082024", "02012024"]
    assert not any(i["element"] == "Client" for i in two.predict_errors())


def test_values_are_sent_as_given_and_dates_are_formatted():
    rules = WellSkyRules()
    assert rules.text(None) == ""
    assert rules.text(" 05 ") == "05"
    assert rules.text(3) == "3"
    assert rules.text(datetime.date(2024, 1, 5)) == "01052024"
    # Licenses are sent exactly as given: nothing is padded or added.
    assert rules.license_text("912345") == "912345"
    assert rules.license_text(" KDADS000001A ") == "KDADS000001A"
    assert rules.license_text("00987654") == "00987654"
    episode = Episode(license="00987654", admit_date="04082024", provider_id="10000")
    assert (episode.license, episode.values["ProviderID"]) == ("00987654", "10000")


def test_explicit_ids_and_enroll_type():
    episode = Episode(license="00987654", admit_date="04082024", treatment_setting="04", source_id="EP-1", event_source_id="EV-1")
    assert episode.values["EnrollType"] == "Inpatient"
    assert episode.source_id() == "EP-1"
    assert Episode(license="1", admit_date="04082024").source_id() == ""
    record, event = episode.record_values("Admission")
    assert (record["SourceID"], event["SourceID"]) == ("EP-1", "EV-1")
    episode.set_discharge(discharge_date="02012024")
    record, event = episode.record_values("Discharge")
    assert record["DateOfLastContact"] == "02012024"
    assert event["SourceID"] == "EV-1"


def test_exclude_errors_leaves_out_episodes_with_errors():
    teds = make_teds(exclude_errors=True)
    add_full_record(teds)
    add_full_record(teds, client=client_values(source_id="90000002", county=""))
    root = ET.fromstring(teds.build_files()["KDADS_00987654_202609140815.xml"].encode())
    assert [c.find("SourceID").text for c in root.findall("Client")] == ["80000001"]


def test_episode_without_license_is_left_out():
    teds = make_teds()
    add_full_record(teds, episode=episode_values(license=""))
    assert teds.build_files() == {}


# ----------------------------------------------------------------------
# Predicting
# ----------------------------------------------------------------------
def test_required_and_code_checks():
    teds = make_teds()
    add_full_record(teds, client=client_values(county="", race="5"), episode=episode_values(payment_source="", senate_bill_6="2"))
    issues = teds.predict_errors()
    assert errors(issues, "CountyofResidence")[0]["error"] == "Required field not populated"
    assert "'05'" in errors(issues, "Race")[0]["message"]
    assert errors(issues, "PrimaryPaymentSource")[0]["record_type"] == "Admission"
    assert errors(issues, "SenateBill6Secondary")[0]["value"] == "2"


def test_names_are_left_out_of_the_report_and_states_match_any_case():
    teds = make_teds()
    add_full_record(teds, client=client_values(last_name="X" * 31, state="KANSAS", county="harvey"))
    issues = teds.predict_errors()
    assert errors(issues, "LastName")[0]["value"] == ""
    assert not errors(issues, "State") and not errors(issues, "CountyofResidence")


def test_conditional_rules():
    teds = make_teds()
    add_full_record(teds, client=client_values(sex="2"), episode=episode_values(
        referral_source="07", criminal_justice_referral="", pregnant="", employment_status="04", not_in_labor_force="96"
        , tobacco_use="1", tb_positive="2", prior_sud_treatment="1", prenatal_care="1"))
    issues = teds.predict_errors()
    for tag in ("CriminalJusticeReferral", "PregnantAtAdmission", "TypeOfTobacco", "Tobacco30", "TBRisk", "TBSymptoms", "PrevSUDTxEp", "MHTxEp"):
        assert errors(issues, tag), tag
    assert errors(issues, "NotInLaborForce")[0]["error"] == "Invalid value"
    assert warnings(issues, "PrenatalCare")
    answered = make_teds()
    add_full_record(answered, episode=episode_values(tobacco_use="2", tobacco_30_days="2"))
    assert warnings(answered.predict_errors(), "Tobacco30")[0]["message"] == "Not answered when TobaccoUse is 2."


def test_more_conditional_rules():
    teds = make_teds()
    add_full_record(teds, episode=episode_values(referral_source="07", criminal_justice_referral="96", employment_status="04", not_in_labor_force="", treatment_setting="96"))
    add_full_record(teds, client=client_values(source_id="90000002"), episode=episode_values(criminal_justice_referral="02", not_in_labor_force="01"))
    issues = teds.predict_errors()
    assert errors(issues, "CriminalJusticeReferral")[0]["error"] == "Invalid value"
    assert errors(issues, "NotInLaborForce")[0]["error"] == "Required field not populated"
    assert errors(issues, "TreatmentSetting")[0]["error"].startswith("Value not applicable unless Client Type")
    assert warnings(issues, "CriminalJusticeReferral") and warnings(issues, "NotInLaborForce")


def test_collateral_clients_need_less():
    teds = make_teds()
    add_full_record(teds, episode=episode_values(client_type="1", treatment_setting="96", education="", hiv=""), substances=[])
    issues = teds.predict_errors()
    assert not errors(issues, "HighestLevelOfEducation") and not errors(issues, "HIV") and not errors(issues, "TreatmentSetting")
    assert not errors(issues, "PrimarySubstance")


def test_employment_status_and_age():
    teds = make_teds()
    add_full_record(teds, episode=episode_values(employment_status="96"))
    add_full_record(teds, client=client_values(source_id="90000002", dob="01012012"), episode=episode_values(employment_status="01", admit_date="04082024"))
    issues = teds.predict_errors()
    assert errors(issues, "EmploymentStatus")[0]["client_source_id"] == "80000001"
    assert warnings(issues, "EmploymentStatus")[0]["client_source_id"] == "90000002"
    assert warnings(issues, "PrimaryAgeOfFirstUse")[0]["source"] == "KDADS KSURS-era edit"


def test_substance_rules():
    teds = make_teds()
    substances = [
        dict(rank="P", substance="01", detailed_drug_code="9996", route="01", frequency="96", age_first_use="96", discharge_substance="01", discharge_frequency="05")
        ,dict(rank="S", substance="02", detailed_drug_code="0401", route="96", frequency="05", age_first_use="")
        ,dict(rank="T", substance="", route="01")
    ]
    add_full_record(teds, substances=substances)
    issues = teds.predict_errors()
    assert errors(issues, "PrimaryRouteOfAdministration")[0]["error"] == "Value not applicable unless Substance is None (01)"
    assert errors(issues, "PrimaryFrequency")[0]["record_type"] == "Discharge"
    assert errors(issues, "SecondaryRouteOfAdministration")
    assert errors(issues, "SecondaryDetailedDrugCode")[0]["error"] == "Value not applicable to selected Substance"
    assert errors(issues, "SecondaryAgeOfFirstUse")[0]["error"] == "Required field not populated"
    assert errors(issues, "TertiarySubstance")


def test_substance_codes_and_discharge_pairs():
    teds = make_teds()
    substances = [
        dict(rank="P", substance="99", detailed_drug_code="0201", route="01", frequency="05", age_first_use="15", discharge_substance="02", discharge_frequency="09")
        ,dict(rank="S", substance="04", detailed_drug_code="0401", route="02", frequency="03", age_first_use="16", discharge_substance="04")
        ,dict(rank="T", substance="05", detailed_drug_code="0501", route="02", frequency="03", age_first_use="16", discharge_frequency="01")
    ]
    add_full_record(teds, substances=substances)
    issues = teds.predict_errors()
    assert errors(issues, "PrimarySubstance")[0]["value"] == "99"
    assert errors(issues, "PrimaryFrequency")[0]["record_type"] == "Discharge"
    assert errors(issues, "SecondaryFrequency")[0]["message"].startswith("Required at discharge when SecondarySubstance")
    assert errors(issues, "TertiarySubstance")[0]["record_type"] == "Discharge"


def test_duplicate_substances():
    teds = make_teds()
    same = dict(substance="02", detailed_drug_code="0201", route="01", frequency="05", age_first_use="15", discharge_substance="02", discharge_frequency="01")
    unknown = dict(substance="97", detailed_drug_code="9997", route="97", frequency="97", age_first_use="97")
    add_full_record(teds, substances=[dict(rank="P", **same), dict(rank="S", **same), dict(rank="T", **unknown)])
    add_full_record(teds, client=client_values(source_id="90000002"), substances=[dict(rank="P", **same), dict(rank="S", **unknown), dict(rank="T", **unknown)])
    issues = teds.predict_errors()
    duplicate = "Duplicate Substance Codes not allowed unless Detailed Drug Codes are different"
    assert [i["client_source_id"] for i in errors(issues) if(i["error"] == duplicate)] == ["80000001"]
    found = {(i["client_source_id"], i["element"], i["record_type"]) for i in warnings(issues) if(i["error"] == duplicate)}
    assert ("80000001", "SecondarySubstance", "Discharge") in found and ("90000002", "TertiarySubstance", "Admission") in found


def test_bad_rank_and_repeated_rank():
    teds = make_teds()
    substances = substance_values() + [dict(rank="Q", substance="02"), dict(rank="Primary", substance="02", detailed_drug_code="0201", route="01", frequency="05", age_first_use="15")]
    add_full_record(teds, substances=substances)
    messages = [i["message"] for i in errors(teds.predict_errors(), "Substance")]
    assert any("Rank 'Q'" in m for m in messages) and any("ranked P" in m for m in messages)
    assert not Substance(rank="Q").validate() and Substance(**substance_values()[0]).validate()


def test_date_checks():
    teds = make_teds()
    add_full_record(teds, discharge=discharge_values(discharge_date="01012024", last_contact_date="01202024"))
    add_full_record(teds, client=client_values(source_id="90000002"), episode=episode_values(admit_date="12012026"), discharge=discharge_values(discharge_date="12152026", last_contact_date="11012026"))
    add_full_record(teds, client=client_values(source_id="90000003", dob="02072025"), discharge=discharge_values(last_contact_date="01011999"))
    add_full_record(teds, client=client_values(source_id="90000004", dob="01012030"))
    issues = teds.predict_errors()
    assert errors(issues, "DateOFDischarge")[0]["client_source_id"] == "80000001"
    found = {(i["client_source_id"], i["element"]) for i in warnings(issues)}
    assert ("80000001", "DateOfLastContact") in found
    assert ("90000002", "DateOfAdmission") in found and ("90000002", "DateOFDischarge") in found and ("90000002", "DateOfLastContact") in found
    assert ("90000003", "DateOfLastContact") in found
    assert {i["client_source_id"] for i in errors(issues, "DateOfAdmission")} == {"90000003", "90000004"}
    assert errors(issues, "DOB")[0]["client_source_id"] == "90000004"


def test_missing_leading_zeros_are_errors():
    teds = make_teds()
    add_full_record(teds, episode=episode_values(arrests="3", days_waiting="42", people_in_household="11", yearly_income="12k", diagnosis="F1"))
    issues = teds.predict_errors()
    assert errors(issues, "ArrestsInPast30Days")[0]["source"] == "WellSky provider instructions"
    assert "'042'" in errors(issues, "DaysWaiting")[0]["message"]
    assert errors(issues, "PeopleInHousehold") and errors(issues, "YearlyIncome")
    assert errors(issues, "SUDiagnosis")[0]["error"] == "Not a valid ICD-10 Diagnosis Code"


def test_every_format_check():
    rules = WellSkyRules()
    check = rules.check_value
    assert check(rules.field("Client", "DOB"), "02302024")[0] == "invalid-format"
    assert check(rules.field("TreatmentEvent", "TypeOfTobacco"), "01|04")[0] == "invalid-value"
    assert check(rules.field("TreatmentEvent", "TypeOfTobacco"), "01|02") is None
    assert check(rules.field("TreatmentEvent", "PrimaryDetailedDrugCode"), "0299")[0] == "invalid-value"
    assert check(rules.field("TreatmentEvent", "ArrestsInPast30Days"), "x")[0] == "invalid-format"
    assert check(rules.field("Client", "Phone"), "555-1234")[0] == "invalid-format"
    assert check(rules.field("Client", "Phone"), "5551234")[0] == "invalid-format"
    assert check(rules.field("Client", "SSN"), "123456789")[0] == "invalid-format"
    assert check(rules.field("Client", "State"), "Kanzas")[0] == "invalid-value"
    assert check(rules.field("Client", "CountyofResidence"), "Cook")[0] == "invalid-value"
    assert check(rules.field("TreatmentEvent", "SUDiagnosis"), "999.9997") is None
    assert rules.age_on("bad", "01012024") is None
    assert rules.age_on("06152000", "06142024") == 23


def test_unattached_episode_and_lonely_client():
    episode = Episode(**episode_values())
    assert errors(episode.predict_errors(), "Client")
    assert not episode.validate()
    teds = make_teds()
    teds.add_client(Client(**client_values()))
    assert warnings(teds.predict_errors(), "Client")
    assert Client(**client_values()).validate()


def test_file_level_checks():
    teds = make_teds()
    add_full_record(teds)
    add_full_record(teds)
    add_full_record(teds, client=client_values(first_name="Other"))
    add_full_record(teds, client=client_values(source_id="90000005"), episode=episode_values(license="KDADS-1", event_source_id="SHARED"))
    add_full_record(teds, client=client_values(source_id="90000006"), episode=episode_values(license="KDADS-1", event_source_id="SHARED", admit_date="01162024"))
    issues = teds.predict_errors()
    assert any(i["element"] == "SourceID" and i["record_type"] == "Episode" and i["severity"] == "Error" for i in issues)
    assert any(i["element"] == "SourceID" and i["record_type"] == "Client" for i in warnings(issues))
    assert any(i["value"] == "SHARED" for i in warnings(issues, "SourceID"))
    assert errors(issues, "ProviderID")[0]["value"] == "KDADS-1"
    # Three Client objects share SourceID 80000001 under one license, so the client is split across elements.
    split = [i for i in warnings(issues, "Client") if(i["client_source_id"] == "80000001")]
    assert "split across 3" in split[0]["message"]


# ----------------------------------------------------------------------
# Reading files back in
# ----------------------------------------------------------------------
def test_read_back_matches_what_was_written(tmp_path):
    teds = make_teds(tmp_path)
    add_full_record(teds)
    teds.execute()
    written = tmp_path / "KDADS_00987654_202609140815.xml"
    assert written.is_file() and (tmp_path / "wellsky_predicted_errors.csv").is_file()
    checker = make_teds(tmp_path, dry_run=True)
    assert checker.execute()["errors"] == 0
    rebuilt = checker.build_xml([e for c in checker.read_clients for e in c.episodes])
    assert rebuilt == written.read_text(encoding="utf-8")


def test_reading_flags_a_wrong_transaction_type_and_a_lone_discharge(tmp_path):
    teds = make_teds()
    add_full_record(teds)
    text = teds.build_files()["KDADS_00987654_202609140815.xml"]
    root = ET.fromstring(text.encode())
    client = root.find("Client")
    client.find("Admission/ClientTransactionType").text = "D"
    lone = ET.SubElement(root, "Client")
    for child in client:
        if(child.tag == "Discharge"):
            lone.append(child)
        elif(child.tag != "Admission"):
            ET.SubElement(lone, child.tag).text = child.text
    (tmp_path / "check.xml").write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    checker = make_teds(tmp_path, dry_run=True)
    checker.execute()
    assert errors(checker.issues, "ClientTransactionType")[0]["value"] == "D"
    assert warnings(checker.issues, "Admission")[0]["error"] == "No Admission matching this Discharge found"


def test_reading_a_file_that_leaves_elements_out(tmp_path):
    teds = make_teds()
    add_full_record(teds, client=client_values(sex="2"), episode=episode_values(pregnant="2"))
    root = ET.fromstring(teds.build_files()["KDADS_00987654_202609140815.xml"].encode())
    # Drop elements outright, rather than leaving them as empty tags.
    for parent_path, tag in (("Client", "CountyofResidence"), ("Client/Admission/TreatmentEvent", "NotInLaborForce"), ("Client/Admission/TreatmentEvent", "PregnantAtAdmission"), ("Client/Discharge/TreatmentEvent", "NotInLaborForce"), ("Client/Discharge/TreatmentEvent", "EmploymentStatus"), ("Client/Discharge", "ReasonForDischarge")):
        parent = root.find(parent_path)
        parent.remove(parent.find(tag))
    (tmp_path / "sparse.xml").write_text(ET.tostring(root, encoding="unicode"), encoding="utf-8")
    checker = make_teds(tmp_path, dry_run=True)
    assert checker.execute() is not None
    found = {(i["element"], i["record_type"]) for i in errors(checker.issues) if(i["error"] == "Required field not populated")}
    assert {("CountyofResidence", "Client"), ("PregnantAtAdmission", "Admission"), ("EmploymentStatus", "Discharge"), ("ReasonForDischarge", "Discharge")} <= found


@pytest.mark.skipif(not SAMPLE.is_file(), reason="No sample WellSky export available.")
def test_the_sample_export_reads_and_rebuilds_exactly(tmp_path):
    shutil.copy(SAMPLE, tmp_path / "sample.xml")
    checker = make_teds(tmp_path, dry_run=True)
    checker.execute()
    rebuilt = ET.fromstring(checker.build_xml([e for c in checker.read_clients for e in c.episodes]).encode())
    original = ET.parse(SAMPLE).getroot()
    pairs = lambda e: [(c.tag, (c.text or "").strip()) for c in e.iter() if(c.tag != "ReportingDate")]
    assert pairs(original) == pairs(rebuilt)
    assert errors(checker.issues, "ReasonForDischarge")[0]["value"] == "97"


def test_a_made_up_record_has_the_sample_exports_element_order():
    if(not SAMPLE.is_file()):
        pytest.skip("No sample WellSky export available.")
    teds = make_teds()
    add_full_record(teds)
    built = ET.fromstring(teds.build_files()["KDADS_00987654_202609140815.xml"].encode()).find("Client")
    sample_client = [c for c in ET.parse(SAMPLE).getroot().findall("Client") if(c.find("Discharge") is not None)][0]
    assert [c.tag for c in built.iter()] == [c.tag for c in sample_client.iter()]


# ----------------------------------------------------------------------
# Running
# ----------------------------------------------------------------------
def test_validate_failures(tmp_path):
    nowhere = make_teds()
    add_full_record(nowhere)
    assert not nowhere.validate()
    assert nowhere.execute() is None
    a_file = tmp_path / "not_a_folder.txt"
    a_file.write_text("x", encoding="utf-8")
    assert not make_teds(a_file).validate()
    # Nothing added in code, and no .xml files to check.
    assert not make_teds(tmp_path).validate()
    assert not make_teds(tmp_path / "missing").validate()


def test_a_missing_folder_is_created(tmp_path):
    folder = tmp_path / "new" / "out"
    teds = make_teds(folder)
    add_full_record(teds)
    assert teds.validate()
    teds.execute()
    assert sorted(p.name for p in folder.iterdir()) == ["KDADS_00987654_202609140815.xml", "wellsky_predicted_errors.csv"]


def test_dry_run_writes_nothing(tmp_path):
    teds = make_teds(tmp_path / "out", dry_run=True)
    add_full_record(teds)
    summary = teds.execute()
    assert summary["files"] == ["KDADS_00987654_202609140815.xml"] and summary["clients"] == 1
    assert list(tmp_path.iterdir()) == []


def test_report_columns(tmp_path):
    teds = make_teds(tmp_path)
    add_full_record(teds, client=client_values(county=""))
    summary = teds.execute()
    lines = (tmp_path / "wellsky_predicted_errors.csv").read_text(encoding="utf-8").splitlines()
    assert lines[0] == "Severity,Error,Element,Value,Message,Source,Record Type,License,Client Source ID,Episode Source ID"
    assert lines[1].startswith("Error,Required field not populated,CountyofResidence")
    assert summary["by_error"] == {"Error: Required field not populated": 1}


def test_console_monitor_prints(capsys):
    monitor = ConsoleMonitor()
    monitor.add_log(log_system="A", log_category="B", log_subcategory="C", log_line="D")
    assert capsys.readouterr().out.strip() == "A | B | C | D"
    assert WellSkyPredictor().rules.slots["P"] == "Primary"


def test_command_line(tmp_path, monkeypatch, capsys):
    teds = make_teds(tmp_path)
    add_full_record(teds)
    teds.execute()
    xml_file = tmp_path / "KDADS_00987654_202609140815.xml"
    before = xml_file.read_text(encoding="utf-8")
    (tmp_path / "wellsky_predicted_errors.csv").unlink()
    monkeypatch.setattr(sys, "argv", ["WellSkyTEDS.py", "--path", str(tmp_path)])
    main()
    # The report is written into the same folder, and the checked file is left as it was.
    assert (tmp_path / "wellsky_predicted_errors.csv").is_file()
    assert xml_file.read_text(encoding="utf-8") == before
    monkeypatch.setattr(sys, "argv", ["WellSkyTEDS.py", "--path", str(tmp_path / "missing")])
    main()
    assert "usage:" in capsys.readouterr().out
    assert main(get_args=True).parse_args(["--path", "x"]).dry_run is False
