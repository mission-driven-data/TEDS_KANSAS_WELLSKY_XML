"""
==================================================================
~~~~~~~~~~~~~~~~~~~~~~~
WellSkyTEDS.py
~~~~~~~~~~~~~~~~~~~~~~~
==================================================================
Builds WellSky Custom TEDS Import XML for Kansas (KDADS) and predicts the
errors WellSky is likely to return. The rules come from the WellSky SUD Custom
TEDS Import Layout v13 (03/10/2026). The XML is shaped like a working WellSky
export.

This file knows nothing about where the data comes from. The caller reads its
own source and passes WellSky values in; this file builds, checks and writes.
A caller builds records from three objects and hands them to WellSkyTEDS:

- Client: one person, written as <Client>.
- Episode: one admission, and its discharge when there is one, written as
  <Admission> and <Discharge>, each with its <TreatmentEvent>. The episode
  carries the provider license number, which WellSky uses as ProviderID and
  in the file name.
- Substance: one ranked substance (Primary, Secondary or Tertiary) on an
  episode, with its admission values and its discharge values.

Records can be built one object at a time (Client, Episode, Substance, then
attach them), or a whole client at once with WellSkyTEDS.add_record() from
plain dicts. Both produce the same objects and the same XML.

Classes in this file:

- WellSkyRules: the layout's field table, code lists, Detailed Drug Code Map,
  US states and Kansas counties, and the checks on single values.
- Substance, Client, Episode: hold values. predict_errors() lists the
  object's own predicted errors; validate() is True when none is an Error.
- WellSkyPredictor: runs every object's checks plus the file-level checks
  (repeated IDs, conflicting client details, license format), summarizes
  them and writes the predicted error report (CSV).
- WellSkyTEDS: collects clients, writes one KDADS_[license]_yyyyMMddHHmm.xml
  per license, reads existing WellSky XML back in, and from the command line
  checks the XML files in a folder.

It needs Python 3.9 or later and nothing else. The XML and the report hold
client information, so write them only to a location approved for PHI.

Created by Mission Driven Data (https://missiondrivendata.com).
Copyright (c) 2026 Mission Driven Data. Released under the MIT License; see LICENSE.
Not affiliated with or endorsed by WellSky, KDADS or SAMHSA. Provided as is, without
warranty; see the Disclaimer in README.md.
=======
"""

from pathlib import Path
import argparse
import csv
import datetime
import re
import textwrap
import xml.etree.ElementTree as ET


class ConsoleMonitor:
    def __init__(self
                 ,verbose=True):
        """
        A small stand-in for JCT's Monitor, so this file runs without MDD libraries.
        Any object with the same add_log signature and a verbose attribute can be injected instead.

        :param verbose: When True, print each log line. Always True unless a caller turns it off.
        """
        self.verbose = verbose
        self.lines = []

    def add_log(self
                ,log_system
                ,log_category
                ,log_subcategory
                ,log_line):
        """
        Records one log line and prints it when verbose.

        :param log_system: The class producing the event.
        :param log_category: The method, in Title Case.
        :param log_subcategory: The subject inside the method.
        :param log_line: The detail. Never include client information.
        """
        line = f"{log_system} | {log_category} | {log_subcategory} | {log_line}"
        self.lines.append(line)
        if(self.verbose):
            print(line)


class WellSkyRules:
    def __init__(self):
        """
        The WellSky SUD Custom TEDS Import Layout v13 (03/10/2026) as data, plus the checks on single values.
        """
        # Class Data
        # Where a rule comes from. The report shows it in the Source column.
        self.source_layout = "WellSky layout v13"
        self.source_instructions = "WellSky provider instructions"
        self.source_reading = "MDD reading of layout v13"
        self.source_integrity = "Data integrity"
        self.source_kdads = "KDADS KSURS-era edit"
        # WellSky's own error wording (the interface's error list), so the report reads like WellSky's response.
        # The last two are this file's own: problems WellSky's list doesn't name.
        self.errors = {
            "required": "Required field not populated"
            ,"invalid-value": "Invalid value"
            ,"invalid-format": "Invalid format"
            ,"icd10": "Not a valid ICD-10 Diagnosis Code"
            ,"collateral-only": "Value not applicable unless Client Type = Codependent/Collateral (1)"
            ,"none-substance": "Value not applicable unless Substance is None (01)"
            ,"drug-substance": "Value not applicable to selected Substance"
            ,"duplicate-substance": "Duplicate Substance Codes not allowed unless Detailed Drug Codes are different"
            ,"no-admission": "No Admission matching this Discharge found"
            ,"provider-id": "Provider ID not found"
            ,"integrity": "Data integrity"
            ,"kdads": "Likely KDADS edit"
        }
        # The WellSky layout v13 as a table: one row per WellSky XML element, describing what WellSky accepts.
        # This is the specification the checks and the XML writer use. It describes no input file; callers
        # pass their values in through Client, Episode and Substance.
        # Columns: the XML tag, the element it sits under, its format, the width WellSky pads it to, its
        # maximum length, its requirement on an admission and on a discharge, whether it is required for
        # a collateral client, the allowed codes, and the allowed numeric range.
        # Requirement flags: Y required, C conditionally required, O optional, N not sent on that record type.
        # Record means the <Admission> or <Discharge> element itself. Rows are in the layout's element order.
        self.field_keys = ("xml_tag", "parent", "format", "pad_width", "max_length", "admission", "discharge", "required_if_collateral", "codes", "range")
        rows = [
            ('StateCode', 'File', 'code', None, 2, 'Y', 'Y', True, 'KS', None)
            ,('ReportingDate', 'File', 'date', None, 8, 'Y', 'Y', True, '', None)
            ,('SourceID', 'Client', 'text', None, 50, 'Y', 'Y', True, '', None)
            ,('LastName', 'Client', 'text', None, 30, 'Y', 'Y', True, '', None)
            ,('FirstName', 'Client', 'text', None, 30, 'Y', 'Y', True, '', None)
            ,('MiddleName', 'Client', 'text', None, 30, 'O', 'O', False, '', None)
            ,('AKA', 'Client', 'text', None, 100, 'O', 'O', False, '', None)
            ,('DOB', 'Client', 'date', None, 8, 'Y', 'Y', True, '', None)
            ,('Sex', 'Client', 'code', 1, 1, 'Y', 'Y', True, '1 2 7', None)
            ,('Race', 'Client', 'code', 2, 2, 'Y', 'Y', False, '01 02 04 05 13 20 21 23 97', None)
            ,('HispanicOrigin', 'Client', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 05 06 97', None)
            ,('GenderIdentity', 'Client', 'code', 1, 1, 'Y', 'Y', False, '1 2 3 4 7 8', None)
            ,('SexualOrientation', 'Client', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 05 06 07 09 98', None)
            ,('Phone', 'Client', 'digits', None, 10, 'O', 'O', False, '', None)
            ,('Street', 'Client', 'text', None, 100, 'O', 'O', False, '', None)
            ,('State', 'Client', 'state', None, 20, 'O', 'O', False, '', None)
            ,('CountyofResidence', 'Client', 'county', None, 100, 'Y', 'Y', True, '', None)
            ,('DepartmentOfCorrectionsNum', 'Client', 'text', None, 100, 'O', 'O', False, '', None)
            ,('MedicaidNumber', 'Client', 'text', None, 100, 'O', 'O', False, '', None)
            ,('SSN', 'Client', 'ssn', None, 11, 'O', 'O', False, '', None)
            ,('ASO', 'Client', 'text', None, 100, 'O', 'O', False, '', None)
            ,('ProviderID', 'Record', 'text', None, 50, 'Y', 'Y', True, '', None)
            ,('SourceID', 'Record', 'text', None, 100, 'Y', 'Y', False, '', None)
            ,('EnrollType', 'Record', 'code', None, 10, 'Y', 'Y', False, 'Inpatient Outpatient', None)
            ,('DateOfAdmission', 'Record', 'date', None, 8, 'Y', 'Y', True, '', None)
            ,('ClientTransactionType', 'Record', 'code', None, 1, 'Y', 'Y', True, 'A T D', None)
            ,('ClientType', 'Record', 'code', 1, 1, 'Y', 'Y', True, '1 2', None)
            ,('ReferralSource', 'Record', 'code', 2, 2, 'Y', 'N', False, '01 02 03 04 05 06 07 97', None)
            ,('CriminalJusticeReferral', 'Record', 'code', 2, 2, 'C', 'N', False, '01 02 03 04 05 06 07 08 96 97', None)
            ,('TreatmentSetting', 'Record', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 05 06 07 08 96', None)
            ,('DateOfLastContact', 'Record', 'date', None, 8, 'N', 'Y', False, '', None)
            ,('DateOFDischarge', 'Record', 'date', None, 8, 'N', 'Y', True, '', None)
            ,('ReasonForDischarge', 'Record', 'code', 2, 2, 'N', 'Y', False, '01 02 03 04 05 06 07 14 24', None)
            ,('SourceID', 'TreatmentEvent', 'text', None, 100, 'Y', 'Y', False, '', None)
            ,('HighestLevelOfEducation', 'TreatmentEvent', 'code', 2, 2, 'Y', 'N', False, '00 01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 19 70 71 97', None)
            ,('EmploymentStatus', 'TreatmentEvent', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 96 97', None)
            ,('NotInLaborForce', 'TreatmentEvent', 'code', 2, 2, 'C', 'C', False, '01 02 03 04 05 06 96 97', None)
            ,('PregnantAtAdmission', 'TreatmentEvent', 'code', 1, 1, 'C', 'N', False, '1 2 6 7', None)
            ,('PrenatalCare', 'TreatmentEvent', 'code', 1, 1, 'O', 'N', False, '1 2', None)
            ,('VeteranStatus', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2 7', None)
            ,('LivingArrangement', 'TreatmentEvent', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 97', None)
            ,('YearlyIncome', 'TreatmentEvent', 'digits', None, 10, 'Y', 'N', False, '', None)
            ,('FederalPovertyLevel', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2 6', None)
            ,('PeopleInHousehold', 'TreatmentEvent', 'range', None, 2, 'Y', 'N', False, '', (1, 10, ()))
            ,('ChildrenInHome', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('ChildrenInHomeAtRisk', 'TreatmentEvent', 'code', 2, 2, 'Y', 'N', False, '00 01 02 03 04 05 06 07 08 09 10', None)
            ,('DCFCustody', 'TreatmentEvent', 'code', 1, 1, 'O', 'N', False, '1 2 9', None)
            ,('SourcesOfIncome', 'TreatmentEvent', 'code', 2, 2, 'Y', 'N', False, '01 02 03 04 20 21 97', None)
            ,('HealthInsurance', 'TreatmentEvent', 'code', 2, 2, 'O', 'N', False, '01 02 03 04 06 20 21 97', None)
            ,('PrimaryPaymentSource', 'TreatmentEvent', 'code', 2, 2, 'Y', 'N', False, '01 02 03 04 05 06 07 08 09 97', None)
            ,('SenateBill6Secondary', 'TreatmentEvent', 'code', 1, 1, 'O', 'N', False, '0 1', None)
            ,('GamblingFundMemberType', 'TreatmentEvent', 'code', 2, 2, 'O', 'N', False, '01 02 03', None)
            ,('GPRA', 'TreatmentEvent', 'code', 1, 1, 'O', 'N', False, '0 1', None)
            ,('MaritalStatus', 'TreatmentEvent', 'code', 2, 2, 'O', 'N', False, '01 02 03 04 05 97', None)
            ,('DaysWaiting', 'TreatmentEvent', 'range', 3, 3, 'O', 'N', False, '', (0, 995, ('997',)))
            ,('ArrestsInPast30Days', 'TreatmentEvent', 'range', 2, 2, 'Y', 'Y', False, '', (0, 96, ('97',)))
            ,('SelfHelpGroupInPast30Days', 'TreatmentEvent', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 05 06 97', None)
            ,('GamblingWithdrawal', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('GamblingHidden', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('GamblingFinancialTrouble', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('TobaccoUse', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('TypeOfTobacco', 'TreatmentEvent', 'pipe', 2, 8, 'C', 'N', False, '01 02 03', None)
            ,('Tobacco30', 'TreatmentEvent', 'code', 1, 1, 'C', 'N', False, '1 2', None)
            ,('TBPositive', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('TBRisk', 'TreatmentEvent', 'code', 1, 1, 'C', 'N', False, '1 2', None)
            ,('TBSymptoms', 'TreatmentEvent', 'code', 1, 1, 'C', 'N', False, '1 2', None)
            ,('TBEducation', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('TBCaseMgm', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('HIV', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2 9', None)
            ,('MHTx', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('Co-OccurringMHSU', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2 7', None)
            ,('PsyMed', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('SUHistory', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('MHHistory', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('PrevSUDTx', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2', None)
            ,('PrevSUDTxEp', 'TreatmentEvent', 'code', 1, 1, 'C', 'N', False, '0 1 2 3 4 5 7', None)
            ,('MHTxEp', 'TreatmentEvent', 'code', 2, 2, 'C', 'N', False, '00 01 02 03 04 05 06 07 08 09 10', None)
            ,('MOUD', 'TreatmentEvent', 'code', 1, 1, 'Y', 'N', False, '1 2 6 7', None)
            ,('PrimarySubstance', 'TreatmentEvent', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 20 97', None)
            ,('PrimaryDetailedDrugCode', 'TreatmentEvent', 'drug', 4, 4, 'Y', 'N', False, '', None)
            ,('PrimaryRouteOfAdministration', 'TreatmentEvent', 'code', 2, 2, 'Y', 'N', False, '01 02 03 04 20 96 97', None)
            ,('PrimaryFrequency', 'TreatmentEvent', 'code', 2, 2, 'Y', 'Y', False, '01 02 03 04 05 96 97', None)
            ,('PrimaryAgeOfFirstUse', 'TreatmentEvent', 'range', 2, 2, 'Y', 'N', False, '', (0, 95, ('96', '97')))
            ,('SecondarySubstance', 'TreatmentEvent', 'code', 2, 2, 'O', 'O', False, '01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 20 97', None)
            ,('SecondaryDetailedDrugCode', 'TreatmentEvent', 'drug', 4, 4, 'C', 'N', False, '', None)
            ,('SecondaryRouteOfAdministration', 'TreatmentEvent', 'code', 2, 2, 'C', 'N', False, '01 02 03 04 20 96 97', None)
            ,('SecondaryFrequency', 'TreatmentEvent', 'code', 2, 2, 'C', 'C', False, '01 02 03 04 05 96 97', None)
            ,('SecondaryAgeOfFirstUse', 'TreatmentEvent', 'range', 2, 2, 'C', 'N', False, '', (0, 95, ('96', '97')))
            ,('TertiarySubstance', 'TreatmentEvent', 'code', 2, 2, 'O', 'O', False, '01 02 03 04 05 06 07 08 09 10 11 12 13 14 15 16 17 18 20 97', None)
            ,('TertiaryDetailedDrugCode', 'TreatmentEvent', 'drug', 4, 4, 'C', 'N', False, '', None)
            ,('TertiaryRouteOfAdministration', 'TreatmentEvent', 'code', 2, 2, 'C', 'N', False, '01 02 03 04 20 96 97', None)
            ,('TertiaryFrequency', 'TreatmentEvent', 'code', 2, 2, 'C', 'C', False, '01 02 03 04 05 96 97', None)
            ,('TertiaryAgeOfFirstUse', 'TreatmentEvent', 'range', 2, 2, 'C', 'N', False, '', (0, 95, ('96', '97')))
            ,('SUDiagnosis', 'TreatmentEvent', 'icd10', None, 10, 'Y', 'N', False, '', None)
        ]
        self.fields = [dict(zip(self.field_keys, row)) for row in rows]
        for field in self.fields:
            field["codes"] = field["codes"].split()
        self.fields_by_key = {(f["parent"], f["xml_tag"]): f for f in self.fields}
        self.slots = {"P": "Primary", "S": "Secondary", "T": "Tertiary"}
        self.substance_parts = ("Substance", "DetailedDrugCode", "RouteOfAdministration", "Frequency", "AgeOfFirstUse")
        self.discharge_parts = ("Substance", "Frequency")
        self.substance_tags = {f"{slot}{part}" for slot in self.slots.values() for part in self.substance_parts}
        # The layout's Detailed Drug Code Map: detailed code to its substance.
        self.drug_parents = {
            "9996": "01", "0201": "02", "0301": "03", "0302": "03", "0401": "04", "0501": "05", "0601": "06", "0701": "07"
            ,"0702": "07", "0703": "07", "0704": "07", "0705": "07", "0706": "07", "0707": "07", "0708": "07", "0709": "07"
            ,"0710": "07", "0711": "07", "0801": "08", "0901": "09", "0902": "09", "1001": "10", "1101": "11", "1103": "11"
            ,"1109": "11", "1201": "12", "1202": "12", "1301": "13", "1302": "13", "1303": "13", "1304": "13", "1305": "13"
            ,"1306": "13", "1307": "13", "1308": "13", "1309": "13", "1310": "13", "1401": "14", "1403": "14", "1501": "15"
            ,"1502": "15", "1503": "15", "1509": "15", "1601": "16", "1602": "16", "1603": "16", "1604": "16", "1605": "16"
            ,"1701": "17", "1702": "17", "1703": "17", "1704": "17", "1705": "17", "1801": "18", "1809": "18", "2001": "20"
            ,"2002": "20", "2003": "20", "2004": "20", "9997": "97"
        }
        # Names are compared without regard to case: a working WellSky export sends State as KANSAS.
        self.state_names = {name.upper() for name in (
            "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "District of Columbia"
            ,"Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine"
            ,"Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada"
            ,"New Hampshire", "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon"
            ,"Pennsylvania", "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia"
            ,"Washington", "West Virginia", "Wisconsin", "Wyoming"
        )}
        self.counties = {name.upper() for name in (
            "Allen", "Anderson", "Atchison", "Barber", "Barton", "Bourbon", "Brown", "Butler", "Chase", "Chautauqua", "Cherokee"
            ,"Cheyenne", "Clark", "Clay", "Cloud", "Coffey", "Comanche", "Cowley", "Crawford", "Decatur", "Dickinson", "Doniphan"
            ,"Douglas", "Edwards", "Elk", "Ellis", "Ellsworth", "Finney", "Ford", "Franklin", "Geary", "Gove", "Graham", "Grant"
            ,"Gray", "Greeley", "Greenwood", "Hamilton", "Harper", "Harvey", "Haskell", "Hodgeman", "Jackson", "Jefferson", "Jewell"
            ,"Johnson", "Kearny", "Kingman", "Kiowa", "Labette", "Lane", "Leavenworth", "Lincoln", "Linn", "Logan", "Lyon", "Marion"
            ,"Marshall", "McPherson", "Meade", "Miami", "Mitchell", "Montgomery", "Morris", "Morton", "Nemaha", "Neosho", "Ness"
            ,"Norton", "Osage", "Osborne", "Ottawa", "Pawnee", "Phillips", "Pottawatomie", "Pratt", "Rawlins", "Reno", "Republic"
            ,"Rice", "Riley", "Rooks", "Rush", "Russell", "Saline", "Scott", "Sedgwick", "Seward", "Shawnee", "Sheridan", "Sherman"
            ,"Smith", "Stafford", "Stanton", "Stevens", "Sumner", "Thomas", "Trego", "Wabaunsee", "Wallace", "Washington", "Wichita"
            ,"Wilson", "Woodson", "Wyandotte"
        )}
        # The report leaves these values out: they identify the person.
        self.sensitive_tags = {"LastName", "FirstName", "MiddleName", "AKA", "DOB", "Phone", "Street", "SSN", "MedicaidNumber", "DepartmentOfCorrectionsNum", "ASO"}
        self.inpatient_settings = ("01", "02", "03", "04", "05")
        self.earliest_contact = datetime.date(2000, 1, 1)

    def text(self, value):
        """
        A value as the text WellSky receives: '' for None, MMDDYYYY for dates, otherwise the trimmed string.
        Nothing else is changed: codes are sent exactly as given.

        :param value: Any value a caller passes in.
        """
        if(value is None):
            return ""
        if(isinstance(value, (datetime.date, datetime.datetime))):
            return value.strftime("%m%d%Y")
        return str(value).strip()

    def license_text(self, value):
        """
        A provider license exactly as given, trimmed. It names the file, and WellSky's provider
        instructions allow no characters beyond the license itself, so nothing is added or padded.

        :param value: The license number, as KDADS issued it (with any leading zeros).
        """
        return self.text(value)

    def as_date(self, text):
        """
        An MMDDYYYY string as a date, or None when it is blank or not a real date.

        :param text: MMDDYYYY text.
        """
        if(not re.fullmatch(r"\d{8}", text or "")):
            return None
        try:
            return datetime.datetime.strptime(text, "%m%d%Y").date()
        except ValueError:
            return None

    def age_on(self, dob, on):
        """
        Whole years between two MMDDYYYY dates, or None when either isn't a real date.

        :param dob: Date of birth, MMDDYYYY.
        :param on: The date to measure to, MMDDYYYY.
        """
        born, then = self.as_date(dob), self.as_date(on)
        if(born is None or then is None):
            return None
        return then.year - born.year - ((then.month, then.day) < (born.month, born.day))

    def field(self, parent, tag):
        """
        One element's rule.

        :param parent: 'File', 'Client', 'Record' or 'TreatmentEvent'.
        :param tag: The XML tag.
        """
        return self.fields_by_key[(parent, tag)]

    def flag(self, field, record_type):
        """
        The element's requirement flag (Y, C, O or N) on one record type.

        :param field: Field rule dict.
        :param record_type: 'Client', 'Admission' or 'Discharge'.
        """
        return field["discharge"] if(record_type == "Discharge") else field["admission"]

    def sent_fields(self, parent, record_type):
        """
        The elements written under one parent on one record type, in layout order.

        :param parent: 'Client', 'Record' or 'TreatmentEvent'.
        :param record_type: 'Client', 'Admission' or 'Discharge'.
        """
        return [f for f in self.fields if(f["parent"] == parent and self.flag(f, record_type) != "N")]

    def issue(self, context, element, error, message, severity="Error", source=None, value=""):
        """
        One predicted error as a report row.

        :param context: Dict with record_type, license, client_source_id and episode_source_id.
        :param element: The XML tag (or 'Client', 'Episode', 'Substance', 'File').
        :param error: Key into self.errors.
        :param message: What is wrong, in plain words.
        :param severity: 'Error' (WellSky's rules say it will be rejected) or 'Warning' (it may be).
        :param source: Where the rule comes from. Defaults to the layout.
        :param value: The value sent; left out for elements that identify the person.
        """
        return {
            "severity": severity
            ,"error": self.errors[error]
            ,"element": element
            ,"value": "" if(element in self.sensitive_tags) else value
            ,"message": message
            ,"source": source or self.source_layout
            ,"record_type": context["record_type"]
            ,"license": context["license"]
            ,"client_source_id": context["client_source_id"]
            ,"episode_source_id": context["episode_source_id"]
        }

    def check_value(self, field, value):
        """
        Checks one non-blank value against its element's rule.

        :param field: Field rule dict.
        :param value: The text sent.
        :return: Tuple of (error key, message, severity, source), or None when the value passes.
        """
        fmt = field["format"]
        if(field["max_length"] and fmt != "date" and len(value) > field["max_length"]):
            return ("invalid-format", f"Longer than {field['max_length']} characters.", "Error", self.source_layout)
        if(fmt == "date"):
            if(self.as_date(value) is None):
                return ("invalid-format", "Dates must be real dates written MMDDYYYY.", "Error", self.source_layout)
        elif(fmt == "code"):
            if(value not in field["codes"]):
                hint = f" Did you mean '{value.zfill(field['pad_width'])}'?" if(field["pad_width"] and value.zfill(field["pad_width"]) in field["codes"]) else ""
                return ("invalid-value", f"'{value}' is not one of WellSky's codes ({', '.join(field['codes'])}).{hint}", "Error", self.source_layout)
        elif(fmt == "pipe"):
            if(any(part not in field["codes"] for part in value.split("|"))):
                return ("invalid-value", f"Each part must be one of {', '.join(field['codes'])}, separated by a pipe.", "Error", self.source_layout)
        elif(fmt == "drug"):
            if(value not in self.drug_parents):
                return ("invalid-value", f"'{value}' is not in the Detailed Drug Code Map.", "Error", self.source_layout)
        elif(fmt == "range"):
            low, high, extra = field["range"]
            if(not value.isdigit()):
                return ("invalid-format", "Numbers only.", "Error", self.source_layout)
            if(value not in extra and not (low <= int(value) <= high)):
                return ("invalid-value", f"Must be {low} to {high}{' or ' + ', '.join(extra) if(extra) else ''}.", "Error", self.source_layout)
            if(field["pad_width"] and len(value) != field["pad_width"]):
                return ("invalid-format", f"Leading zeros must be included: send {field['pad_width']} digits, e.g. '{value.zfill(field['pad_width'])}'.", "Error", self.source_instructions)
        elif(fmt == "digits"):
            if(not value.isdigit()):
                return ("invalid-format", "Numbers only.", "Error", self.source_layout)
            if(field["xml_tag"] == "Phone" and len(value) != 10):
                return ("invalid-format", "Phone numbers are 10 digits.", "Error", self.source_layout)
        elif(fmt == "ssn"):
            if(not re.fullmatch(r"\d{3}-\d{2}-\d{4}", value)):
                return ("invalid-format", "SSN must be written ###-##-####.", "Error", self.source_layout)
        elif(fmt == "icd10"):
            if(value != "999.9997" and not re.fullmatch(r"[A-Z]\d[0-9A-Z](\.[0-9A-Z]{1,4})?", value)):
                return ("icd10", f"'{value}' is not an ICD-10 code written like F10.20 (or 999.9997 for unknown).", "Error", self.source_layout)
        elif(fmt == "state"):
            if(value.upper() not in self.state_names):
                return ("invalid-value", "Not a US state name.", "Error", self.source_layout)
        elif(fmt == "county"):
            if(value.upper() not in self.counties):
                return ("invalid-value", "Not a Kansas county name.", "Error", self.source_layout)
        return None

    def check_fields(self, values, fields, record_type, context, collateral=False):
        """
        Checks a set of elements: required ones (flag Y) must be present, and every present value must pass its rule.
        Conditionally required elements (flag C) are checked by the objects that know the condition.

        :param values: {tag: text}.
        :param fields: Field rule dicts to check.
        :param record_type: 'Client', 'Admission' or 'Discharge'.
        :param context: Report context for the issues.
        :param collateral: True when Client Type is 1, so only elements required for collateral clients are required.
        :return: List of issue dicts.
        """
        issues = []
        for field in fields:
            tag = field["xml_tag"]
            value = values.get(tag, "")
            if(not value):
                if(self.flag(field, record_type) == "Y" and (not collateral or field["required_if_collateral"])):
                    issues.append(self.issue(context, tag, "required", "Required, and blank."))
                continue
            problem = self.check_value(field, value)
            if(problem):
                issues.append(self.issue(context, tag, problem[0], problem[1], problem[2], problem[3], value))
        return issues


class Substance:
    def __init__(self
                 ,rank
                 ,substance=None
                 ,detailed_drug_code=None
                 ,route=None
                 ,frequency=None
                 ,age_first_use=None
                 ,discharge_substance=None
                 ,discharge_frequency=None
                 ,rules=None):
        """
        One ranked substance on an episode. It fills the Primary, Secondary or Tertiary elements
        of the admission's TreatmentEvent and, when given, of the discharge's.

        :param rank: 'P', 'S' or 'T' (or 'Primary', 'Secondary', 'Tertiary').
        :param substance: PrimarySubstance (and so on) at admission, e.g. '02'.
        :param detailed_drug_code: The four-digit detailed drug code at admission, e.g. '0201'.
        :param route: Route of administration at admission, e.g. '01'.
        :param frequency: Frequency of use at admission, e.g. '05'.
        :param age_first_use: Age of first use, e.g. '15'.
        :param discharge_substance: The substance reported at discharge for this rank.
        :param discharge_frequency: Frequency of use at discharge for this rank.
        :param rules: A WellSkyRules to share. One is made when not given.
        """
        # Class Objects
        self.rules = rules or WellSkyRules()

        # Class Data
        self.rank = self.rules.text(rank).upper()[:1]
        self.values = {
            "Substance": self.rules.text(substance)
            ,"DetailedDrugCode": self.rules.text(detailed_drug_code)
            ,"RouteOfAdministration": self.rules.text(route)
            ,"Frequency": self.rules.text(frequency)
            ,"AgeOfFirstUse": self.rules.text(age_first_use)
        }
        self.discharge_values = {
            "Substance": self.rules.text(discharge_substance)
            ,"Frequency": self.rules.text(discharge_frequency)
        }
        self.episode = None

    def slot(self):
        """
        The element prefix for this rank: 'Primary', 'Secondary', 'Tertiary', or '' for an unknown rank.
        """
        return self.rules.slots.get(self.rank, "")

    def admission_tags(self):
        """
        This substance's admission values keyed by XML tag (e.g. PrimarySubstance).
        """
        return {f"{self.slot()}{part}": value for part, value in self.values.items()}

    def discharge_tags(self):
        """
        This substance's discharge values keyed by XML tag (e.g. PrimaryFrequency).
        """
        return {f"{self.slot()}{part}": value for part, value in self.discharge_values.items()}

    def predict_errors(self, admission_context=None, discharge_context=None):
        """
        This substance's own predicted errors: its codes, the elements a reported substance requires,
        the 01 None / 96 Not applicable pairing, and whether the detailed drug code belongs to the substance.

        :param admission_context: Report context for the admission. A blank context is used when not given.
        :param discharge_context: Report context for the discharge, or None when the episode has no discharge.
        :return: List of issue dicts.
        """
        blank = {"record_type": "Admission", "license": "", "client_source_id": "", "episode_source_id": ""}
        admission_context = admission_context or blank
        slot = self.slot()
        if(not slot):
            return [self.rules.issue(admission_context, "Substance", "integrity", f"Rank '{self.rank}' is not P, S or T.", "Error", self.rules.source_integrity, self.rank)]
        issues = []
        substance = self.values["Substance"]
        for part, value in self.values.items():
            tag = f"{slot}{part}"
            if(value):
                problem = self.rules.check_value(self.rules.field("TreatmentEvent", tag), value)
                if(problem):
                    issues.append(self.rules.issue(admission_context, tag, problem[0], problem[1], problem[2], problem[3], value))
            elif(substance and part != "Substance"):
                issues.append(self.rules.issue(admission_context, tag, "required", f"Required when {slot}Substance is reported."))
        if(not substance and any(self.values[part] for part in self.rules.substance_parts[1:])):
            issues.append(self.rules.issue(admission_context, f"{slot}Substance", "required", f"Other {slot} elements are filled in but the substance is blank."))
        issues.extend(self.none_pairing(admission_context, self.values, ("RouteOfAdministration", "Frequency", "AgeOfFirstUse")))
        detail = self.values["DetailedDrugCode"]
        if(detail in self.rules.drug_parents and substance and self.rules.drug_parents[detail] != substance):
            issues.append(self.rules.issue(admission_context, f"{slot}DetailedDrugCode", "drug-substance", f"Detailed code {detail} belongs to substance {self.rules.drug_parents[detail]}, not {substance}.", value=detail))

        if(discharge_context is not None and any(self.discharge_values.values())):
            for part, value in self.discharge_values.items():
                tag = f"{slot}{part}"
                if(value):
                    problem = self.rules.check_value(self.rules.field("TreatmentEvent", tag), value)
                    if(problem):
                        issues.append(self.rules.issue(discharge_context, tag, problem[0], problem[1], problem[2], problem[3], value))
                else:
                    other = "Frequency" if(part == "Substance") else "Substance"
                    issues.append(self.rules.issue(discharge_context, tag, "required", f"Required at discharge when {slot}{other} is reported."))
            issues.extend(self.none_pairing(discharge_context, self.discharge_values, ("Frequency",)))
        return issues

    def none_pairing(self, context, values, parts):
        """
        The layout's rule that 96 (Not applicable) goes with substance 01 (None), and only with it.

        :param context: Report context for the issues.
        :param values: {part: text} for one record type.
        :param parts: The parts the rule applies to.
        :return: List of issue dicts.
        """
        issues = []
        substance = values["Substance"]
        for part in parts:
            value = values[part]
            if(value and substance and ((substance == "01") != (value == "96"))):
                message = "Substance 01 (None) needs 96 here." if(substance == "01") else "96 is only for substance 01 (None)."
                issues.append(self.rules.issue(context, f"{self.slot()}{part}", "none-substance", message, value=value))
        return issues

    def validate(self):
        """
        True when this substance has no predicted Error of its own.
        """
        return not any(i["severity"] == "Error" for i in self.predict_errors(discharge_context=None))


class Client:
    def __init__(self
                 ,source_id
                 ,last_name=None
                 ,first_name=None
                 ,dob=None
                 ,sex=None
                 ,race=None
                 ,hispanic_origin=None
                 ,gender_identity=None
                 ,sexual_orientation=None
                 ,county=None
                 ,middle_name=None
                 ,aka=None
                 ,phone=None
                 ,street=None
                 ,state=None
                 ,corrections_number=None
                 ,medicaid_number=None
                 ,ssn=None
                 ,aso=None
                 ,rules=None):
        """
        One person, written as <Client>. The client is written again for every episode, as in a working WellSky export.

        :param source_id: SourceID: the client's ID in the EHR, the same ID the EHR's ongoing WellSky export uses.
        :param last_name: LastName.
        :param first_name: FirstName.
        :param dob: DOB, as MMDDYYYY text or a date.
        :param sex: Sex: 1 male, 2 female, 7 unknown.
        :param race: Race, two digits, e.g. '05'.
        :param hispanic_origin: HispanicOrigin, two digits, e.g. '05'.
        :param gender_identity: GenderIdentity, e.g. '7'.
        :param sexual_orientation: SexualOrientation, two digits, e.g. '98'.
        :param county: CountyofResidence: a Kansas county name.
        :param middle_name: MiddleName.
        :param aka: AKA.
        :param phone: Phone, 10 digits.
        :param street: Street.
        :param state: State: a US state name.
        :param corrections_number: DepartmentOfCorrectionsNum.
        :param medicaid_number: MedicaidNumber.
        :param ssn: SSN, written ###-##-####.
        :param aso: ASO.
        :param rules: A WellSkyRules to share. One is made when not given.
        """
        # Class Objects
        self.rules = rules or WellSkyRules()

        # Class Data
        text = self.rules.text
        self.values = {
            "SourceID": text(source_id)
            ,"LastName": text(last_name)
            ,"FirstName": text(first_name)
            ,"MiddleName": text(middle_name)
            ,"AKA": text(aka)
            ,"DOB": text(dob)
            ,"Sex": text(sex)
            ,"Race": text(race)
            ,"HispanicOrigin": text(hispanic_origin)
            ,"GenderIdentity": text(gender_identity)
            ,"SexualOrientation": text(sexual_orientation)
            ,"Phone": text(phone)
            ,"Street": text(street)
            ,"State": text(state)
            ,"CountyofResidence": text(county)
            ,"DepartmentOfCorrectionsNum": text(corrections_number)
            ,"MedicaidNumber": text(medicaid_number)
            ,"SSN": text(ssn)
            ,"ASO": text(aso)
        }
        self.episodes = []

    def add_episode(self, episode):
        """
        Attaches an episode to this client.

        :param episode: An Episode.
        :return: The episode, so calls can be chained.
        """
        episode.client = self
        self.episodes.append(episode)
        return episode

    def context(self):
        """
        Report context for this client's own issues.
        """
        return {"record_type": "Client", "license": "", "client_source_id": self.values["SourceID"], "episode_source_id": ""}

    def predict_errors(self, today=None):
        """
        This client's own predicted errors: required elements, codes and formats, and a birth date in the future.

        :param today: The date the file is made, for the future-date check. Defaults to today.
        :return: List of issue dicts.
        """
        today = today or datetime.date.today()
        context = self.context()
        issues = self.rules.check_fields(self.values, self.rules.sent_fields("Client", "Client"), "Client", context)
        born = self.rules.as_date(self.values["DOB"])
        if(born and born > today):
            issues.append(self.rules.issue(context, "DOB", "integrity", "The birth date is in the future.", "Error", self.rules.source_integrity))
        return issues

    def validate(self):
        """
        True when this client has no predicted Error of its own.
        """
        return not any(i["severity"] == "Error" for i in self.predict_errors())


class Episode:
    def __init__(self
                 ,license
                 ,admit_date
                 ,treatment_setting=None
                 ,client_type=None
                 ,referral_source=None
                 ,criminal_justice_referral=None
                 ,enroll_type=None
                 ,source_id=None
                 ,event_source_id=None
                 ,education=None
                 ,employment_status=None
                 ,not_in_labor_force=None
                 ,pregnant=None
                 ,prenatal_care=None
                 ,veteran_status=None
                 ,living_arrangement=None
                 ,yearly_income=None
                 ,federal_poverty_level=None
                 ,people_in_household=None
                 ,children_in_home=None
                 ,children_at_risk=None
                 ,dcf_custody=None
                 ,income_source=None
                 ,health_insurance=None
                 ,payment_source=None
                 ,senate_bill_6=None
                 ,gambling_fund_member_type=None
                 ,gpra=None
                 ,marital_status=None
                 ,days_waiting=None
                 ,arrests=None
                 ,self_help=None
                 ,gambling_withdrawal=None
                 ,gambling_hidden=None
                 ,gambling_financial_trouble=None
                 ,tobacco_use=None
                 ,tobacco_type=None
                 ,tobacco_30_days=None
                 ,tb_positive=None
                 ,tb_risk=None
                 ,tb_symptoms=None
                 ,tb_education=None
                 ,tb_case_management=None
                 ,hiv=None
                 ,mh_treatment=None
                 ,co_occurring=None
                 ,psych_medication=None
                 ,su_history=None
                 ,mh_history=None
                 ,prior_sud_treatment=None
                 ,prior_sud_episodes=None
                 ,mh_treatment_episodes=None
                 ,moud=None
                 ,diagnosis=None
                 ,provider_id=None
                 ,rules=None):
        """
        One treatment episode: its admission and, after set_discharge(), its discharge.

        :param license: The provider license number for this episode's location, exactly as KDADS issued it
            (with any leading zeros). It names the XML file and, unless provider_id is given, is sent as ProviderID.
        :param admit_date: DateOfAdmission, as MMDDYYYY text or a date.
        :param treatment_setting: TreatmentSetting, two digits, e.g. '07'.
        :param client_type: ClientType: 1 codependent/collateral, 2 client.
        :param referral_source: ReferralSource, two digits.
        :param criminal_justice_referral: CriminalJusticeReferral; required when ReferralSource is 07.
        :param enroll_type: EnrollType. Defaults to Inpatient for settings 01 to 05, otherwise Outpatient.
        :param source_id: The episode's SourceID. Defaults to the pattern working WellSky exports use:
            TreatmentSetting + license + client SourceID + DateOfAdmission.
        :param event_source_id: The TreatmentEvent SourceID. Defaults to the episode's SourceID.
        :param education: HighestLevelOfEducation.
        :param employment_status: EmploymentStatus at admission.
        :param not_in_labor_force: NotInLaborForce at admission; required when EmploymentStatus is 04.
        :param pregnant: PregnantAtAdmission; required when the client's Sex is 2.
        :param prenatal_care: PrenatalCare.
        :param veteran_status: VeteranStatus.
        :param living_arrangement: LivingArrangement at admission.
        :param yearly_income: YearlyIncome, digits only.
        :param federal_poverty_level: FederalPovertyLevel.
        :param people_in_household: PeopleInHousehold, 1 to 10.
        :param children_in_home: ChildrenInHome.
        :param children_at_risk: ChildrenInHomeAtRisk, two digits.
        :param dcf_custody: DCFCustody.
        :param income_source: SourcesOfIncome.
        :param health_insurance: HealthInsurance.
        :param payment_source: PrimaryPaymentSource.
        :param senate_bill_6: SenateBill6Secondary.
        :param gambling_fund_member_type: GamblingFundMemberType.
        :param gpra: GPRA.
        :param marital_status: MaritalStatus.
        :param days_waiting: DaysWaiting.
        :param arrests: ArrestsInPast30Days at admission.
        :param self_help: SelfHelpGroupInPast30Days at admission.
        :param gambling_withdrawal: GamblingWithdrawal.
        :param gambling_hidden: GamblingHidden.
        :param gambling_financial_trouble: GamblingFinancialTrouble.
        :param tobacco_use: TobaccoUse.
        :param tobacco_type: TypeOfTobacco; codes separated by a pipe, e.g. '01|02'.
        :param tobacco_30_days: Tobacco30.
        :param tb_positive: TBPositive.
        :param tb_risk: TBRisk.
        :param tb_symptoms: TBSymptoms.
        :param tb_education: TBEducation.
        :param tb_case_management: TBCaseMgm.
        :param hiv: HIV.
        :param mh_treatment: MHTx.
        :param co_occurring: Co-OccurringMHSU.
        :param psych_medication: PsyMed.
        :param su_history: SUHistory.
        :param mh_history: MHHistory.
        :param prior_sud_treatment: PrevSUDTx.
        :param prior_sud_episodes: PrevSUDTxEp.
        :param mh_treatment_episodes: MHTxEp.
        :param moud: MOUD.
        :param diagnosis: SUDiagnosis: an ICD-10 code such as F10.20, or 999.9997 for unknown.
        :param provider_id: ProviderID, when WellSky knows the provider by a number other than its license.
            Defaults to the license.
        :param rules: A WellSkyRules to share. One is made when not given.
        """
        # Class Objects
        self.rules = rules or WellSkyRules()

        # Class Data
        text = self.rules.text
        setting = text(treatment_setting)
        self.license = self.rules.license_text(license)
        self.values = {
            "ProviderID": text(provider_id) or self.license
            ,"SourceID": text(source_id)
            ,"EnrollType": text(enroll_type) or ("Inpatient" if(setting in self.rules.inpatient_settings) else "Outpatient")
            ,"DateOfAdmission": text(admit_date)
            ,"ClientTransactionType": "A"
            ,"ClientType": text(client_type)
            ,"ReferralSource": text(referral_source)
            ,"CriminalJusticeReferral": text(criminal_justice_referral)
            ,"TreatmentSetting": setting
        }
        self.event_values = {
            "SourceID": text(event_source_id)
            ,"HighestLevelOfEducation": text(education)
            ,"EmploymentStatus": text(employment_status)
            ,"NotInLaborForce": text(not_in_labor_force)
            ,"PregnantAtAdmission": text(pregnant)
            ,"PrenatalCare": text(prenatal_care)
            ,"VeteranStatus": text(veteran_status)
            ,"LivingArrangement": text(living_arrangement)
            ,"YearlyIncome": text(yearly_income)
            ,"FederalPovertyLevel": text(federal_poverty_level)
            ,"PeopleInHousehold": text(people_in_household)
            ,"ChildrenInHome": text(children_in_home)
            ,"ChildrenInHomeAtRisk": text(children_at_risk)
            ,"DCFCustody": text(dcf_custody)
            ,"SourcesOfIncome": text(income_source)
            ,"HealthInsurance": text(health_insurance)
            ,"PrimaryPaymentSource": text(payment_source)
            ,"SenateBill6Secondary": text(senate_bill_6)
            ,"GamblingFundMemberType": text(gambling_fund_member_type)
            ,"GPRA": text(gpra)
            ,"MaritalStatus": text(marital_status)
            ,"DaysWaiting": text(days_waiting)
            ,"ArrestsInPast30Days": text(arrests)
            ,"SelfHelpGroupInPast30Days": text(self_help)
            ,"GamblingWithdrawal": text(gambling_withdrawal)
            ,"GamblingHidden": text(gambling_hidden)
            ,"GamblingFinancialTrouble": text(gambling_financial_trouble)
            ,"TobaccoUse": text(tobacco_use)
            ,"TypeOfTobacco": text(tobacco_type)
            ,"Tobacco30": text(tobacco_30_days)
            ,"TBPositive": text(tb_positive)
            ,"TBRisk": text(tb_risk)
            ,"TBSymptoms": text(tb_symptoms)
            ,"TBEducation": text(tb_education)
            ,"TBCaseMgm": text(tb_case_management)
            ,"HIV": text(hiv)
            ,"MHTx": text(mh_treatment)
            ,"Co-OccurringMHSU": text(co_occurring)
            ,"PsyMed": text(psych_medication)
            ,"SUHistory": text(su_history)
            ,"MHHistory": text(mh_history)
            ,"PrevSUDTx": text(prior_sud_treatment)
            ,"PrevSUDTxEp": text(prior_sud_episodes)
            ,"MHTxEp": text(mh_treatment_episodes)
            ,"MOUD": text(moud)
            ,"SUDiagnosis": text(diagnosis)
        }
        # Filled by set_discharge(). Record elements the discharge doesn't hold are taken from the admission.
        self.discharge_values = None
        self.discharge_event_values = None
        self.substances = []
        self.client = None
        # False only for a discharge read from a file that doesn't hold its admission.
        self.admission_included = True

    def add_substance(self, substance):
        """
        Attaches a ranked substance to this episode.

        :param substance: A Substance.
        :return: The substance, so calls can be chained.
        """
        substance.episode = self
        self.substances.append(substance)
        return substance

    def set_discharge(self
                      ,discharge_date
                      ,discharge_reason=None
                      ,last_contact_date=None
                      ,treatment_setting=None
                      ,employment_status=None
                      ,not_in_labor_force=None
                      ,living_arrangement=None
                      ,arrests=None
                      ,self_help=None
                      ,event_source_id=None):
        """
        Records the episode's discharge. The discharge is written as its own <Discharge> after the <Admission>.
        Discharge substances are set on each Substance (discharge_substance, discharge_frequency).

        :param discharge_date: DateOFDischarge, as MMDDYYYY text or a date.
        :param discharge_reason: ReasonForDischarge, two digits.
        :param last_contact_date: DateOfLastContact. Defaults to the discharge date, the layout's value when unanswered.
        :param treatment_setting: TreatmentSetting at discharge. Defaults to the admission's.
        :param employment_status: EmploymentStatus at discharge.
        :param not_in_labor_force: NotInLaborForce at discharge.
        :param living_arrangement: LivingArrangement at discharge.
        :param arrests: ArrestsInPast30Days at discharge.
        :param self_help: SelfHelpGroupInPast30Days at discharge.
        :param event_source_id: The discharge TreatmentEvent SourceID. Defaults to the admission's, as in a working WellSky export.
        :return: The episode, so calls can be chained.
        """
        text = self.rules.text
        self.discharge_values = {
            "ClientTransactionType": "D"
            ,"TreatmentSetting": text(treatment_setting)
            ,"DateOfLastContact": text(last_contact_date) or text(discharge_date)
            ,"DateOFDischarge": text(discharge_date)
            ,"ReasonForDischarge": text(discharge_reason)
        }
        self.discharge_event_values = {
            "SourceID": text(event_source_id)
            ,"EmploymentStatus": text(employment_status)
            ,"NotInLaborForce": text(not_in_labor_force)
            ,"LivingArrangement": text(living_arrangement)
            ,"ArrestsInPast30Days": text(arrests)
            ,"SelfHelpGroupInPast30Days": text(self_help)
        }
        return self

    def source_id(self):
        """
        The episode SourceID: the one given, or the pattern working WellSky exports use
        (TreatmentSetting + license + client SourceID + DateOfAdmission) once the episode has a client.
        """
        if(self.values["SourceID"]):
            return self.values["SourceID"]
        if(self.client is None):
            return ""
        return f"{self.values['TreatmentSetting']}{self.license}{self.client.values['SourceID']}{self.values['DateOfAdmission']}"

    def record_types(self):
        """
        The records this episode writes: 'Admission', then 'Discharge' when discharged.
        """
        types = ["Admission"] if(self.admission_included) else []
        if(self.discharge_values is not None):
            types.append("Discharge")
        return types

    def record_values(self, record_type):
        """
        Every element of one record, keyed by tag, ready to write or check.

        :param record_type: 'Admission' or 'Discharge'.
        :return: Tuple of (record element values, TreatmentEvent values).
        """
        source_id = self.source_id()
        record = dict(self.values, SourceID=source_id)
        if(record_type == "Admission"):
            event = dict(self.event_values)
            event["SourceID"] = event["SourceID"] or source_id
            for substance in self.substances:
                if(substance.slot()):
                    event.update(substance.admission_tags())
            return record, event
        for tag, value in self.discharge_values.items():
            if(value or tag not in record):
                record[tag] = value
        event = dict(self.discharge_event_values)
        event["SourceID"] = event["SourceID"] or self.event_values["SourceID"] or source_id
        for substance in self.substances:
            if(substance.slot()):
                event.update(substance.discharge_tags())
        return record, event

    def context(self, record_type):
        """
        Report context for one of this episode's records.

        :param record_type: 'Admission' or 'Discharge'.
        """
        client_id = self.client.values["SourceID"] if(self.client) else ""
        return {"record_type": record_type, "license": self.license, "client_source_id": client_id, "episode_source_id": self.source_id()}

    def predict_errors(self, today=None):
        """
        This episode's predicted errors: every element of its admission and discharge, the layout's
        conditional rules, its substances, and dates that contradict each other.

        :param today: The date the file is made, for the future-date checks. Defaults to today.
        :return: List of issue dicts.
        """
        today = today or datetime.date.today()
        issues = []
        if(self.client is None):
            issues.append(self.rules.issue(self.context("Admission"), "Client", "integrity", "The episode isn't attached to a client, so it can't be written.", "Error", self.rules.source_integrity))
        if(not self.admission_included):
            issues.append(self.rules.issue(self.context("Discharge"), "Admission", "no-admission", "This file holds the discharge without its admission. WellSky accepts it only if the admission was sent before.", "Warning"))
        ranks = [s.rank for s in self.substances]
        for rank in sorted({r for r in ranks if(ranks.count(r) > 1)}):
            issues.append(self.rules.issue(self.context("Admission"), "Substance", "integrity", f"More than one substance is ranked {rank}; only the last one is written.", "Error", self.rules.source_integrity, rank))

        for record_type in self.record_types():
            context = self.context(record_type)
            record, event = self.record_values(record_type)
            collateral = record["ClientType"] == "1"
            issues.extend(self.rules.check_fields(record, self.rules.sent_fields("Record", record_type), record_type, context, collateral))
            event_fields = [f for f in self.rules.sent_fields("TreatmentEvent", record_type) if(f["xml_tag"] not in self.rules.substance_tags)]
            issues.extend(self.rules.check_fields(event, event_fields, record_type, context, collateral))
            if(not event.get("PrimarySubstance") and not collateral):
                issues.append(self.rules.issue(context, "PrimarySubstance", "required", "Required, and blank."))
            expected = ("D",) if(record_type == "Discharge") else ("A", "T")
            if(record["ClientTransactionType"] and record["ClientTransactionType"] not in expected):
                issues.append(self.rules.issue(context, "ClientTransactionType", "invalid-value", f"A and T are valid for an Admission only, and D for a Discharge only.", value=record["ClientTransactionType"]))
            issues.extend(self.conditional_errors(record_type, record, event, context))
            issues.extend(self.duplicate_errors(record_type, event, context))
            issues.extend(self.date_errors(record_type, record, context, today))

        discharge_context = self.context("Discharge") if(self.discharge_values is not None) else None
        for substance in self.substances:
            issues.extend(substance.predict_errors(self.context("Admission"), discharge_context))
        return issues

    def conditional_errors(self, record_type, record, event, context):
        """
        The layout's conditional rules for one record.

        :param record_type: 'Admission' or 'Discharge'.
        :param record: The record element values.
        :param event: The TreatmentEvent values.
        :param context: Report context for the issues.
        :return: List of issue dicts.
        """
        issue = self.rules.issue
        issues = []
        sex = self.client.values["Sex"] if(self.client) else ""
        if(record_type == "Admission"):
            referral, justice = record["ReferralSource"], record["CriminalJusticeReferral"]
            if(referral == "07" and not justice):
                issues.append(issue(context, "CriminalJusticeReferral", "required", "Required when ReferralSource is 07."))
            elif(referral == "07" and justice == "96"):
                issues.append(issue(context, "CriminalJusticeReferral", "invalid-value", "96 isn't allowed when ReferralSource is 07.", value=justice))
            elif(referral and referral != "07" and justice not in ("", "96")):
                issues.append(issue(context, "CriminalJusticeReferral", "invalid-value", "Only for ReferralSource 07; otherwise leave it blank or send 96.", "Warning", value=justice))
            if(sex == "2" and not event["PregnantAtAdmission"]):
                issues.append(issue(context, "PregnantAtAdmission", "required", "Required when the client's Sex is 2."))
            if(event["PrenatalCare"] and event["PregnantAtAdmission"] != "1"):
                issues.append(issue(context, "PrenatalCare", "invalid-value", "Answered only when PregnantAtAdmission is 1.", "Warning", value=event["PrenatalCare"]))
            needs = (("TobaccoUse", "1", ("TypeOfTobacco", "Tobacco30")), ("TBPositive", "2", ("TBRisk", "TBSymptoms")), ("PrevSUDTx", "1", ("PrevSUDTxEp", "MHTxEp")))
            for tag, trigger, required in needs:
                if(event[tag] == trigger):
                    for needed in required:
                        if(not event[needed]):
                            issues.append(issue(context, needed, "required", f"Required when {tag} is {trigger}."))
            if(event["TobaccoUse"] == "2"):
                for tag in ("TypeOfTobacco", "Tobacco30"):
                    if(event[tag]):
                        issues.append(issue(context, tag, "invalid-value", "Not answered when TobaccoUse is 2.", "Warning", self.rules.source_instructions, event[tag]))
        employment, labor = event["EmploymentStatus"], event["NotInLaborForce"]
        if(employment == "04" and not labor):
            issues.append(issue(context, "NotInLaborForce", "required", "Required when EmploymentStatus is 04."))
        elif(employment == "04" and labor == "96"):
            issues.append(issue(context, "NotInLaborForce", "invalid-value", "96 isn't allowed when EmploymentStatus is 04.", value=labor))
        elif(employment and employment != "04" and labor not in ("", "96")):
            issues.append(issue(context, "NotInLaborForce", "invalid-value", "Only for EmploymentStatus 04; otherwise leave it blank or send 96.", "Warning", value=labor))
        if(record["TreatmentSetting"] == "96" and record["ClientType"] != "1"):
            issues.append(issue(context, "TreatmentSetting", "collateral-only", "96 is only for Client Type 1.", value="96"))
        on = record["DateOFDischarge"] if(record_type == "Discharge") else record["DateOfAdmission"]
        age = self.rules.age_on(self.client.values["DOB"], on) if(self.client) else None
        if(age is not None and employment == "96" and age >= 16):
            issues.append(issue(context, "EmploymentStatus", "invalid-value", "96 is only for clients under 16.", value=employment))
        elif(age is not None and employment and employment != "96" and age < 16):
            issues.append(issue(context, "EmploymentStatus", "invalid-value", "The client is under 16, so WellSky replaces this with 96 (layout revision 13).", "Warning", value=employment))
        if(record_type == "Admission" and age is not None):
            for slot in self.rules.slots.values():
                first = event.get(f"{slot}AgeOfFirstUse", "")
                if(first.isdigit() and first not in ("96", "97") and int(first) > age):
                    issues.append(issue(context, f"{slot}AgeOfFirstUse", "kdads", f"Age of first use {first} is greater than the client's age at admission.", "Warning", self.rules.source_kdads, first))
        return issues

    def duplicate_errors(self, record_type, event, context):
        """
        The layout's rule that a substance can't repeat across Primary, Secondary and Tertiary unless
        the detailed drug codes differ. 01 (None) may repeat. 97 (Unknown) repeats in a working WellSky export,
        so a repeated 97 is only a Warning.

        :param record_type: 'Admission' or 'Discharge'.
        :param event: The TreatmentEvent values.
        :param context: Report context for the issues.
        :return: List of issue dicts.
        """
        issues = []
        seen = []
        for slot in self.rules.slots.values():
            substance = event.get(f"{slot}Substance", "")
            pair = (substance, event.get(f"{slot}DetailedDrugCode", ""))
            if(substance and substance != "01" and pair in seen):
                unknown = substance == "97" or record_type == "Discharge"
                note = " Discharges carry no detailed drug codes, so this is only a guess." if(record_type == "Discharge") else ""
                issues.append(self.rules.issue(context, f"{slot}Substance", "duplicate-substance", f"Substance {substance} repeats an earlier slot with the same detailed drug code.{note}", "Warning" if(unknown) else "Error", self.rules.source_reading if(unknown) else None, substance))
            seen.append(pair)
        return issues

    def date_errors(self, record_type, record, context, today):
        """
        Dates that contradict each other or the calendar.

        :param record_type: 'Admission' or 'Discharge'.
        :param record: The record element values.
        :param context: Report context for the issues.
        :param today: The date the file is made.
        :return: List of issue dicts.
        """
        issue = self.rules.issue
        as_date = self.rules.as_date
        issues = []
        admitted = as_date(record["DateOfAdmission"])
        born = as_date(self.client.values["DOB"]) if(self.client) else None
        if(admitted and admitted > today):
            issues.append(issue(context, "DateOfAdmission", "kdads", "The admission date is in the future.", "Warning", self.rules.source_kdads, record["DateOfAdmission"]))
        if(record_type == "Admission" and admitted and born and born > admitted):
            issues.append(issue(context, "DateOfAdmission", "integrity", "The client was admitted before their birth date.", "Error", self.rules.source_integrity, record["DateOfAdmission"]))
        if(record_type == "Discharge"):
            discharged, last = as_date(record["DateOFDischarge"]), as_date(record["DateOfLastContact"])
            if(discharged and admitted and discharged < admitted):
                issues.append(issue(context, "DateOFDischarge", "integrity", "The discharge is dated before the admission.", "Error", self.rules.source_integrity, record["DateOFDischarge"]))
            if(discharged and discharged > today):
                issues.append(issue(context, "DateOFDischarge", "kdads", "The discharge date is in the future.", "Warning", self.rules.source_kdads, record["DateOFDischarge"]))
            # WellSky defines last contact as the last contact before discharging, so a date outside the episode contradicts it.
            if(last and discharged and last > discharged):
                issues.append(issue(context, "DateOfLastContact", "kdads", "The last contact is after the discharge.", "Warning", self.rules.source_kdads, record["DateOfLastContact"]))
            if(last and admitted and last < admitted):
                issues.append(issue(context, "DateOfLastContact", "kdads", "The last contact is before the admission.", "Warning", self.rules.source_kdads, record["DateOfLastContact"]))
            if(last and last < self.rules.earliest_contact):
                issues.append(issue(context, "DateOfLastContact", "kdads", "The last contact is before 01/01/2000.", "Warning", self.rules.source_kdads, record["DateOfLastContact"]))
        return issues

    def validate(self):
        """
        True when this episode has no predicted Error.
        """
        return not any(i["severity"] == "Error" for i in self.predict_errors())


class WellSkyPredictor:
    def __init__(self
                 ,rules=None
                 ,monitor=None):
        """
        Builds the predicted error report: every object's own checks, plus checks that need the whole file.

        :param rules: A WellSkyRules to share. One is made when not given.
        :param monitor: Optional injected monitor with an add_log method and a verbose attribute.
        """
        # Set up the monitor
        self.monitor = monitor or ConsoleMonitor()

        # Class Data
        self.report_columns = {
            "severity": "Severity"
            ,"error": "Error"
            ,"element": "Element"
            ,"value": "Value"
            ,"message": "Message"
            ,"source": "Source"
            ,"record_type": "Record Type"
            ,"license": "License"
            ,"client_source_id": "Client Source ID"
            ,"episode_source_id": "Episode Source ID"
        }

        # Class Objects
        self.rules = rules or WellSkyRules()

    def predict(self, clients, today=None):
        """
        Every predicted error for a set of clients, Errors first.

        :param clients: List of Client objects.
        :param today: The date the file is made, for the future-date checks. Defaults to today.
        :return: List of issue dicts.
        """
        today = today or datetime.date.today()
        issues = []
        for client in clients:
            issues.extend(client.predict_errors(today))
            for episode in client.episodes:
                issues.extend(episode.predict_errors(today))
        issues.extend(self.file_errors(clients))
        issues.sort(key=lambda i: (i["severity"] != "Error", i["client_source_id"], i["episode_source_id"], i["record_type"]))
        return issues

    def file_errors(self, clients):
        """
        Checks that need the whole file: repeated episode and treatment event IDs, one client ID with
        different details, licenses WellSky may not know, and clients with nothing to send.

        :param clients: List of Client objects.
        :return: List of issue dicts.
        """
        issue = self.rules.issue
        issues = []
        episodes = {}
        events = {}
        people = {}
        for client in clients:
            context = client.context()
            if(not client.episodes):
                issues.append(issue(context, "Client", "integrity", "The client has no episodes, so nothing is written for them.", "Warning", self.rules.source_integrity))
            details = tuple(client.values[tag] for tag in ("LastName", "FirstName", "DOB", "Sex"))
            people.setdefault(client.values["SourceID"], set()).add(details)
            for episode in client.episodes:
                key = (episode.license, episode.source_id(), tuple(episode.record_types()))
                episodes[key] = episodes.get(key, 0) + 1
                for record_type in episode.record_types():
                    _record, event = episode.record_values(record_type)
                    events.setdefault(event["SourceID"], set()).add(episode.source_id())
        for (license_number, source_id, _types), count in episodes.items():
            if(count > 1 and source_id):
                context = {"record_type": "Episode", "license": license_number, "client_source_id": "", "episode_source_id": source_id}
                issues.append(issue(context, "SourceID", "integrity", f"This episode appears {count} times in the file.", "Error", self.rules.source_integrity, source_id))
        for event_id, owners in events.items():
            if(event_id and len(owners) > 1):
                context = {"record_type": "Episode", "license": "", "client_source_id": "", "episode_source_id": ", ".join(sorted(owners))}
                issues.append(issue(context, "SourceID", "integrity", f"TreatmentEvent SourceID {event_id} is used by {len(owners)} episodes; the layout says it should not repeat.", "Warning", self.rules.source_layout, event_id))
        for source_id, details in people.items():
            if(source_id and len(details) > 1):
                context = {"record_type": "Client", "license": "", "client_source_id": source_id, "episode_source_id": ""}
                issues.append(issue(context, "SourceID", "integrity", "This client SourceID appears with different names, birth dates or sex.", "Warning", self.rules.source_integrity, source_id))
        licenses = sorted({e.license for c in clients for e in c.episodes if(e.license)})
        for license_number in licenses:
            if(not re.fullmatch(r"[A-Za-z0-9]+", license_number)):
                context = {"record_type": "File", "license": license_number, "client_source_id": "", "episode_source_id": ""}
                issues.append(issue(context, "ProviderID", "provider-id", "The license names the file, and the file name may hold only the license: letters and digits, no spaces or symbols.", "Error", self.rules.source_instructions, license_number))
        # WellSky's provider instructions: all of one client's records in a file belong in one <Client>
        # element, or a discharge may not find its admission.
        elements = {}
        for client in clients:
            for license_number in {e.license for e in client.episodes}:
                elements.setdefault((license_number, client.values["SourceID"]), []).append(client)
        for (license_number, source_id), owners in elements.items():
            if(source_id and len(owners) > 1):
                context = {"record_type": "Client", "license": license_number, "client_source_id": source_id, "episode_source_id": ""}
                issues.append(issue(context, "Client", "integrity", f"This client is split across {len(owners)} <Client> elements. Keep all of one client's records in one <Client>, or a discharge may not find its admission.", "Warning", self.rules.source_instructions, source_id))
        return issues

    def summarize(self, issues, clients, files=None):
        """
        Counts for the log and the caller. Holds no client information.

        :param issues: List of issue dicts.
        :param clients: List of Client objects.
        :param files: Optional {file name: XML text} that was built.
        :return: Summary dict.
        """
        episodes = [e for c in clients for e in c.episodes]
        blocked = {(i["license"], i["episode_source_id"]) for i in issues if(i["severity"] == "Error" and i["episode_source_id"])}
        by_error = {}
        by_element = {}
        for i in issues:
            key = f"{i['severity']}: {i['error']}"
            by_error[key] = by_error.get(key, 0) + 1
            by_element[i["element"]] = by_element.get(i["element"], 0) + 1
        return {
            "clients": len(clients)
            ,"episodes": len(episodes)
            ,"admissions": sum(1 for e in episodes if(e.admission_included))
            ,"discharges": sum(1 for e in episodes if(e.discharge_values is not None))
            ,"episodes_with_errors": len(blocked)
            ,"errors": sum(1 for i in issues if(i["severity"] == "Error"))
            ,"warnings": sum(1 for i in issues if(i["severity"] == "Warning"))
            ,"by_error": dict(sorted(by_error.items(), key=lambda kv: -kv[1]))
            ,"by_element": dict(sorted(by_element.items(), key=lambda kv: -kv[1]))
            ,"files": sorted(files or {})
        }

    def log_summary(self, summary):
        """
        Logs the summary counts. Holds no client information.

        :param summary: Summary dict from summarize().
        """
        self.monitor.add_log(
            log_system="WellSkyPredictor"
            ,log_category="Log Summary"
            ,log_subcategory="Totals"
            ,log_line=f"{summary['clients']} client(s), {summary['episodes']} episode(s), {summary['admissions']} admission(s), {summary['discharges']} discharge(s); {summary['errors']} predicted error(s) and {summary['warnings']} warning(s); {summary['episodes_with_errors']} episode(s) with at least one error."
        )
        for name, count in summary["by_error"].items():
            self.monitor.add_log(
                log_system="WellSkyPredictor"
                ,log_category="Log Summary"
                ,log_subcategory="By Error"
                ,log_line=f"{count} x {name}"
            )

    def write_report(self, issues, path):
        """
        Writes the predicted error report as CSV, one row per predicted error. It holds client IDs.

        :param issues: List of issue dicts.
        :param path: The CSV file to write.
        :return: The path written.
        """
        path = Path(path)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(self.report_columns.values())
            for i in issues:
                writer.writerow([i[key] for key in self.report_columns])
        self.monitor.add_log(
            log_system="WellSkyPredictor"
            ,log_category="Write Report"
            ,log_subcategory="Written"
            ,log_line=f"Wrote {len(issues)} row(s) to {path.name}."
        )
        return path


class WellSkyTEDS:
    def __init__(self
                 ,path=None
                 ,exclude_errors=False
                 ,dry_run=False
                 ,now=None
                 ,monitor=None):
        """
        Collects clients, predicts WellSky's errors, and writes the XML and the predicted error report.

        :param path: The folder for this run. The XML files and the predicted error report are written here,
            and the folder is created if it doesn't exist. When no clients are added in code, execute() instead
            checks the .xml files already in this folder and writes the report beside them; those files are
            never changed.
        :param exclude_errors: When True, leave out of the XML every episode with a predicted Error.
            Default False: everything is written, and the report says what WellSky is likely to reject.
        :param dry_run: When True, build and check everything, log counts, and write nothing.
        :param now: Datetime used for ReportingDate and the file names. Defaults to the current time.
        :param monitor: Optional injected monitor with an add_log method and a verbose attribute.
        """
        # Set up the monitor
        self.monitor = monitor or ConsoleMonitor()

        # Class Settings
        self.cli_path = Path(path) if(path) else None
        self.cli_exclude_errors = exclude_errors
        self.cli_dry_run = dry_run
        self.cli_now = now or datetime.datetime.now()

        # Class Data
        self.report_file = "wellsky_predicted_errors.csv"
        self.file_pattern = "KDADS_{license}_{stamp}.xml"
        # Clients added in code are written; clients read from the files in path are only checked.
        self.clients = []
        self.read_clients = []
        self.issues = []
        self.summary = {}

        # Class Objects
        self.rules = WellSkyRules()
        self.predictor = WellSkyPredictor(rules=self.rules, monitor=self.monitor)

    def add_client(self, client):
        """
        Adds a client, with its episodes and substances, to the file.

        :param client: A Client.
        :return: The client, so calls can be chained.
        """
        self.clients.append(client)
        return client

    def add_record(self, client, episodes=None):
        """
        Builds and adds a whole client from plain dicts: the client's values, and a list of episodes,
        each holding its values plus optional 'substances' (a list of Substance values) and 'discharge'
        (the set_discharge() values). Keys are the same names the classes take.

        :param client: Dict of Client values, e.g. {"source_id": "80000001", "last_name": "Doe", ...}.
        :param episodes: List of dicts of Episode values, each with optional 'substances' and 'discharge'.
        :return: The Client built.
        """
        person = Client(**client, rules=self.rules)
        for item in episodes or []:
            values = dict(item)
            substances = values.pop("substances", [])
            discharge = values.pop("discharge", None)
            episode = person.add_episode(Episode(**values, rules=self.rules))
            for substance in substances:
                episode.add_substance(Substance(**substance, rules=self.rules))
            if(discharge):
                episode.set_discharge(**discharge)
        return self.add_client(person)

    def predict_errors(self):
        """
        Every predicted error for the clients added so far and any read from the files in path, Errors first.

        :return: List of issue dicts.
        """
        self.issues = self.predictor.predict(self.clients + self.read_clients, self.cli_now.date())
        return self.issues

    def add_elements(self, parent, fields, values):
        """
        Appends one child per element in layout order, writing blanks as empty tags.

        :param parent: ElementTree element.
        :param fields: Field rule dicts, in order.
        :param values: {tag: text}.
        """
        for field in fields:
            child = ET.SubElement(parent, field["xml_tag"])
            text = values.get(field["xml_tag"], "")
            if(text):
                child.text = text

    def build_client(self, root, client, episodes):
        """
        Appends one <Client> holding every given episode of that client: each episode's <Admission> and,
        when discharged, its <Discharge>. WellSky's provider instructions require all of one client's records
        in a file to sit in the same <Client> element, so a discharge can find its admission.

        :param root: The <KSTeds> element.
        :param client: The Client.
        :param episodes: That client's episodes for this file, in the order they were added.
        """
        rules = self.rules
        element = ET.SubElement(root, "Client")
        self.add_elements(element, rules.sent_fields("Client", "Client"), client.values)
        for episode in episodes:
            for record_type in episode.record_types():
                record, event = episode.record_values(record_type)
                child = ET.SubElement(element, record_type)
                self.add_elements(child, rules.sent_fields("Record", record_type), record)
                treatment = ET.SubElement(child, "TreatmentEvent")
                self.add_elements(treatment, rules.sent_fields("TreatmentEvent", record_type), event)

    def build_xml(self, episodes):
        """
        One <KSTeds> document, written on one line after the XML declaration. Episodes are grouped under
        their client, in the order the clients were first seen.

        :param episodes: Episodes for one license, in the order they were added.
        :return: The XML text.
        """
        root = ET.Element("KSTeds")
        ET.SubElement(root, "StateCode").text = "KS"
        ET.SubElement(root, "ReportingDate").text = self.cli_now.strftime("%m%d%Y")
        grouped = {}
        for episode in episodes:
            grouped.setdefault(id(episode.client), (episode.client, []))[1].append(episode)
        for client, client_episodes in grouped.values():
            self.build_client(root, client, client_episodes)
        return '<?xml version="1.0" encoding="UTF-8"?>' + ET.tostring(root, encoding="unicode")

    def build_files(self):
        """
        One file per license. With exclude_errors, episodes with a predicted Error are left out.
        Episodes with no license can't be named into a file and are left out (the report flags them).

        :return: Dict of {file name: XML text}.
        """
        by_license = {}
        skipped = 0
        for client in self.clients:
            for episode in client.episodes:
                if(not episode.license or (self.cli_exclude_errors and not (client.validate() and episode.validate()))):
                    skipped += 1
                    continue
                by_license.setdefault(episode.license, []).append(episode)
        if(skipped):
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Build Files"
                ,log_subcategory="Left Out"
                ,log_line=f"{skipped} episode(s) left out of the XML (no license{', or a predicted error' if(self.cli_exclude_errors) else ''})."
            )
        stamp = self.cli_now.strftime("%Y%m%d%H%M")
        return {self.file_pattern.format(license=license_number, stamp=stamp): self.build_xml(episodes) for license_number, episodes in by_license.items()}

    def read_xml(self, path):
        """
        Reads WellSky XML files back into Client, Episode and Substance objects, so they can be checked.

        :param path: An XML file, or a folder of them.
        :return: List of Client objects, one per <Client> element.
        """
        path = Path(path)
        files = sorted(path.glob("*.xml")) if(path.is_dir()) else [path]
        clients = []
        for file in files:
            root = ET.parse(file).getroot()
            for element in root.findall("Client"):
                clients.append(self.client_from_element(element))
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Read XML"
                ,log_subcategory="File Read"
                ,log_line=f"Read {len(root.findall('Client'))} client element(s) from {file.name}."
            )
        return clients

    def client_from_element(self, element):
        """
        One <Client> element as a Client, with its episodes. A <Discharge> joins the <Admission> with the
        same SourceID in the same <Client>; a discharge without one becomes an episode with no admission.

        :param element: A <Client> ElementTree element.
        :return: The Client.
        """
        values = {c.tag: (c.text or "").strip() for c in element if(c.tag not in ("Admission", "Discharge"))}
        client = Client(source_id=values.get("SourceID", ""), rules=self.rules)
        client.values.update(values)
        by_source = {}
        for record in element:
            if(record.tag not in ("Admission", "Discharge")):
                continue
            record_values = {c.tag: (c.text or "").strip() for c in record if(c.tag != "TreatmentEvent")}
            event_element = record.find("TreatmentEvent")
            event = {c.tag: (c.text or "").strip() for c in event_element} if(event_element is not None) else {}
            source_id = record_values.get("SourceID", "")
            episode = by_source.get(source_id)
            if(episode is None):
                episode = client.add_episode(Episode(license=record_values.get("ProviderID", ""), admit_date=record_values.get("DateOfAdmission", ""), rules=self.rules))
                episode.values.update({k: v for k, v in record_values.items() if(k in episode.values)})
                by_source[source_id] = episode
                episode.admission_included = record.tag == "Admission"
            substance_values = {k: v for k, v in event.items() if(k in self.rules.substance_tags)}
            event_values = {k: v for k, v in event.items() if(k not in self.rules.substance_tags)}
            if(record.tag == "Admission"):
                episode.admission_included = True
                episode.event_values.update(event_values)
            else:
                # A file may leave elements out instead of writing empty tags. Every discharge element
                # starts blank, so a missing one is checked like a blank one.
                discharge_tags = [f["xml_tag"] for f in self.rules.sent_fields("TreatmentEvent", "Discharge") if(f["xml_tag"] not in self.rules.substance_tags)]
                episode.discharge_values = dict(record_values)
                episode.discharge_event_values = dict({tag: "" for tag in discharge_tags}, **event_values)
            self.substances_from_tags(episode, substance_values, record.tag == "Discharge")
        return client

    def substances_from_tags(self, episode, values, discharge):
        """
        Fills an episode's substances from Primary/Secondary/Tertiary tags read from a file.

        :param episode: The Episode.
        :param values: {tag: text} for the substance elements.
        :param discharge: True when the tags come from a <Discharge>.
        """
        for rank, slot in self.rules.slots.items():
            parts = self.rules.discharge_parts if(discharge) else self.rules.substance_parts
            found = {part: values.get(f"{slot}{part}", "") for part in parts}
            if(not any(found.values())):
                continue
            substance = next((s for s in episode.substances if(s.rank == rank)), None)
            if(substance is None):
                substance = episode.add_substance(Substance(rank=rank, rules=self.rules))
            target = substance.discharge_values if(discharge) else substance.values
            target.update(found)

    def write_outputs(self, files, folder):
        """
        Writes the XML files and the predicted error report.

        :param files: Dict of {file name: XML text}.
        :param folder: The folder to write to.
        """
        for name, text in files.items():
            with open(folder / name, "w", encoding="utf-8", newline="") as handle:
                handle.write(text)
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Write Outputs"
                ,log_subcategory="XML Written"
                ,log_line=f"Wrote {name}."
            )
        self.predictor.write_report(self.issues, folder / self.report_file)
        self.monitor.add_log(
            log_system="WellSkyTEDS"
            ,log_category="Write Outputs"
            ,log_subcategory="Written"
            ,log_line=f"Wrote {len(files)} XML file(s) and the predicted error report to {folder}."
        )

    def execute(self):
        """
        With clients added in code: checks them, then writes the XML and the predicted error report into path.
        With none: checks the .xml files already in path and writes the report there, leaving the files as they are.

        :return: The summary dict, or None when validation fails.
        """
        if(not self.validate()):
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Execute"
                ,log_subcategory="Validation Failure"
                ,log_line="Validation failure is fatal."
            )
            return None

        if(not self.clients):
            self.read_clients = self.read_xml(self.cli_path)
        self.predict_errors()
        files = self.build_files() if(self.clients) else {}
        self.summary = self.predictor.summarize(self.issues, self.clients + self.read_clients, files)
        self.predictor.log_summary(self.summary)
        if(self.cli_dry_run):
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Execute"
                ,log_subcategory="Dry Run"
                ,log_line=f"Dry run: nothing written. {len(files)} XML file(s) and the report would be written."
            )
            return self.summary
        self.cli_path.mkdir(parents=True, exist_ok=True)
        self.write_outputs(files, self.cli_path)
        return self.summary

    def validate(self):
        """
        Validates the settings and what has been added, and logs anything missing or in conflict.

        :return: True when the run can go ahead, otherwise False.
        """
        # Validation problems always print, even through a monitor that was set to stay quiet.
        verbose = self.monitor.verbose
        self.monitor.verbose = True
        valid = True

        if(self.cli_path is None):
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Validate"
                ,log_subcategory="Path"
                ,log_line="A --path folder is needed: the XML files and the predicted error report go there."
            )
            valid = False
        elif(self.cli_path.exists() and not self.cli_path.is_dir()):
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Validate"
                ,log_subcategory="Path"
                ,log_line=f"--path must be a folder, not a file: {self.cli_path}"
            )
            valid = False
        elif(not self.clients and not (self.cli_path.is_dir() and any(self.cli_path.glob("*.xml")))):
            self.monitor.add_log(
                log_system="WellSkyTEDS"
                ,log_category="Validate"
                ,log_subcategory="Nothing To Do"
                ,log_line=f"No clients were added, and there are no .xml files to check in {self.cli_path}"
            )
            valid = False

        self.monitor.verbose = verbose
        return valid


def main(get_args=False):
    class AppHelpFormatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            WellSkyTEDS.py: build and check WellSky Custom TEDS Import XML for Kansas.

            What this file does:
            1. Gives other Python code Client, Episode and Substance objects to build
               WellSky TEDS records from any source, and writes one
               KDADS_[license]_yyyyMMddHHmm.xml per license.
            2. Predicts the errors WellSky is likely to return, using the WellSky SUD
               Custom TEDS Import Layout v13 (03/10/2026), and writes them to
               wellsky_predicted_errors.csv.
            3. From the command line, checks the WellSky XML files in a folder and
               writes the predicted error report into that same folder.

            Run model:
            - The command line only checks files; it never changes them.
            - Every log line is printed. Log lines hold counts, never client information.
            - The report holds client IDs, so --path must be approved for PHI.
        """),
        epilog=textwrap.dedent("""\
            Examples
            --------
            Check every .xml file in a folder; the report is written there too:
              wellsky-teds --path "C:/TEDS/Out"

            Check and log counts only:
              wellsky-teds --path "C:/TEDS/Out" --dry-run

            Without installing, run the file itself with the same flags:
              python WellSkyTEDS.py --path "C:/TEDS/Out"

            Rules
            -----
            - --path is required, and must be a folder holding .xml files.
            - To build XML, import WellSkyTEDS, Client, Episode and Substance in
              Python; see README.md.
        """),
        formatter_class=AppHelpFormatter
    )

    # Keep each add_argument(...) call on a single line when practical.
    core = parser.add_argument_group("Core Arguments")
    core.add_argument("--path", required=not get_args, type=Path, help="Folder of WellSky XML files to check; the report is written there.")

    behavior = parser.add_argument_group("Behavior")
    behavior.add_argument("--dry-run", action="store_true", default=False, help="Check everything, log counts, and write nothing.")
    if(get_args):
        return parser

    # Parse arguments
    args = parser.parse_args()

    # Create object
    go = WellSkyTEDS(
        path=args.path
        ,dry_run=args.dry_run
    )
    if(not go.validate()):
        parser.print_help()
    else:
        go.execute()

if(__name__ == "__main__"):
    main()
