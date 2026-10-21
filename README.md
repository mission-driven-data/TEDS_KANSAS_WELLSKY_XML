# WellSky TEDS for Kansas

**Build and check WellSky Custom TEDS Import XML for KDADS, in plain Python.**

---

## Overview

### What TEDS is

The Treatment Episode Data Set (TEDS) is SAMHSA's national data system of annual admissions to and discharges from substance use treatment. Its records come from treatment facilities licensed or certified by each state's substance use agency. [SAMHSA: TEDS](https://www.samhsa.gov/data/data-we-collect/teds-treatment-episode-data-set)

### Who reports it in Kansas

In Kansas, the state agency is the Kansas Department for Aging and Disability Services (KDADS). Every Kansas substance use treatment provider that accepts public funding must collect and submit TEDS data. KDADS ties this reporting to the federal funding that supports substance use treatment in Kansas. [KDADS: WellSky Human Services](https://www.kdads.ks.gov/partners-providers/behavioral-health-services-provider-information/wellsky-human-services-kansas-substance-use-reporting-system)

### How Kansas has collected it

| When | System | How providers reported |
|---|---|---|
| Until October 2018 | KCPC (Kansas Client Placement Criteria) | KDADS stopped supporting KCPC and ended its transmission of client records in October 2018. |
| From 2019 | KSURS (Kansas Substance Use Reporting Solution) | Records keyed in online, or bulk-uploaded as three fixed-width files (Client, Admission, Substance) in a state-set format. KSURS was meant as an interim system. |
| From October 2, 2023 | WellSky Human Services | WellSky went into production for KDADS. Providers who key in data moved to WellSky; providers who bulk-uploaded were told to keep using KSURS until further notice. |
| Now | WellSky Custom TEDS Import | Providers upload XML files to a KDADS-hosted SFTP site. WellSky imports them once a day and returns a response file listing any errors. |

Sources: [KDADS: KSURS](https://www.kdads.ks.gov/provider-home/providers/ksurs), [KDADS: WellSky Human Services](https://www.kdads.ks.gov/partners-providers/behavioral-health-services-provider-information/wellsky-human-services-kansas-substance-use-reporting-system), and WellSky's import documents (see [The WellSky import format](#the-wellsky-import-format)).

---

## Why this exists

WellSky's import is strict. Every element has a fixed name, place, format and code list; one client's records must stay together; and the file name must follow an exact pattern. A file that misses any of these comes back with errors, and the records with errors aren't imported.

This project helps Kansas agencies produce XML files that meet WellSky's Custom TEDS Import (bulk upload) requirements, and know before they upload whether they do. It's for anyone who has to make or check those files:

- **Converting historic records** from another system, such as KSURS, into WellSky's format.
- **Filling gaps** an EHR's own export doesn't cover.
- **Checking a file before upload**, whoever made it.

You bring the data, from a database, spreadsheets, an API, flat files or anything else Python can read. Your code passes each client, episode and substance to `WellSkyTEDS.py` as Python objects, and it does the rest:

- **Writes compliant XML.** Every element in WellSky's order, blanks as empty tags, all of a client's records in one `<Client>`, one file per provider license, named the way WellSky requires.
- **Predicts WellSky's errors.** It checks every record against WellSky's published rules and writes a report in WellSky's own error wording, so fixes happen before upload instead of after the response file.
- **Checks existing files.** Point it at any WellSky XML file and it reports the same way.

It needs Python 3.9 or later and uses only Python's standard library. See [Installation](#installation).

> [!IMPORTANT]
> TEDS files and the error report contain client information. Write them only to a location approved for protected health information.

---

## Contents

1. [Overview](#overview)
2. [Why this exists](#why-this-exists)
3. [What's in this folder](#whats-in-this-folder)
4. [Installation](#installation)
5. [Quick start](#quick-start)
6. [The WellSky import format](#the-wellsky-import-format)
7. [How the pieces fit](#how-the-pieces-fit)
8. [Building records](#building-records)
9. [What it fills in for you, and what it never changes](#what-it-fills-in-for-you-and-what-it-never-changes)
10. [Writing the files](#writing-the-files)
11. [Running it from your own script or a .bat file](#running-it-from-your-own-script-or-a-bat-file)
12. [The predicted error report](#the-predicted-error-report)
13. [Checking an existing file](#checking-an-existing-file)
14. [Field reference](#field-reference)
15. [Where the layout and real files disagree](#where-the-layout-and-real-files-disagree)
16. [Limits](#limits)
17. [Running the tests](#running-the-tests)
18. [Sources](#sources)
19. [Disclaimer](#disclaimer)
20. [License](#license)

---

## What's in this folder

| File | What it is |
|---|---|
| `WellSkyTEDS.py` | The whole thing: the objects, the WellSky rules, the error predictor and a small command line. |
| `example_build_records.py` | A runnable example with made-up data, showing both ways of building records. |
| `tests/test_wellsky_teds.py` | Unit tests on made-up records. |
| `pyproject.toml` | What pip needs to install it as the `wellsky-teds` package. |
| `LICENSE` | The MIT License. |
| `README.md` | This guide. |

---

## Installation

It needs Python 3.9 or later. Check with `python --version`. On Windows, if `python` isn't found, try `py` in its place in every command below.

It uses only Python's standard library, so installing it pulls in nothing else.

### Install with pip

Pick whichever source you have. Each one installs the same package, `wellsky-teds`.

**From GitHub**, if Git is installed:

```
python -m pip install "git+https://github.com/mission-driven-data/TEDS_KANSAS_WELLSKY_XML.git"
```

**From GitHub without Git**, using the repository's zip download:

```
python -m pip install "https://github.com/mission-driven-data/TEDS_KANSAS_WELLSKY_XML/archive/refs/heads/main.zip"
```

**From a copy on your machine or a shared drive**, pointing at the folder that holds `pyproject.toml`:

```
python -m pip install "C:\path\to\WellSkyTEDS"
```

To pin a release instead of the latest code, put a tag after the repository address, such as `git+https://github.com/mission-driven-data/TEDS_KANSAS_WELLSKY_XML.git@v0.1.0`.

Running pip as `python -m pip` makes sure the package goes to the same Python that runs your scripts. If you can't install for every user on the machine, add `--user` after `install`.

### What you get

- **The library.** `from WellSkyTEDS import WellSkyTEDS, Client, Episode, Substance` works in any script, from any folder.
- **A command.** `wellsky-teds` checks existing files from any terminal. See [Checking an existing file](#checking-an-existing-file).

Confirm it installed:

```
wellsky-teds --help
```

### Update or remove it

```
python -m pip install --upgrade "git+https://github.com/mission-driven-data/TEDS_KANSAS_WELLSKY_XML.git"
python -m pip uninstall wellsky-teds
```

### Without pip

Copy `WellSkyTEDS.py` into the folder that holds your script. Everything works the same, and the command line becomes `python WellSkyTEDS.py` instead of `wellsky-teds`. This suits machines where installing packages isn't allowed.

### For running the tests

The tests need [`pytest`](https://pypi.org/project/pytest/), and coverage reports need [`pytest-cov`](https://pypi.org/project/pytest-cov/). Add `[test]` to any of the installs above to get both:

```
python -m pip install "C:\path\to\WellSkyTEDS[test]"
```

> [!TIP]
> To keep the package apart from the rest of your machine, install it into a virtual environment:
>
> ```
> python -m venv .venv
> .venv\Scripts\activate          (Windows)
> source .venv/bin/activate       (macOS or Linux)
> python -m pip install "git+https://github.com/mission-driven-data/TEDS_KANSAS_WELLSKY_XML.git"
> ```
>
> Activate the environment again in each new terminal, or point your `.bat` file at `.venv\Scripts\python.exe`.

---

## Quick start

Once it's [installed](#installation), a script this short builds a file and its report:

```python
from WellSkyTEDS import WellSkyTEDS

teds = WellSkyTEDS(path=r"C:\TEDS\Out")          # where the XML and the report go

teds.add_record(
    client={"source_id": "80000001", "last_name": "Demo", "first_name": "Robin",
            "dob": "09231998", "sex": "1", "race": "05", "hispanic_origin": "05",
            "gender_identity": "1", "sexual_orientation": "01", "county": "Reno"},
    episodes=[{
        "license": "00987654", "admit_date": "04082024", "treatment_setting": "07",
        "client_type": "2", "referral_source": "01",
        # ...the rest of the admission answers...
        "substances": [{"rank": "P", "substance": "02", "detailed_drug_code": "0201",
                        "route": "01", "frequency": "05", "age_first_use": "15"}],
        "discharge": {"discharge_date": "05202024", "discharge_reason": "01"},
    }],
)

summary = teds.execute()        # checks everything, writes the XML and the report
print(summary["errors"], "predicted errors")
```

The run leaves this in `C:\TEDS\Out`:

```
KDADS_00987654_202609140815.xml     one file per license
wellsky_predicted_errors.csv        one row per predicted problem
```

For a complete working version, run `python example_build_records.py`.

---

## The WellSky import format

This section summarizes what WellSky requires of an import file and what it does with one. Everything here comes from the documents below. Where they disagree with each other, or with real files, that's noted in [Where the layout and real files disagree](#where-the-layout-and-real-files-disagree).

### The documents

| Document | Version | What it covers |
|---|---|---|
| **WellSky SUD Custom TEDS Import Layout** (spreadsheet) | v13, 03/10/2026 | Every element: its name, parent, data type, maximum length, whether it's required on an admission, a discharge and for a collateral client, its validation notes, valid codes, and the TEDS item it maps to. Also the Detailed Drug Code Map and the revision history. This is the main rule book, and the table in `WellSkyRules` is built from it. |
| **Custom TEDS Import Interface Specifications, KS KDADS** | v2, 05/15/2024 | How WellSky processes a file: how it matches clients, enrollments and assessments, what the response file holds, and the full error list. |
| **TEDS Import into WellSky: Instructions for Providers** | 03/16/2026 | The provider's side: SFTP folders, email summaries, the file name, how to structure the file, common errors, resubmitting, and the field mapping. |
| **A working WellSky export** on test clients | 10/20/2026 | One real import file made by an EHR's own WellSky export. It isn't included here. This tool reads it back and rebuilds it exactly, element for element; the shape described below matches it. |

The three WellSky documents aren't posted publicly. WellSky and KDADS distribute them to Kansas providers; see [Sources](#sources) for who to ask.

### Getting files to WellSky

- **Transport.** Each provider gets a login to an SFTP site hosted by KDADS, with its own folder. Import files go in `ProviderDrop`; WellSky's response files come back in `WellSkyDrop`.
- **Timing.** WellSky processes uploaded files once a day.
- **Email summaries.** To be emailed when a file is processed, put a text file with one email address per line in the provider's root folder. The instructions call it `ResponseDistribution.txt` in the text and `DistributionResponse.txt` in their folder diagram.
- **File name.** `KDADS_[Provider License Number]_yyyyMMddHHmm.xml`, for example `KDADS_0012345_202507170832.xml`. Nothing else may be added to the name.
- **Format.** XML. Elements WellSky doesn't expect are ignored. A file that isn't readable XML is rejected whole, as *File not valid*.

### The structure

```
KSTeds                       StateCode (KS), ReportingDate (the day the file is made)
└── Client                   one per client: who the person is
    ├── Admission            any number per client
    │   └── TreatmentEvent   exactly one: the admission's answers
    └── Discharge            any number per client
        └── TreatmentEvent   exactly one: the discharge's answers
```

- A file may hold many clients, each in its own `<Client>`.
- **All of one client's records in a file must sit in the same `<Client>`.** If an admission and its discharge are in separate `<Client>` elements, WellSky can't link them and rejects the discharge.
- A discharge must carry the same episode `SourceID` as its admission. That's how WellSky links the two.

### Element rules

- **Order.** Elements follow the layout's order. The [Field reference](#field-reference) lists them.
- **Requirement flags.** Each element is marked for admissions and for discharges: **Y** required, **C** required in stated conditions, **O** optional, or **N** not sent on that record type. A separate column marks what's required when `ClientType` is 1 (codependent or collateral); for those clients, everything else is optional.
- **Dates** are `MMDDYYYY`.
- **Codes** come from the layout's lists and must include leading zeros: `05`, not `5`. Yes/No questions use 1 for Yes and 2 for No.
- **Unanswered questions** use the layout's "not answered" code where it has one, such as 97 for Unknown or 96 for Not applicable. 96 is allowed only where the layout says, for example on route, frequency and age of first use only when the substance is 01 (None).
- **Lengths and formats.** Text has a maximum length; Phone is 10 digits; SSN is `###-##-####`; `TypeOfTobacco` takes several codes joined by `|`; `SUDiagnosis` is an ICD-10 code, or `999.9997` for unknown.

### What WellSky does with a file

| In the file | Becomes in WellSky | How WellSky matches it to what it already has |
|---|---|---|
| `<Client>` | A consumer | ProviderID plus the client `SourceID`. Failing that, the same last name, first name, birth date and sex. Otherwise it creates a new consumer. |
| `<Admission>` / `<Discharge>` | An enrollment | ProviderID plus the episode `SourceID`. Failing that, an enrollment with no SourceID and the same admission date. A discharge with no matching enrollment is rejected as *No Admission matching this Discharge found*. |
| `<TreatmentEvent>` | An assessment: the TEDS admission form, or the discharge summary | ProviderID plus SourceID, or a blank SourceID and the same date. Each element inside is one question on the form. |

WellSky matches `ProviderID` to its own provider (vendor) number. A ProviderID it doesn't know is rejected as *Provider ID not found*.

Records with a missing required value or an invalid code aren't imported. One bad record doesn't stop the others. **Resubmitting is safe:** sending a whole file again doesn't create duplicates, it updates whatever changed, and fixed records are then created.

### The response file

For each file processed, WellSky writes `[ProcessedFileName]_Response_YYYYMMDD_HHMMSS.csv` to the provider's `WellSkyDrop` folder. Each row has the input file name, client SourceID, Admission or Discharge, ProviderID, field name and error. The errors are:

| Error | Applies to |
|---|---|
| Provider ID not found | ProviderID |
| No Admission matching this Discharge found | Discharges (reported under DateOfAdmission) |
| Required field not populated | Any required element |
| Invalid value | A code not in the list, or an invalid date |
| Invalid format | For example, letters where only numbers belong |
| Value not applicable unless Client Type = Codependent/Collateral (1) | TreatmentSetting, ReasonForDischarge |
| Value not applicable unless Substance is None (01) | Route, frequency and age of first use, for each substance |
| Duplicate Substance Codes not allowed unless Detailed Drug Codes are different | SecondarySubstance, TertiarySubstance |
| Value not applicable to selected Substance | The detailed drug codes |
| Not a valid ICD-10 Diagnosis Code | SUDiagnosis |
| File not valid | The whole file, when it isn't readable XML |

The predicted error report uses these same words, so the two line up.

### An example

Real files are one long line. Here is a file this tool wrote from made-up data, indented for reading, with the middle of each `<TreatmentEvent>` shortened (`...`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<KSTeds>
  <StateCode>KS</StateCode>
  <ReportingDate>09142026</ReportingDate>
  <Client>
    <SourceID>80000001</SourceID>
    <LastName>Demo</LastName>
    <FirstName>Robin</FirstName>
    <MiddleName />
    <AKA />
    <DOB>09231998</DOB>
    <Sex>1</Sex>
    <Race>05</Race>
    <HispanicOrigin>05</HispanicOrigin>
    <GenderIdentity>1</GenderIdentity>
    <SexualOrientation>01</SexualOrientation>
    <Phone />
    <Street />
    <State>Kansas</State>
    <CountyofResidence>Reno</CountyofResidence>
    <DepartmentOfCorrectionsNum />
    <MedicaidNumber />
    <SSN />
    <ASO />
    <Admission>
      <ProviderID>00987654</ProviderID>
      <SourceID>07009876548000000104082024</SourceID>
      <EnrollType>Outpatient</EnrollType>
      <DateOfAdmission>04082024</DateOfAdmission>
      <ClientTransactionType>A</ClientTransactionType>
      <ClientType>2</ClientType>
      <ReferralSource>01</ReferralSource>
      <CriminalJusticeReferral>96</CriminalJusticeReferral>
      <TreatmentSetting>07</TreatmentSetting>
      <TreatmentEvent>
        <SourceID>07009876548000000104082024</SourceID>
        <HighestLevelOfEducation>12</HighestLevelOfEducation>
        <EmploymentStatus>01</EmploymentStatus>
        ...
        <PrimarySubstance>02</PrimarySubstance>
        <PrimaryDetailedDrugCode>0201</PrimaryDetailedDrugCode>
        <PrimaryRouteOfAdministration>01</PrimaryRouteOfAdministration>
        <PrimaryFrequency>05</PrimaryFrequency>
        <PrimaryAgeOfFirstUse>15</PrimaryAgeOfFirstUse>
        ...
        <SUDiagnosis>F10.20</SUDiagnosis>
      </TreatmentEvent>
    </Admission>
    <Discharge>
      <ProviderID>00987654</ProviderID>
      <SourceID>07009876548000000104082024</SourceID>
      <EnrollType>Outpatient</EnrollType>
      <DateOfAdmission>04082024</DateOfAdmission>
      <ClientTransactionType>D</ClientTransactionType>
      <ClientType>2</ClientType>
      <TreatmentSetting>07</TreatmentSetting>
      <DateOfLastContact>05172024</DateOfLastContact>
      <DateOFDischarge>05202024</DateOFDischarge>
      <ReasonForDischarge>01</ReasonForDischarge>
      <TreatmentEvent>
        <SourceID>07009876548000000104082024</SourceID>
        <EmploymentStatus>01</EmploymentStatus>
        <NotInLaborForce>96</NotInLaborForce>
        <LivingArrangement>03</LivingArrangement>
        <ArrestsInPast30Days>00</ArrestsInPast30Days>
        <SelfHelpGroupInPast30Days>02</SelfHelpGroupInPast30Days>
        <PrimarySubstance>02</PrimarySubstance>
        <PrimaryFrequency>01</PrimaryFrequency>
        ...
      </TreatmentEvent>
    </Discharge>
  </Client>
</KSTeds>
```

Note what the example shows:

- The admission and its discharge sit in the same `<Client>` and share the episode `SourceID`.
- The discharge repeats only the episode's identifying elements and adds its own; questions asked only at admission, such as ReferralSource, aren't sent on it.
- Blank optional elements are written as empty tags, such as `<AKA />`.

---

## How the pieces fit

WellSky's file nests like this, and the objects follow the same shape:

```
KSTeds                                    one file per license
└── Client                                ← Client
    ├── Admission                         ← Episode
    │   └── TreatmentEvent                ← Episode answers + Substances (admission values)
    └── Discharge  (when discharged)      ← Episode.set_discharge(...)
        └── TreatmentEvent                ← discharge answers + Substances (discharge values)
```

| Object | Holds | You create it with |
|---|---|---|
| `Client` | One person: name, birth date, demographics, county. | `Client(source_id=..., ...)` |
| `Episode` | One admission, and later its discharge. **It carries the provider license**, which WellSky uses as ProviderID and in the file name. | `Episode(license=..., admit_date=..., ...)` |
| `Substance` | One ranked substance (P, S or T), with its admission values and its discharge values. | `Substance(rank="P", substance=..., ...)` |
| `WellSkyTEDS` | The run: every client, the checks, and the files. | `WellSkyTEDS(path=...)` |

Two more classes do the work behind these: `WellSkyRules` holds the layout, and `WellSkyPredictor` builds the error report. You won't usually need them directly.

---

## Building records

There are two ways to build records, and they produce exactly the same XML. Use whichever fits your data, or mix them in one run.

### Way 1: a whole client at once

`add_record()` takes plain dicts. The keys are the same parameter names the classes use (see the [Field reference](#field-reference)). Each episode can carry a `substances` list and a `discharge` dict.

```python
teds.add_record(
    client={"source_id": "80000001", "last_name": "Demo", ...},
    episodes=[
        {"license": "00987654", "admit_date": "04082024", ...,
         "substances": [{"rank": "P", ...}, {"rank": "S", ...}],
         "discharge": {"discharge_date": "05202024", "discharge_reason": "01", ...}},
        {"license": "00923456", "admit_date": "06012024", ...},      # still open: no discharge
    ],
)
```

This suits data that already sits in rows or dicts, one client at a time. A misspelled key stops the run with Python's own error, so a typo can't slip through as a blank.

### Way 2: one object at a time

Build each object, then attach them. This suits data that arrives in pieces: clients from one table or file, admissions from another, substances from a third.

```python
from WellSkyTEDS import Client, Episode, Substance, WellSkyTEDS

client = Client(source_id="90000002", last_name="Sample", first_name="Lee", dob="07141985",
                sex="2", race="04", hispanic_origin="05", gender_identity="2",
                sexual_orientation="98", county="Sedgwick")

episode = Episode(license="00934567", admit_date="06032024", treatment_setting="06", ...)
episode.add_substance(Substance(rank="P", substance="10", detailed_drug_code="1001",
                                route="04", frequency="03", age_first_use="19"))
client.add_episode(episode)

teds.add_client(client)
```

Every object can check itself at any point, before or after it's attached:

```python
for issue in episode.predict_errors():
    print(issue["severity"], issue["element"], issue["message"])

episode.validate()      # True when there's no predicted Error
```

Some rules depend on more than one object. For example, PregnantAtAdmission is required when the client's Sex is 2. Those rules run once the objects are attached.

### Discharges

Call `set_discharge()` on the episode. Each substance's discharge values go on its `Substance`:

```python
episode.set_discharge(discharge_date="05202024", discharge_reason="01",
                      last_contact_date="05172024", employment_status="01",
                      living_arrangement="03", arrests="00", self_help="02")

primary = Substance(rank="P", substance="02", ..., discharge_substance="02", discharge_frequency="01")
```

A discharge can also report a substance in a slot that was blank or unknown at admission. Give that rank a `Substance` with only its discharge values:

```python
episode.add_substance(Substance(rank="S", discharge_substance="01", discharge_frequency="96"))
```

### Values

- **Pass codes as strings, exactly as WellSky lists them**: `"05"`, not `5`. Numbers are accepted, but `5` is sent as `5`, and WellSky's Race code is `05`. The report catches this and suggests the right code.
- **Dates can be `MMDDYYYY` text or Python `date` objects.** They're written as `MMDDYYYY`.
- **`None` and `""` both mean blank.** A blank element is written as an empty tag.

---

## What it fills in for you, and what it never changes

These defaults follow the layout, or what working WellSky exports do. Pass a value yourself to override any of them.

| Element | When you don't supply it | Why |
|---|---|---|
| `ProviderID` | The episode's `license`, exactly as given. Pass `provider_id` to send something else. | Working exports send the license here. WellSky matches ProviderID to its own provider number, so if WellSky knows the provider by another number, pass that as `provider_id`; the license still names the file. |
| Episode `SourceID` | TreatmentSetting + license + client SourceID + admission date, e.g. `07` `00987654` `80000001` `04082024`. | The pattern working exports use. When your historic records use it too, discharges your EHR sends later can link to them. |
| TreatmentEvent `SourceID` | The episode's SourceID. The discharge uses the same one as the admission. | Working exports reuse the admission's event ID on the discharge. |
| `EnrollType` | `Inpatient` for treatment settings 01 to 05, otherwise `Outpatient`. | Settings 01 to 05 are 24-hour or residential care. The layout's not-answered value is Outpatient. |
| `ClientTransactionType` | `A` on the Admission, `D` on the Discharge. | The layout: A and T for admissions, D for discharges. |
| `DateOfLastContact` | The discharge date. | The layout's own value when last contact isn't answered. |
| Discharge `TreatmentSetting`, `ClientType`, `EnrollType`, `DateOfAdmission` | The admission's values. | They describe the same episode. |
| `StateCode`, `ReportingDate` | `KS` and the day the file is made. | Fixed by the layout. |

**It never changes a code or a license you give it.** It doesn't pad, translate or guess. Pass the license exactly as KDADS issued it, leading zeros included. Turning your source's codes into WellSky's codes is your code's job. This file reports any value WellSky won't accept, so you can fix it at the source.

> [!TIP]
> Use the same client SourceID your EHR sends WellSky for that person. Then historic records and current ones belong to the same client in WellSky.

---

## Writing the files

`teds.execute()` runs the checks and writes everything. It returns a summary of counts, with no client information:

```python
{"clients": 2, "episodes": 2, "admissions": 2, "discharges": 1,
 "episodes_with_errors": 0, "errors": 0, "warnings": 0,
 "by_error": {...}, "by_element": {...},
 "files": ["KDADS_00987654_202609140815.xml", "KDADS_00934567_202609140815.xml"]}
```

**Shape.** The files follow [the WellSky import format](#the-wellsky-import-format):

- one file per license, named `KDADS_[license]_yyyyMMddHHmm.xml`
- the whole document on one line, after `<?xml version="1.0" encoding="UTF-8"?>`
- every element the layout lists for that record type, in layout order, with blanks as empty tags such as `<AKA />`
- one `<Client>` per client in each file, holding every episode for that license: each `<Admission>` and, when discharged, its `<Discharge>`, in the order you added them

**Options on `WellSkyTEDS(...)`:**

| Option | Default | What it does |
|---|---|---|
| `path` | none | The folder for the run: the XML files and the report are written here. Created if it doesn't exist. Required. |
| `exclude_errors` | `False` | When `True`, leaves out of the XML every episode with a predicted Error. By default everything is written, and the report says what is likely to be rejected. |
| `dry_run` | `False` | Builds and checks everything, logs the counts, and writes nothing. |
| `now` | current time | The time used for `ReportingDate` and the file names. |
| `monitor` | none | A hook for plugging in your own logger: any object with an `add_log(log_system, log_category, log_subcategory, log_line)` method. You can ignore it. |

Every log line is printed. Log lines carry counts and file names only, never client information.

You can also run the steps yourself: `teds.predict_errors()` returns the list of predicted problems, and `teds.build_files()` returns `{file name: XML text}` without writing anything.

---

## Running it from your own script or a .bat file

`WellSkyTEDS` is a library. Your script imports it, reads your data, and passes it in. In outline:

```python
from WellSkyTEDS import Client, Episode, Substance, WellSkyTEDS

teds = WellSkyTEDS(path=r"C:\TEDS\Out")

for person in read_clients():                   # your code: read clients from your source
    client = Client(source_id=person.client_id, last_name=person.last, ...)
    for stay in read_admissions(person):        # your code: that client's admissions
        episode = client.add_episode(Episode(license=stay.license, admit_date=stay.admitted, ...))
        for use in read_substances(stay):       # your code: that admission's substances
            episode.add_substance(Substance(rank=use.rank, substance=use.code, ...))
        if stay.discharged:
            episode.set_discharge(discharge_date=stay.discharged, discharge_reason=stay.reason, ...)
    teds.add_client(client)

summary = teds.execute()                        # one report for everything added
```

One `WellSkyTEDS` collects every client you add. `execute()` checks them all together and writes one report for the whole run, plus one XML file per license. To check a run without writing anything, pass `dry_run=True`.

To schedule it or hand it to someone, a `.bat` file runs your script like any other Python:

```bat
@echo off
cd /d "C:\TEDS\Scripts"
python build_wellsky_teds.py
```

---

## The predicted error report

WellSky checks every file it receives and sends back its errors. This report predicts that response before you upload, so the fixes can happen first.

> [!NOTE]
> It's a prediction, not a guarantee. It knows the published layout and what real files have shown since. It can't know WellSky's provider list or any rule WellSky hasn't published. When WellSky's actual response differs, that's worth adding as a new rule.

### How it works

The checks run in three layers, each building on the one before:

```
1. Each value on its own       → Is it a WellSky code? The right format? Too long?
        │                          Blank when the layout says Required?
        ▼
2. Each object with its links  → Rules that need two values together:
        │                          ReferralSource 07 needs a CriminalJusticeReferral,
        │                          Sex 2 needs PregnantAtAdmission, substance 01 goes with 96,
        │                          a detailed drug code must belong to its substance,
        │                          the client's age decides EmploymentStatus 96 ...
        ▼
3. The whole file              → An episode sent twice, a TreatmentEvent ID reused,
                                   one client ID with two different birth dates,
                                   a license WellSky may not know
```

Each problem becomes one row in `wellsky_predicted_errors.csv`, Errors first, then Warnings.

### Reading a row

| Column | What it means |
|---|---|
| **Severity** | `Error`: WellSky's published rules say it will be rejected. `Warning`: it might be, or WellSky might change the value. Worth a look. |
| **Error** | WellSky's own wording from its error list, such as *Required field not populated* or *Invalid value*, so the report reads like WellSky's response. Problems WellSky's list doesn't name are labelled *Data integrity* or *Likely KDADS edit*. |
| **Element** | The XML element, such as `CountyofResidence`. |
| **Value** | What was sent. It's left blank for elements that identify the person: names, birth date, phone, street, SSN and ID numbers. |
| **Message** | What's wrong, in plain words, and what WellSky expects. |
| **Source** | Where the rule comes from (see below). |
| **Record Type** | `Client`, `Admission`, `Discharge`, `Episode` or `File`. |
| **License**, **Client Source ID**, **Episode Source ID** | Which record to fix. |

### Where the rules come from

| Source | What it is | Severity |
|---|---|---|
| **WellSky layout v13** | The WellSky SUD Custom TEDS Import Layout v13: required elements, code lists, formats, the Detailed Drug Code Map, the conditional rules. | Error (a few layout notes that only advise are Warnings) |
| **WellSky provider instructions** | WellSky's TEDS Import Instructions for Providers (03/16/2026): leading zeros must be included, all of a client's records in one `<Client>`, nothing but the license in the file name, questions not to answer. | Error, or Warning where the instruction only advises |
| **Data integrity** | The data contradicts itself: a discharge dated before its admission, an admission before the birth date, the same episode twice. | Error (Warning where only a person can judge) |
| **MDD reading of layout v13** | Mission Driven Data's reading of places where the layout is unclear, or where working exports do something else, so it isn't yet clear which way WellSky goes. Example: repeated 97 (Unknown) substances, which working exports send routinely. | Warning |
| **KDADS KSURS-era edit** | Checks KDADS ran on uploads to KSURS, its earlier TEDS system: age of first use greater than the client's age, dates in the future, last contact outside the episode. WellSky may or may not run them. | Warning |

### Every check

<details>
<summary><b>Values (layer 1)</b></summary>

| Check | Error |
|---|---|
| A required element is blank. Collateral clients (`ClientType` 1) need only the elements the layout marks for them. | Required field not populated |
| A code isn't in WellSky's list. When padding would fix it (`5` → `05`), the message says so. | Invalid value |
| A date isn't a real `MMDDYYYY` date. | Invalid format |
| A value is longer than the layout allows. | Invalid format |
| Not a number where one is needed, or a number out of range: PeopleInHousehold 1–10, DaysWaiting 0–995 or 997, ArrestsInPast30Days 0–96 or 97, AgeOfFirstUse 0–95 or 96/97. | Invalid format / Invalid value |
| A number without its leading zeros, such as `3` for `ArrestsInPast30Days` (`03`). The provider instructions say leading zeros must be included. | Invalid format |
| Phone isn't 10 digits, or SSN isn't `###-##-####`. | Invalid format |
| `TypeOfTobacco` parts aren't all valid codes separated by `\|`. | Invalid value |
| A detailed drug code isn't in the Detailed Drug Code Map. | Invalid value |
| `SUDiagnosis` isn't an ICD-10 code like `F10.20`, or `999.9997` for unknown. | Not a valid ICD-10 Diagnosis Code |
| `State` isn't a US state name, or `CountyofResidence` isn't a Kansas county. Case doesn't matter, so `KANSAS` passes. | Invalid value |

</details>

<details>
<summary><b>Rules between values (layer 2)</b></summary>

| Check | Severity | Error |
|---|---|---|
| ReferralSource 07 with no CriminalJusticeReferral, or with 96. | Error | Required field not populated / Invalid value |
| CriminalJusticeReferral other than blank or 96 when ReferralSource isn't 07. | Warning | Invalid value |
| EmploymentStatus 04 with no NotInLaborForce, or with 96 (admission and discharge). | Error | Required field not populated / Invalid value |
| NotInLaborForce other than blank or 96 when EmploymentStatus isn't 04. | Warning | Invalid value |
| The client's Sex is 2 and PregnantAtAdmission is blank. | Error | Required field not populated |
| PrenatalCare answered when PregnantAtAdmission isn't 1. | Warning | Invalid value |
| TobaccoUse 1 needs TypeOfTobacco and Tobacco30. TBPositive 2 needs TBRisk and TBSymptoms. PrevSUDTx 1 needs PrevSUDTxEp and MHTxEp. | Error | Required field not populated |
| TypeOfTobacco or Tobacco30 answered when TobaccoUse is 2. The provider instructions say not to answer them then. | Warning | Invalid value |
| TreatmentSetting 96 when ClientType isn't 1. | Error | Value not applicable unless Client Type = Codependent/Collateral (1) |
| EmploymentStatus 96 for a client 16 or older. | Error | Invalid value |
| EmploymentStatus other than 96 for a client under 16. WellSky replaces it with 96 (layout revision 13). | Warning | Invalid value |
| A reported substance missing its detailed drug code, route, frequency or age of first use. At discharge, a substance without a frequency, or a frequency without a substance. | Error | Required field not populated |
| Route, frequency or age of first use is 96 when the substance isn't 01, or isn't 96 when it is. | Error | Value not applicable unless Substance is None (01) |
| A detailed drug code that belongs to a different substance, such as 0401 under substance 02. | Error | Value not applicable to selected Substance |
| The same substance and detailed drug code in two slots. 01 may repeat. A repeated 97, or a repeat at discharge (which carries no drug codes), is a Warning. | Error / Warning | Duplicate Substance Codes not allowed unless Detailed Drug Codes are different |
| No Primary substance. Not required for collateral clients. | Error | Required field not populated |
| An Admission with a ClientTransactionType other than A or T, or a Discharge with one other than D. | Error | Invalid value |
| Two substances with the same rank (only the last is written), or a rank that isn't P, S or T. | Error | Data integrity |
| The discharge dated before the admission, an admission before the birth date, or a birth date in the future. | Error | Data integrity |
| Age of first use greater than the client's age at admission. | Warning | Likely KDADS edit |
| An admission or discharge date in the future, or a last contact after the discharge, before the admission, or before 01/01/2000. | Warning | Likely KDADS edit |
| A discharge with no admission in the file (when checking a file). WellSky accepts it only if the admission was sent before. | Warning | No Admission matching this Discharge found |
| An episode not attached to a client. | Error | Data integrity |

</details>

<details>
<summary><b>The whole file (layer 3)</b></summary>

| Check | Severity | Error |
|---|---|---|
| The same episode (license and SourceID) appears more than once. | Error | Data integrity |
| One TreatmentEvent SourceID is used by more than one episode. The layout says it shouldn't repeat. | Warning | Data integrity |
| One client SourceID appears with different names, birth dates or sex. | Warning | Data integrity |
| One client split across more than one `<Client>` element for the same license. WellSky may not link a discharge to its admission. | Warning | Data integrity |
| A license with anything but letters and digits. It names the file, and nothing else may go in the file name. Whether WellSky knows the license, only WellSky can say. | Error | Provider ID not found |
| A client with no episodes, so nothing is written for them. | Warning | Data integrity |

</details>

### What the log shows

The log, and the summary `execute()` returns, carry counts only:

```
WellSkyPredictor | Log Summary | Totals   | 4 client(s), 4 episode(s), 4 admission(s), 1 discharge(s); 27 predicted error(s) and 15 warning(s); 4 episode(s) with at least one error.
WellSkyPredictor | Log Summary | By Error | 21 x Error: Required field not populated
WellSkyPredictor | Log Summary | By Error | 6 x Error: Invalid value
...
```

---

## Checking an existing file

From the command line, it checks WellSky XML that already exists: an EHR's export, your own output, or both. Put the files in one folder and point `--path` at it. It checks every `.xml` file there and writes `wellsky_predicted_errors.csv` into the same folder. It only reads the XML files; it never changes them.

```
wellsky-teds --path "C:\TEDS\Out"
wellsky-teds --path "C:\TEDS\Out" --dry-run
```

If you copied the file instead of installing it, run `python WellSkyTEDS.py` with the same flags.

| Flag | What it does |
|---|---|
| `--path` | The folder of `.xml` files to check. The report is written there too. Required. |
| `--dry-run` | Check and log counts; write nothing. |

Every log line is always printed. They hold counts and file names, never client information. To keep them, redirect the output: `wellsky-teds --path "C:\TEDS\Out" > check.log`.

In Python, the same check is `WellSkyTEDS(path=...).execute()` with no clients added.

---

## Field reference

Every parameter, the WellSky element it fills, and whether the layout requires it. *Conditional* means required only in the cases listed under [Every check](#every-check). A dash (—) means the element isn't sent on that record type.

<details open>
<summary><b>Client</b>: <code>Client(...)</code></summary>

| Parameter | Element | Admission | Discharge | Values |
|---|---|---|---|---|
| `source_id` | `SourceID` | Required | Required | Text, up to 50 |
| `last_name` | `LastName` | Required | Required | Text, up to 30 |
| `first_name` | `FirstName` | Required | Required | Text, up to 30 |
| `dob` | `DOB` | Required | Required | MMDDYYYY |
| `sex` | `Sex` | Required | Required | 1, 2, 7 |
| `race` | `Race` | Required | Required | 01, 02, 04, 05, 13, 20, 21, 23, 97 |
| `hispanic_origin` | `HispanicOrigin` | Required | Required | 01, 02, 03, 04, 05, 06, 97 |
| `gender_identity` | `GenderIdentity` | Required | Required | 1, 2, 3, 4, 7, 8 |
| `sexual_orientation` | `SexualOrientation` | Required | Required | 01, 02, 03, 04, 05, 06, 07, 09, 98 |
| `county` | `CountyofResidence` | Required | Required | Kansas county name |
| `middle_name` | `MiddleName` | Optional | Optional | Text, up to 30 |
| `aka` | `AKA` | Optional | Optional | Text, up to 100 |
| `phone` | `Phone` | Optional | Optional | 10 digits |
| `street` | `Street` | Optional | Optional | Text, up to 100 |
| `state` | `State` | Optional | Optional | US state name |
| `corrections_number` | `DepartmentOfCorrectionsNum` | Optional | Optional | Text, up to 100 |
| `medicaid_number` | `MedicaidNumber` | Optional | Optional | Text, up to 100 |
| `ssn` | `SSN` | Optional | Optional | ###-##-#### |
| `aso` | `ASO` | Optional | Optional | Text, up to 100 |

</details>

<details>
<summary><b>Episode (the admission)</b>: <code>Episode(...)</code></summary>

| Parameter | Element | Admission | Values |
|---|---|---|---|
| `license` | `ProviderID`, and the file name | Required | The location's provider license, exactly as issued |
| `admit_date` | `DateOfAdmission` | Required | MMDDYYYY |
| `treatment_setting` | `TreatmentSetting` | Required | 01, 02, 03, 04, 05, 06, 07, 08, 96 |
| `client_type` | `ClientType` | Required | 1, 2 |
| `referral_source` | `ReferralSource` | Required | 01, 02, 03, 04, 05, 06, 07, 97 |
| `criminal_justice_referral` | `CriminalJusticeReferral` | Conditional | 01, 02, 03, 04, 05, 06, 07, 08, 96, 97 |
| `enroll_type` | `EnrollType` | Required (filled in) | Inpatient, Outpatient |
| `source_id` | `SourceID` (Admission/Discharge) | Required (filled in) | Text, up to 100 |
| `event_source_id` | `SourceID` (TreatmentEvent) | Required (filled in) | Text, up to 100 |
| `education` | `HighestLevelOfEducation` | Required | 00–19, 70, 71, 97 |
| `employment_status` | `EmploymentStatus` | Required | 01, 02, 03, 04, 96, 97 |
| `not_in_labor_force` | `NotInLaborForce` | Conditional | 01, 02, 03, 04, 05, 06, 96, 97 |
| `pregnant` | `PregnantAtAdmission` | Conditional | 1, 2, 6, 7 |
| `prenatal_care` | `PrenatalCare` | Optional | 1, 2 |
| `veteran_status` | `VeteranStatus` | Required | 1, 2, 7 |
| `living_arrangement` | `LivingArrangement` | Required | 01, 02, 03, 97 |
| `yearly_income` | `YearlyIncome` | Required | Digits |
| `federal_poverty_level` | `FederalPovertyLevel` | Required | 1, 2, 6 |
| `people_in_household` | `PeopleInHousehold` | Required | 1 to 10 |
| `children_in_home` | `ChildrenInHome` | Required | 1, 2 |
| `children_at_risk` | `ChildrenInHomeAtRisk` | Required | 00–10 |
| `dcf_custody` | `DCFCustody` | Optional | 1, 2, 9 |
| `income_source` | `SourcesOfIncome` | Required | 01, 02, 03, 04, 20, 21, 97 |
| `health_insurance` | `HealthInsurance` | Optional | 01, 02, 03, 04, 06, 20, 21, 97 |
| `payment_source` | `PrimaryPaymentSource` | Required | 01–09, 97 |
| `senate_bill_6` | `SenateBill6Secondary` | Optional | 0, 1 |
| `gambling_fund_member_type` | `GamblingFundMemberType` | Optional | 01, 02, 03 |
| `gpra` | `GPRA` | Optional | 0, 1 |
| `marital_status` | `MaritalStatus` | Optional | 01, 02, 03, 04, 05, 97 |
| `days_waiting` | `DaysWaiting` | Optional | 0 to 995, or 997 |
| `arrests` | `ArrestsInPast30Days` | Required | 0 to 96, or 97 |
| `self_help` | `SelfHelpGroupInPast30Days` | Required | 01, 02, 03, 04, 05, 06, 97 |
| `gambling_withdrawal` | `GamblingWithdrawal` | Required | 1, 2 |
| `gambling_hidden` | `GamblingHidden` | Required | 1, 2 |
| `gambling_financial_trouble` | `GamblingFinancialTrouble` | Required | 1, 2 |
| `tobacco_use` | `TobaccoUse` | Required | 1, 2 |
| `tobacco_type` | `TypeOfTobacco` | Conditional | 01, 02, 03, joined by `\|` |
| `tobacco_30_days` | `Tobacco30` | Conditional | 1, 2 |
| `tb_positive` | `TBPositive` | Required | 1, 2 |
| `tb_risk` | `TBRisk` | Conditional | 1, 2 |
| `tb_symptoms` | `TBSymptoms` | Conditional | 1, 2 |
| `tb_education` | `TBEducation` | Required | 1, 2 |
| `tb_case_management` | `TBCaseMgm` | Required | 1, 2 |
| `hiv` | `HIV` | Required | 1, 2, 9 |
| `mh_treatment` | `MHTx` | Required | 1, 2 |
| `co_occurring` | `Co-OccurringMHSU` | Required | 1, 2, 7 |
| `psych_medication` | `PsyMed` | Required | 1, 2 |
| `su_history` | `SUHistory` | Required | 1, 2 |
| `mh_history` | `MHHistory` | Required | 1, 2 |
| `prior_sud_treatment` | `PrevSUDTx` | Required | 1, 2 |
| `prior_sud_episodes` | `PrevSUDTxEp` | Conditional | 0, 1, 2, 3, 4, 5, 7 |
| `mh_treatment_episodes` | `MHTxEp` | Conditional | 00–10 |
| `moud` | `MOUD` | Required | 1, 2, 6, 7 |
| `diagnosis` | `SUDiagnosis` | Required | ICD-10 such as F10.20, or 999.9997 |
| `provider_id` | `ProviderID` | Optional (defaults to `license`) | WellSky's number for the provider, when it isn't the license |

</details>

<details>
<summary><b>Discharge</b>: <code>episode.set_discharge(...)</code></summary>

| Parameter | Element | Discharge | Values |
|---|---|---|---|
| `discharge_date` | `DateOFDischarge` | Required | MMDDYYYY |
| `discharge_reason` | `ReasonForDischarge` | Required | 01, 02, 03, 04, 05, 06, 07, 14, 24 |
| `last_contact_date` | `DateOfLastContact` | Required (filled in) | MMDDYYYY |
| `treatment_setting` | `TreatmentSetting` | Required (filled in) | 01–08, 96 |
| `employment_status` | `EmploymentStatus` | Required | 01, 02, 03, 04, 96, 97 |
| `not_in_labor_force` | `NotInLaborForce` | Conditional | 01, 02, 03, 04, 05, 06, 96, 97 |
| `living_arrangement` | `LivingArrangement` | Required | 01, 02, 03, 97 |
| `arrests` | `ArrestsInPast30Days` | Required | 0 to 96, or 97 |
| `self_help` | `SelfHelpGroupInPast30Days` | Required | 01, 02, 03, 04, 05, 06, 97 |
| `event_source_id` | `SourceID` (TreatmentEvent) | Required (filled in) | Text, up to 100 |

</details>

<details>
<summary><b>Substance</b>: <code>Substance(rank=..., ...)</code></summary>

`rank` is `P`, `S` or `T` (`Primary`, `Secondary` and `Tertiary` work too), and it decides which elements a substance fills: `Primary...`, `Secondary...` or `Tertiary...`. Primary is required. Secondary and Tertiary are optional, but once reported, every part of them is required.

| Parameter | Element (shown for Primary) | Admission | Discharge | Values |
|---|---|---|---|---|
| `substance` | `PrimarySubstance` | Required | — | 01–18, 20, 97 |
| `detailed_drug_code` | `PrimaryDetailedDrugCode` | Required | — | The Detailed Drug Code Map, such as 0201 |
| `route` | `PrimaryRouteOfAdministration` | Required | — | 01, 02, 03, 04, 20, 96, 97 |
| `frequency` | `PrimaryFrequency` | Required | — | 01, 02, 03, 04, 05, 96, 97 |
| `age_first_use` | `PrimaryAgeOfFirstUse` | Required | — | 0 to 95, or 96, 97 |
| `discharge_substance` | `PrimarySubstance` | — | Required | 01–18, 20, 97 |
| `discharge_frequency` | `PrimaryFrequency` | — | Required | 01, 02, 03, 04, 05, 96, 97 |

</details>

---

## Where the layout and real files disagree

Working WellSky exports don't always follow WellSky's documents to the letter, and the documents don't always agree with each other. These are the gaps we know of, and how this file handles each one. When the documents and a real file disagree, this file follows the documents. If WellSky's response settles any of them differently, the rule is easy to change.

| What exports have been seen doing | What WellSky's documents say | How this file handles it |
|---|---|---|
| The same client repeated in a separate `<Client>` for every episode. | Provider instructions: all of one client's records in a file belong in the same `<Client>`. | Writes one `<Client>` per client. Reports a client split across elements as a Warning. |
| A discharged episode's `<Admission>` sent with `ClientTransactionType` **D**. | Layout: A and T are for admissions; D is for discharges. | Always writes A on the Admission. Reports D on an Admission as an Error. |
| Numbers without leading zeros: `ArrestsInPast30Days` **3**, `DaysWaiting` **42**. | Provider instructions: leading zeros must be included. | Sends exactly what you give it. Reports an Error. |
| `ReasonForDischarge` **97**. | Layout: 97 isn't in the list (01–07, 14, 24), though the layout's not-answered note says 97. | Error |
| `SenateBill6Secondary` **2**. | Layout: only 0 and 1. | Error |
| `Tobacco30` answered when `TobaccoUse` is 2. | Provider instructions: don't answer it then. | Warning |
| Secondary and Tertiary both **97 / 9997**. | Layout: no repeated substance unless the detailed drug codes differ. | Warning only, since exports do this routinely. |
| `State` in capitals, such as **KANSAS**. | Layout: a US state name. | Accepted; case doesn't matter. |
| 8-digit licenses with leading zeros (`00987654`). | Provider instructions' example file name: `KDADS_0012345_…`, 7 characters. | Sends the license exactly as you give it and never pads it. Use the license as KDADS issued it. |
| ProviderID filled with the license. | Interface: WellSky matches ProviderID to its own provider (vendor) number. | Sends the license unless you pass `provider_id`. |

---

## Limits

- **It follows layout v13 (03/10/2026).** When WellSky publishes a new layout, the rules in `WellSkyRules` need updating to match. They're a single table at the top of that class, one row per element.
- **It can't check WellSky's provider list.** A license WellSky doesn't know only shows up in WellSky's response, as *Provider ID not found*.
- **It doesn't send anything.** Uploading the files to WellSky is a separate step.
- **It doesn't translate codes.** Turning your source's values into WellSky codes is up to your code; this file tells you where they don't fit.

---

## Running the tests

Install `pytest` first (see [Installation](#installation)), then, from this folder:

```
python -m pytest tests
```

To also see which lines the tests cover:

```
python -m pytest tests --cov=WellSkyTEDS --cov-report=term-missing
```

The tests use made-up records only. Two more tests use a real WellSky export on test clients when one is available, saved as `tests/sample_export.xml` or named by the `WELLSKY_SAMPLE_XML` environment variable. They read it and confirm the rebuild matches it exactly. Without one, those two are skipped.

---

## Sources

Links checked 10/21/2026.

### Public

| Source | Publisher | What it's for |
|---|---|---|
| [Treatment Episode Data Set (TEDS)](https://www.samhsa.gov/data/data-we-collect/teds-treatment-episode-data-set) | SAMHSA | What TEDS is and who reports it. |
| [TEDS Data Reporting Instructions and Tools](https://www.samhsa.gov/data/data-we-collect/teds-treatment-episode-data-set/instructions) (updated 02/13/2025) | SAMHSA | The national reporting instructions and state crosswalks. |
| [Combined Substance Use and Mental Health TEDS State Instruction Manual](https://www.samhsa.gov/data/report/combined-substance-use-and-mental-health-teds-state-instruction-manual) | SAMHSA | The national TEDS data items and codes that WellSky's layout maps to. |
| [WellSky Human Services (Kansas Substance Use Reporting System)](https://www.kdads.ks.gov/partners-providers/behavioral-health-services-provider-information/wellsky-human-services-kansas-substance-use-reporting-system) | KDADS | Kansas's reporting requirement, the October 2, 2023 move to WellSky, and contacts. |
| [KSURS](https://www.kdads.ks.gov/provider-home/providers/ksurs) | KDADS | The earlier system, and its history after KCPC. |
| [KSURS Bulk Upload File Specifications](https://web.archive.org/web/20250203/https://kdads.ks.gov/home/showpublisheddocument/3302/638533548884100000) (updated 02/07/2022; Internet Archive copy, since KDADS's link no longer works) | KDADS | The retired fixed-width layout, useful when converting historic KSURS files. |

### From WellSky, for Kansas providers

These aren't posted publicly. WellSky and KDADS give them to providers who use the import.

| Document | Version |
|---|---|
| WellSky SUD Custom TEDS Import Layout | v13, 03/10/2026 |
| Custom TEDS Import Interface Specifications, KS KDADS | v2, 05/15/2024 |
| TEDS Import into WellSky: Instructions for Providers | 03/16/2026 |

### Who to ask

KDADS lists these contacts on its [WellSky Human Services page](https://www.kdads.ks.gov/partners-providers/behavioral-health-services-provider-information/wellsky-human-services-kansas-substance-use-reporting-system):

- **Questions about WellSky Human Services or the move from KSURS:** KDADS.WellskyUserRegistry@ks.gov
- **Technical support for KSURS or WellSky Human Services:** EBITSM@ks.gov, 785-296-4999

---

## Disclaimer

- **Independent work.** This project is made by Mission Driven Data. It isn't affiliated with, endorsed by or supported by WellSky, KDADS or SAMHSA. WellSky is a trademark of its owner, and other names belong to theirs; they're used here only to say what this tool works with.
- **Not official guidance.** This README summarizes WellSky's documents as we read them, as of the dates given. WellSky and KDADS set the actual requirements, and they can change them at any time. When this README and their documents disagree, theirs win.
- **Predictions, not guarantees.** A clean predicted error report means no known rule was broken. It doesn't promise that WellSky will accept a file, and a predicted error isn't proof that WellSky will reject one. Always read WellSky's own response file.
- **Your data, your responsibility.** You're responsible for the accuracy of the data you send, for meeting your reporting obligations, and for protecting client information. Substance use treatment records are protected by HIPAA and by 42 CFR Part 2. Keep the XML files and the error report on systems approved for that information, and don't put real client data in an issue, a pull request or an email about this project.
- **As is.** The software is provided as is, without warranty of any kind, as the [License](#license) says. Nothing here is legal advice.

---

## License

Copyright (c) 2026 Mission Driven Data. Released under the [MIT License](LICENSE).

You may use, copy, change and share this software for free, including in your own projects, as long as every copy keeps the copyright notice and the license text. If you build on it, a credit line such as "Built with WellSky TEDS for Kansas by Mission Driven Data" is appreciated.
