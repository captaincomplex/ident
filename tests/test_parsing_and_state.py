"""Run with:  python -m pytest tests/  (or: python tests/test_parsing_and_state.py)"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ident.parsers.ecrew_pdf import parse_pdf
from ident.models import DutyState, DutyType
from ident.state_engine import compute_view

PDF = "/mnt/user-data/uploads/ScheduleReport_2.pdf"
UTC = dt.timezone.utc


def _roster():
    return parse_pdf(PDF)


def test_parse_counts():
    r = _roster()
    assert r.base == "LGW"
    assert r.crew_name          # parsed from the roster header
    assert len(r.duties) == 30
    fly = [d for d in r.duties if d.duty_type == DutyType.FLY]
    assert len(fly) == 13
    for d in fly:
        assert 1 <= len(d.sectors) <= 4
        assert d.report is not None and d.duty_end is not None


def test_duty_02jun_structure():
    d = next(d for d in _roster().duties if d.date == dt.date(2026, 6, 2))
    assert [s.flight_no for s in d.sectors] == ["8243", "8244"]
    assert (d.sectors[0].dep, d.sectors[0].arr) == ("LGW", "SKG")
    assert d.sectors[1].sta == dt.datetime(2026, 6, 2, 13, 32, tzinfo=UTC)
    # debrief rule: duty end = last on-chocks + 30 min
    assert d.duty_end == d.sectors[1].sta + dt.timedelta(minutes=30)


def _view(now, **kw):
    return compute_view(_roster(), now, debrief_minutes=30,
                        walk_minutes=kw.get("walk", 10),
                        commute_minutes=kw.get("commute", 45))


def test_state_pre_report():
    vm = _view(dt.datetime(2026, 6, 2, 3, 0, tzinfo=UTC))
    assert vm.state == DutyState.BETWEEN_DUTIES
    assert vm.countdown_label == "RPT"
    assert vm.next_sector.flight_no == "8243"
    assert vm.return_sector.flight_no == "8244"


def test_state_in_flight_outbound():
    vm = _view(dt.datetime(2026, 6, 2, 7, 0, tzinfo=UTC))   # mid LGW-SKG
    assert vm.state == DutyState.IN_FLIGHT
    assert vm.active_sector.flight_no == "8243"
    assert vm.return_sector.flight_no == "8244"      # info about return sector
    assert vm.countdown_label == "LAND"


def test_state_turnaround():
    vm = _view(dt.datetime(2026, 6, 2, 9, 0, tzinfo=UTC))   # SKG ground time
    assert vm.state == DutyState.TURNAROUND
    assert vm.next_sector.flight_no == "8244"


def test_home_estimate_math():
    vm = _view(dt.datetime(2026, 6, 2, 7, 0, tzinfo=UTC), walk=10, commute=45)
    # 13:32Z on-chocks +30 debrief +10 walk +45 commute = 14:57Z
    assert vm.home.on_chocks == dt.datetime(2026, 6, 2, 13, 32, tzinfo=UTC)
    assert vm.home.debrief_end == dt.datetime(2026, 6, 2, 14, 2, tzinfo=UTC)
    assert vm.home.home_eta == dt.datetime(2026, 6, 2, 14, 57, tzinfo=UTC)


def test_state_day_off():
    vm = _view(dt.datetime(2026, 6, 6, 12, 0, tzinfo=UTC))
    assert vm.state == DutyState.DAY_OFF


def test_state_standby():
    vm = _view(dt.datetime(2026, 6, 8, 9, 0, tzinfo=UTC))   # within 05:15-13:15Z
    assert vm.state == DutyState.STANDBY


def test_ical_event_parse():
    """The AIMS eCrew event format (from a real calendar event)."""
    from ident.parsers.ical_parser import parse_event
    summary = "8301 LGW-MXP"
    location = "(0555Z-0755Z) LGW"
    description = ("Reporting time : 0540\n"
                   "8301  - LGW  (0655) - MXP  (0855)\n"
                   "* All times in Local Base (LGW)")
    start = dt.datetime(2026, 6, 17, 4, 40, tzinfo=UTC)   # 05:40 BST
    end = dt.datetime(2026, 6, 17, 7, 55, tzinfo=UTC)
    kind, (secs, report) = parse_event(summary, description, location, start, end, "LGW")
    assert kind == "flight"
    s = secs[0]
    assert (s.flight_no, s.dep, s.arr) == ("8301", "LGW", "MXP")
    assert s.std == dt.datetime(2026, 6, 17, 5, 55, tzinfo=UTC)   # 0555Z, matches LOCATION
    assert s.sta == dt.datetime(2026, 6, 17, 7, 55, tzinfo=UTC)   # 0755Z, matches LOCATION
    assert report == dt.datetime(2026, 6, 17, 4, 40, tzinfo=UTC)  # 0440Z


def test_ical_full_feed():
    """End-to-end feed parse. Skips cleanly if icalendar isn't installed."""
    try:
        import icalendar  # noqa: F401
    except Exception:
        print("(skipped: icalendar not installed)")
        return
    from ident.parsers.ical_parser import parse_ical
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "fixtures", "aims_sample.ics"), "rb") as f:
        roster = parse_ical(f.read(), base_iata="LGW")
    fly = [d for d in roster.duties if d.duty_type == DutyType.FLY]
    assert roster.base == "LGW"
    assert len(fly) == 1 and len(fly[0].sectors) == 2
    assert [s.flight_no for s in fly[0].sectors] == ["8301", "8304"]
    assert fly[0].report == dt.datetime(2026, 6, 17, 4, 40, tzinfo=UTC)
    assert any(d.duty_type == DutyType.STANDBY for d in roster.duties)
    assert any(d.duty_type == DutyType.DAY_OFF for d in roster.duties)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {fn.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {fn.__name__}: {type(e).__name__}: {e}")
    print(f"\n{passed}/{len(fns)} passed")
