from openalex import extract_openalex_candidates


def test_openalex_extracts_only_named_pi_french_award_time_affiliation():
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "publication_year": 2019,
                "authorships": [
                    {
                        "author": {"display_name": "Alice Example"},
                        "institutions": [{"country_code": "FR", "display_name": "CNRS"}],
                        "raw_affiliation_strings": ["Laboratoire Exemple, CNRS, France"],
                    },
                    {
                        "author": {"display_name": "Bob Other"},
                        "institutions": [{"country_code": "FR", "display_name": "Other University"}],
                        "raw_affiliation_strings": ["Laboratoire Coauthor, France"],
                    },
                ],
            },
            {
                "id": "https://openalex.org/W2",
                "publication_year": 2020,
                "authorships": [
                    {
                        "author": {"display_name": "Alice Example"},
                        "institutions": [{"country_code": "FR", "display_name": "CNRS"}],
                        "raw_affiliation_strings": ["Laboratoire Exemple, CNRS, France"],
                    }
                ],
            },
        ]
    }
    result = extract_openalex_candidates("1", "Alice Example", 2019, payload)
    assert result.lab_name.tolist() == ["Laboratoire Exemple"]
    assert result.independent_corroboration.tolist() == [True]
    assert result.pi_match.all()


def test_openalex_does_not_use_late_current_affiliation():
    payload = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "publication_year": 2025,
                "authorships": [
                    {
                        "author": {"display_name": "Alice Example"},
                        "institutions": [{"country_code": "FR", "display_name": "CNRS"}],
                        "raw_affiliation_strings": ["Laboratoire Recent, France"],
                    }
                ],
            }
        ]
    }
    result = extract_openalex_candidates("1", "Alice Example", 2019, payload)
    assert result.empty
