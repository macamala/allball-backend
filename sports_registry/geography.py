"""Provider-independent geography: countries, association territories, and regions.

A competition may belong to a country, a region, or both. International
competitions are not forced into a single country.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .schema import GeographyRecord

REGIONS: List[GeographyRecord] = [
    {"id": "world", "slug": "world", "name": "World", "kind": "region", "iso_code": None, "parent_id": None},
    {
        "id": "international",
        "slug": "international",
        "name": "International",
        "kind": "region",
        "iso_code": None,
        "parent_id": None,
    },
    {"id": "europe", "slug": "europe", "name": "Europe", "kind": "region", "iso_code": None, "parent_id": "world"},
    {"id": "asia", "slug": "asia", "name": "Asia", "kind": "region", "iso_code": None, "parent_id": "world"},
    {"id": "africa", "slug": "africa", "name": "Africa", "kind": "region", "iso_code": None, "parent_id": "world"},
    {
        "id": "north-america",
        "slug": "north-america",
        "name": "North America",
        "kind": "region",
        "iso_code": None,
        "parent_id": "world",
    },
    {
        "id": "south-america",
        "slug": "south-america",
        "name": "South America",
        "kind": "region",
        "iso_code": None,
        "parent_id": "world",
    },
    {"id": "oceania", "slug": "oceania", "name": "Oceania", "kind": "region", "iso_code": None, "parent_id": "world"},
]

# FIFA/UEFA-style territories used by existing competitions. Not ISO countries.
ASSOCIATION_TERRITORIES: List[GeographyRecord] = [
    {"id": "england", "slug": "england", "name": "England", "kind": "territory", "iso_code": None, "parent_id": "europe"},
    {"id": "scotland", "slug": "scotland", "name": "Scotland", "kind": "territory", "iso_code": None, "parent_id": "europe"},
    {"id": "wales", "slug": "wales", "name": "Wales", "kind": "territory", "iso_code": None, "parent_id": "europe"},
    {
        "id": "northern-ireland",
        "slug": "northern-ireland",
        "name": "Northern Ireland",
        "kind": "territory",
        "iso_code": None,
        "parent_id": "europe",
    },
]

# slug iso name region
_ISO_COUNTRIES = """
ad AD Andorra europe
ae AE United-Arab-Emirates asia
af AF Afghanistan asia
ag AG Antigua-and-Barbuda north-america
al AL Albania europe
am AM Armenia asia
ao AO Angola africa
ar AR Argentina south-america
at AT Austria europe
au AU Australia oceania
az AZ Azerbaijan asia
ba BA Bosnia-and-Herzegovina europe
bb BB Barbados north-america
bd BD Bangladesh asia
be BE Belgium europe
bf BF Burkina-Faso africa
bg BG Bulgaria europe
bh BH Bahrain asia
bi BI Burundi africa
bj BJ Benin africa
bn BN Brunei asia
bo BO Bolivia south-america
br BR Brazil south-america
bs BS Bahamas north-america
bt BT Bhutan asia
bw BW Botswana africa
by BY Belarus europe
bz BZ Belize north-america
ca CA Canada north-america
cd CD DR-Congo africa
cf CF Central-African-Republic africa
cg CG Congo africa
ch CH Switzerland europe
ci CI Ivory-Coast africa
cl CL Chile south-america
cm CM Cameroon africa
cn CN China asia
co CO Colombia south-america
cr CR Costa-Rica north-america
cu CU Cuba north-america
cv CV Cape-Verde africa
cy CY Cyprus europe
cz CZ Czech-Republic europe
de DE Germany europe
dj DJ Djibouti africa
dk DK Denmark europe
dm DM Dominica north-america
do DO Dominican-Republic north-america
dz DZ Algeria africa
ec EC Ecuador south-america
ee EE Estonia europe
eg EG Egypt africa
er ER Eritrea africa
es ES Spain europe
et ET Ethiopia africa
fi FI Finland europe
fj FJ Fiji oceania
fm FM Micronesia oceania
fr FR France europe
ga GA Gabon africa
gb GB United-Kingdom europe
gd GD Grenada north-america
ge GE Georgia asia
gh GH Ghana africa
gm GM Gambia africa
gn GN Guinea africa
gq GQ Equatorial-Guinea africa
gr GR Greece europe
gt GT Guatemala north-america
gw GW Guinea-Bissau africa
gy GY Guyana south-america
hn HN Honduras north-america
hr HR Croatia europe
ht HT Haiti north-america
hu HU Hungary europe
id ID Indonesia asia
ie IE Ireland europe
il IL Israel asia
in IN India asia
iq IQ Iraq asia
ir IR Iran asia
is IS Iceland europe
it IT Italy europe
jm JM Jamaica north-america
jo JO Jordan asia
jp JP Japan asia
ke KE Kenya africa
kg KG Kyrgyzstan asia
kh KH Cambodia asia
ki KI Kiribati oceania
km KM Comoros africa
kn KN Saint-Kitts-and-Nevis north-america
kp KP North-Korea asia
kr KR South-Korea asia
kw KW Kuwait asia
kz KZ Kazakhstan asia
la LA Laos asia
lb LB Lebanon asia
lc LC Saint-Lucia north-america
li LI Liechtenstein europe
lk LK Sri-Lanka asia
lr LR Liberia africa
ls LS Lesotho africa
lt LT Lithuania europe
lu LU Luxembourg europe
lv LV Latvia europe
ly LY Libya africa
ma MA Morocco africa
mc MC Monaco europe
md MD Moldova europe
me ME Montenegro europe
mg MG Madagascar africa
mh MH Marshall-Islands oceania
mk MK North-Macedonia europe
ml ML Mali africa
mm MM Myanmar asia
mn MN Mongolia asia
mr MR Mauritania africa
mt MT Malta europe
mu MU Mauritius africa
mv MV Maldives asia
mw MW Malawi africa
mx MX Mexico north-america
my MY Malaysia asia
mz MZ Mozambique africa
na NA Namibia africa
ne NE Niger africa
ng NG Nigeria africa
ni NI Nicaragua north-america
nl NL Netherlands europe
no NO Norway europe
np NP Nepal asia
nr NR Nauru oceania
nz NZ New-Zealand oceania
om OM Oman asia
pa PA Panama north-america
pe PE Peru south-america
pg PG Papua-New-Guinea oceania
ph PH Philippines asia
pk PK Pakistan asia
pl PL Poland europe
ps PS Palestine asia
pt PT Portugal europe
pw PW Palau oceania
py PY Paraguay south-america
qa QA Qatar asia
ro RO Romania europe
rs RS Serbia europe
ru RU Russia europe
rw RW Rwanda africa
sa SA Saudi-Arabia asia
sb SB Solomon-Islands oceania
sc SC Seychelles africa
sd SD Sudan africa
se SE Sweden europe
sg SG Singapore asia
si SI Slovenia europe
sk SK Slovakia europe
sl SL Sierra-Leone africa
sm SM San-Marino europe
sn SN Senegal africa
so SO Somalia africa
sr SR Suriname south-america
ss SS South-Sudan africa
st ST Sao-Tome-and-Principe africa
sv SV El-Salvador north-america
sy SY Syria asia
sz SZ Eswatini africa
td TD Chad africa
tg TG Togo africa
th TH Thailand asia
tj TJ Tajikistan asia
tl TL Timor-Leste asia
tm TM Turkmenistan asia
tn TN Tunisia africa
to TO Tonga oceania
tr TR Turkey europe
tt TT Trinidad-and-Tobago north-america
tv TV Tuvalu oceania
tz TZ Tanzania africa
ua UA Ukraine europe
ug UG Uganda africa
us US United-States north-america
uy UY Uruguay south-america
uz UZ Uzbekistan asia
vc VC Saint-Vincent north-america
ve VE Venezuela south-america
vn VN Vietnam asia
vu VU Vanuatu oceania
ws WS Samoa oceania
xk XK Kosovo europe
ye YE Yemen asia
za ZA South-Africa africa
zm ZM Zambia africa
zw ZW Zimbabwe africa
""".strip()

COUNTRY_ALIASES = {
    "usa": "us",
    "united-states": "us",
    "united-kingdom": "gb",
    "uk": "gb",
    "czech-republic": "cz",
    "czechia": "cz",
    "south-korea": "kr",
    "ivory-coast": "ci",
    "cote-divoire": "ci",
    "global": "international",
}


def _iso_countries() -> List[GeographyRecord]:
    rows: List[GeographyRecord] = []
    for line in _ISO_COUNTRIES.splitlines():
        slug, iso, name, region = line.split()
        rows.append(
            {
                "id": slug,
                "slug": slug,
                "name": name.replace("-", " "),
                "kind": "country",
                "iso_code": iso,
                "parent_id": region,
            }
        )
    return rows


COUNTRIES: List[GeographyRecord] = _iso_countries()


def all_geography() -> List[GeographyRecord]:
    return [*REGIONS, *ASSOCIATION_TERRITORIES, *COUNTRIES]


def _geo_index() -> Dict[str, GeographyRecord]:
    out: Dict[str, GeographyRecord] = {}
    for row in all_geography():
        out[row["id"]] = row
        out[row["slug"]] = row
        iso = row.get("iso_code")
        if iso:
            out[iso.lower()] = row
            out[iso] = row
        name_slug = row["name"].lower().replace(" ", "-")
        out.setdefault(name_slug, row)
    return out


def canonical_geo_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    raw = str(value).strip().lower()
    alias = COUNTRY_ALIASES.get(raw, raw)
    row = _geo_index().get(alias)
    return row["id"] if row else alias


def get_geo(value: Optional[str]) -> Optional[GeographyRecord]:
    key = canonical_geo_id(value)
    if not key:
        return None
    return _geo_index().get(key)


def label_for(value: Optional[str]) -> str:
    row = get_geo(value)
    if row:
        return row["name"]
    if not value:
        return ""
    return str(value).replace("-", " ").title()


def region_for_country(value: Optional[str]) -> Optional[str]:
    row = get_geo(value)
    if not row:
        return None
    if row.get("kind") == "region":
        return row["id"]
    parent = row.get("parent_id")
    if parent in {item["id"] for item in REGIONS}:
        return parent
    return None


def public_geo(row: GeographyRecord) -> Dict[str, object]:
    return {
        "id": row["id"],
        "slug": row["slug"],
        "name": row["name"],
        "kind": row["kind"],
        "iso_code": row.get("iso_code"),
        "parent_id": row.get("parent_id"),
        "region_id": region_for_country(row["id"]) if row.get("kind") != "region" else row["id"],
    }
