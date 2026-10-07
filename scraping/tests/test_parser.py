"""Parser tests using text copied from real SFPD CompStat PDFs.

Run:  python -m pytest scraping/tests -q
"""

from scraping.sfpd_scraper import (
    ReportLink, detect_district, fetch_report_links, parse_pages, parse_row, validate,
)

LINK_2026 = ReportLink(2026, 8, "SFPD Compstat Report August 2026", "https://example/aug2026.pdf")
LINK_2023 = ReportLink(2023, 1, "SFPD Compstat Report January 2023", "https://example/jan2023.pdf")

# --- 2025+ Power BI layout: district header comes BEFORE the table ---------
CENTRAL_P1_2026 = """COMPSTAT Power BI Desktop
CENTRAL DISTRICT PROFILE
August 1-31, 2026
CRIME CATEGORY AUG 2025 AUG 2026 % CHANGE JUL 2026 AUG 2026 % CHANGE YTD 2025 YTD 2026 % CHANGE YTD
Homicide 0 0 0 0 2 1 -50%
Rape 3 2 -33% 2 2 0% 17 17 0%
Robbery 16 17 6% 16 17 6% 131 104 -21%
Assault 20 21 5% 20 21 5% 136 137 1%
Human Trafficking - Sex Act 0 0 0 0 0 1
Human Trafficking -Involuntary Serv. 0 0 0 0 0 0
TOTAL PART 1 VIOLENT CRIMES 39 40 3% 38 40 5% 286 260 -9%
Burglary 38 37 -3% 25 37 48% 290 229 -21%
Person/Other Theft * 168 128 -24% 111 128 15% 1153 922 -20%
Theft From Vehicle * 76 14 -82% 24 14 -42% 560 267 -52%
Larceny Theft 244 142 -42% 135 142 5% 1713 1189 -31%
Motor Vehicle Theft 21 26 24% 30 26 -13% 175 186 6%
Arson 3 4 33% 5 4 -20% 21 28 33%
TOTAL PART 1 PROPERTY CRIMES 306 209 -32% 195 209 7% 2199 1632 -26%
TOTAL PART 1 CRIMES 345 249 -28% 233 249 7% 2485 1892 -24%
Not Cal
"""

CITYWIDE_P2_2026 = """Power BI Desktop COMPSTAT - Page 2 - CITYWIDE
San Francisco Police Department
CLASSIFICATION OF OFFENSE AUG 2025 AUG 2026 % CHANGE JUL 2026 AUG 2026 % CHANGE YTD 2025 YTD 2026 % CHANGE YTD
Other Assaults (Misdemeanors) 372 380 2% 408 380 -7% 2974 3044 2%
Total Domestic Violence 294 283 -4% 260 283 9% 2197 2272 3%
Firearm 3 2 -33% 1 2 100% 21 11 -48%
Knife or Other Cutting Instrument 8 5 -38% 2 5 150% 38 30 -21%
Other 84 98 17% 79 98 24% 728 776 7%
Hands, Fists and Feet 144 126 -13% 139 126 -9% 1031 1075 4%
DV's without Known Weapons Involved 80 58 -28% 55 58 5% 563 518 -8%
FIREARM RELATED AUG 2025 AUG 2026 % CHANGE JUL 2026 AUG 2026 % CHANGE YTD 2025 YTD 2026 % CHANGE YTD
Non-Fatal Shooting Incidents-217 11 4 -64% 7 4 -43% 56 49 -13%
Homicides by Firearm-187 Victims 1 0 -100% 0 0 12 10 -17%
Total Gun Violence Incidents 11 4 -64% 6 4 -33% 65 56 -14%
Firearms Seized 87 66 -24% 65 66 2% 643 627 -2%
Jan Feb Mar Apr May Jun Jul Aug
89 79
104
"""

# Percentages wrapped onto their own lines (seen in the Mission page).
MISSION_WRAPPED = """MISSION DISTRICT PROFILE
Burglary 60 26 -57% 34 26 -24% 399 283
Person/Other Theft * 126 85 -33% 112 85 -24% 1029 1030
-29%
0.1%
"""

# --- 2023 layout: district name comes AFTER the table ----------------------
CENTRAL_P1_2023 = """JANUARY JANUARY DECEMBER JANUARY
2022 2023 2022 2023
HOMICIDE 0 0 not cal 0 0 not cal 0 0 not cal
RAPE 2 0 -100% 2 0 -100% 2 0 -100%
ROBBERY 26 20 -23% 20 20 0% 26 20 -23%
AGGRAVATED ASSAULT 17 22 29% 15 22 47% 17 22 29%
TOTAL PART 1 VIOLENT CRIMES 45 42 -7% 37 42 14% 45 42 -7%
LARCENY THEFT* 544 673 24% 878 673 -23% 544 673 24%
AUTO THEFT 41 22 -46% 37 22 -41% 41 22 -46%
TOTAL PART 1 PROPERTY CRIMES 645 762 18% 987 762 -23% 645 762 18%
TOTAL PART 1 CRIMES 690 804 17% 1024 804 -21% 690 804 17%
JAN-01-2023 to JAN-31-2023
COMPSTAT
 Central Profile
"""

# Page 2 of the Southern report has a chart mislabeled "CENTRAL".
SOUTHERN_P2_2023 = """COMPSTAT - Page 2 - Southern
OTHER ASSAULTS (Misdemeanor): 45 46 2% 50 46 -8% 45 46 2%
Non-Fatal Shooting Incidents-217 0 2 not cal 2 2 0% 0 2 not cal
Homicides by Firearm-187 1 0 -100% 1 0 -100% 1 0 -100% SHOOTINGS
Total Shooting Incidents (217 & 187) 1 2 100% 3 2 -33% 1 2 100%
CENTRAL
Total Shooting Incidents (217 & 187)
"""


def _by_cat(records, district):
    return {r["category"]: r for r in records if r["district"] == district}


def test_detect_district_both_layouts():
    assert detect_district(CENTRAL_P1_2026) == "CENTRAL"
    assert detect_district(CITYWIDE_P2_2026) == "CITYWIDE"
    assert detect_district(CENTRAL_P1_2023) == "CENTRAL"
    assert detect_district(SOUTHERN_P2_2023) == "SOUTHERN"


def test_row_without_percent_when_base_is_zero():
    cat, sec, counts = parse_row("Homicide 0 0 0 0 2 1 -50%")
    assert (cat, sec, counts) == ("homicide", "part1_violent", [0, 0, 0, 0, 2, 1])


def test_other_assaults_not_confused_with_assault_or_other():
    cat, _, _ = parse_row("Other Assaults (Misdemeanors) 372 380 2% 408 380 -7% 2974 3044 2%")
    assert cat == "other_assaults_misdemeanor"


def test_new_layout_page1():
    recs = parse_pages([CENTRAL_P1_2026], LINK_2026)
    c = _by_cat(recs, "CENTRAL")
    assert len(c) == 15
    assert c["robbery"]["current_month"] == 17
    assert c["robbery"]["same_month_prior_year"] == 16
    assert c["larceny_theft"]["ytd_current"] == 1189
    assert c["motor_vehicle_theft"]["previous_month"] == 30
    warnings = validate(recs, "2026-08")
    # only one district in the fixture, and its totals add up
    assert len(warnings) == 1 and "missing districts" in warnings[0]


def test_new_layout_page2_dv_and_firearms():
    c = _by_cat(parse_pages([CITYWIDE_P2_2026], LINK_2026), "CITYWIDE")
    assert c["dv_other"]["current_month"] == 98
    assert c["dv_firearm"]["ytd_current"] == 11
    assert c["firearms_seized"]["current_month"] == 66
    assert c["homicides_by_firearm"]["ytd_prior_year"] == 12
    assert c["domestic_violence_total"]["section"] == "domestic_violence"


def test_wrapped_percentages():
    c = _by_cat(parse_pages([MISSION_WRAPPED], LINK_2026), "MISSION")
    assert c["burglary"]["ytd_current"] == 283
    assert c["person_other_theft"]["ytd_current"] == 1030


def test_old_layout_maps_to_same_categories():
    recs = parse_pages([CENTRAL_P1_2023, SOUTHERN_P2_2023], LINK_2023)
    c = _by_cat(recs, "CENTRAL")
    assert c["aggravated_assault"]["current_month"] == 22
    assert c["motor_vehicle_theft"]["current_month"] == 22
    assert c["total_part1"]["current_month"] == 804
    s = _by_cat(recs, "SOUTHERN")
    assert s["total_shooting_incidents"]["current_month"] == 2
    assert "total_shooting_incidents" not in c  # mislabeled chart ignored


def test_fetch_report_links_from_html():
    html = """
    <a href="/sites/default/files/2026-09/August%202026%20Crime%20Report.pdf">SFPD Compstat Report August 2026</a>
    <a href="https://www.sanfranciscopolice.org/sites/default/files/2023-06/x.pdf">SFPD Compstat May 2023</a>
    <a href="/sites/default/files/2018-11/SFPD-CompStat-YearEnd-2017.pdf">SFPD YearEnd Stats 2017</a>
    <a href="/stay-safe">Stay Safe</a>
    """
    links = fetch_report_links(html)
    assert [l.period for l in links] == ["2023-05", "2026-08"]
    assert links[1].url.startswith("https://www.sanfranciscopolice.org/sites/default/files/2026-09/")
