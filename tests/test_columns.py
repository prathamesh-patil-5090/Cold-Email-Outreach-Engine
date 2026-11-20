from outreach.sheets import column_letter


def test_column_letters():
    assert column_letter(1) == "A"
    assert column_letter(20) == "T"
    assert column_letter(27) == "AA"
