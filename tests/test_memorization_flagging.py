"""Tests for the mechanical, code-only memorization flag. No API calls, no
human review -- these are pure text-overlap checks."""
from src.memorization_flagging import extract_distinctive_facts, flag_all, flag_item


def test_phone_number_leak_is_flagged():
    passage = "Call the Hayward Butcher Shop at (510) 889-8690 for hours."
    question = "What is the phone number?"
    withheld_response = "I believe the number is (510) 889-8690, based on general listings."
    result = flag_item(passage, question, withheld_response)
    assert result["likely_memorized"] is True
    assert "(510) 889-8690" in result["matched_in_withheld_response"]


def test_generic_correct_sounding_answer_not_flagged():
    passage = "The store is located in Hayward, California and is open on weekdays."
    question = "Where is the store located?"
    withheld_response = "It's probably somewhere in California, though I can't be sure without more context."
    result = flag_item(passage, question, withheld_response)
    assert result["likely_memorized"] is False


def test_facts_already_given_away_by_question_are_excluded():
    passage = "The 2016 report shows revenue of $4,500,000 for the Acme Corporation."
    question = "What was the 2016 revenue for the Acme Corporation, which was $4,500,000?"
    withheld_response = "The revenue was $4,500,000 for Acme Corporation, as stated in the question."
    facts = extract_distinctive_facts(passage, question)
    # $4,500,000 and "Acme Corporation" are both already in the question, so
    # matching them in the response proves nothing about memorization.
    assert "$4,500,000" not in facts
    assert "Acme Corporation" not in facts


def test_money_amount_leak_is_flagged():
    passage = "The home last sold for $412,500 in a private transaction."
    question = "What did the home sell for?"
    withheld_response = "Based on comparable sales, it likely sold for around $412,500."
    result = flag_item(passage, question, withheld_response)
    assert result["likely_memorized"] is True


def test_short_numbers_are_not_treated_as_distinctive():
    passage = "There are 12 units in the building, built in 1998."
    question = "How many units are there?"
    withheld_response = "There are 12 units, and the building dates to around 1998."
    facts = extract_distinctive_facts(passage, question)
    # 3-digit-or-fewer numbers are too common to count as distinctive on
    # their own -- only 4+ digit numbers, phone numbers, money, and percent
    # patterns count. "12" should not appear here at all.
    assert "12" not in facts


def test_proper_noun_leak_is_flagged():
    passage = "This property is managed by Silver Oak Property Management."
    question = "Who manages this property?"
    withheld_response = "Silver Oak Property Management manages properties in this area."
    result = flag_item(passage, question, withheld_response)
    assert result["likely_memorized"] is True


def test_flag_all_skips_items_without_condition_d_response():
    items = [{"item_id": "x1", "passage": "p", "question": "q"}]
    all_responses = {"x1": {"a": {"text": "some grounded response"}}}  # no "d" key
    flags = flag_all(items, all_responses)
    assert flags == []


def test_flag_all_reports_per_item():
    items = [
        {"item_id": "x1", "passage": "Call (555) 123-4567 for info.", "question": "What number?"},
        {"item_id": "x2", "passage": "The town has a population of about two thousand.", "question": "Population?"},
    ]
    all_responses = {
        "x1": {"d": {"text": "The number is (555) 123-4567."}},
        "x2": {"d": {"text": "I'm not sure of the exact population without the source."}},
    }
    flags = flag_all(items, all_responses)
    by_id = {f["item_id"]: f for f in flags}
    assert by_id["x1"]["likely_memorized"] is True
    assert by_id["x2"]["likely_memorized"] is False
