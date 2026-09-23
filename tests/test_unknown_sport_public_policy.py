def test_unknown_sport_rows_are_not_public():
    # Public list policy deliberately excludes unidentified rows. The writer
    # diagnostics still retain them for repair rather than silently deleting.
    import inspect
    from collector.provider import NinkoCollectedSportsDataProvider

    source = inspect.getsource(NinkoCollectedSportsDataProvider.get_events)
    assert 'row.get("sport") not in {None, "", "unknown"}' in source
