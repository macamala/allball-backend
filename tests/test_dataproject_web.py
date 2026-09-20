from collector.adapters import FetchRequest, FetchResult
from collector.adapters_dataproject import DataProjectWebAdapter, parse_dataproject_html

CEV_HTML = """
<html><body>
<legend><b>Day 1</b> (From: <span>10/09/2026</span>)</legend>
<div id="ctl00_userControl_RADLIST_Legs_ctrl0_RADLIST_Matches_ctrl0_div_match">
<span id="x_Label2"><font>Italy</font></span>
<span id="x_Label4"><font>Sweden</font></span>
<span id="x_LB_SetCasa"><font>3</font></span>
<span id="x_LB_SetOspiti"><font>0</font></span>
<span id="x_LB_DataOra"><font>10/09/2026 21:05</font></span>
<span id="x_LB_Palasport"><font>Arena Piazza del Plebiscito, Naples</font></span>
<a href="MatchPage.aspx?mID=84508">MFA-01</a>
</div>
</body></html>
"""

PLUSLIGA_HTML = """
<html><body>
Aluron CMC Warta Zawiercie vs Jastrzebski Wegiel 3-1
</body></html>
"""


def test_dataproject_family_parses_cev_and_score_rows():
    cev = parse_dataproject_html(CEV_HTML, competition_id="cev-eurovolley-men")
    assert cev[0]["home"]["name"] == "Italy"
    assert cev[0]["score"] == {"home": 3, "away": 0}
    assert cev[0]["id"] == "84508"
    assert cev[0]["source_family"] == "dataproject-web"
    plus = parse_dataproject_html(PLUSLIGA_HTML, competition_id="plusliga")
    assert plus[0]["home"]["name"] == "Aluron CMC Warta Zawiercie"
    assert plus[0]["score"]["home"] == 3
    assert plus[0]["source_family"] == "dataproject-web"


def test_dataproject_adapter_uses_one_host_url():
    pages = {"https://www.legavolley.it/calendario": FetchResult(ok=True, http_status=200, payload=PLUSLIGA_HTML)}

    def getter(url, timeout=None):
        return pages[url]

    adapter = DataProjectWebAdapter(text_getter=getter)
    result = adapter.fetch(FetchRequest(capability="snapshot", competition_id="italy-superlega"))
    assert result.ok
    assert result.request_count == 1
    assert result.events
    assert result.parse_reason.startswith("dataproject-web")
