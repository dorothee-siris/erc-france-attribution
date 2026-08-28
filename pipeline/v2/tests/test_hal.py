import pandas as pd

from hal import extract_hal_candidates


def test_extract_hal_candidates_keeps_only_pi_lab_structures_near_start():
    payload = {
        "response": {
            "docs": [
                {
                    "docid": "123",
                    "producedDateY_i": 2018,
                    "authIdHasPrimaryStructure_fs": [
                        "1-1_FacetSep_Alice Example_JoinSep_10_FacetSep_Lab Alice",
                        "2-2_FacetSep_Bob Other_JoinSep_20_FacetSep_Lab Bob",
                        "1-1_FacetSep_Alice Example_JoinSep_30_FacetSep_Example University",
                    ],
                    "labStructId_i": [10, 20],
                    "labStructName_s": ["Lab Alice", "Lab Bob"],
                }
            ]
        }
    }
    result = extract_hal_candidates("755", "Alice Example", 2017, payload)
    assert result.lab_name.tolist() == ["Lab Alice"]
    assert result.structure_id.tolist() == ["10"]
    assert result.pi_match.all()
    assert result.award_time.all()


def test_extract_hal_candidates_rejects_late_publication_as_initial_lab_evidence():
    payload = {
        "response": {
            "docs": [
                {
                    "docid": "124",
                    "producedDateY_i": 2025,
                    "authIdHasPrimaryStructure_fs": ["1-1_FacetSep_Alice Example_JoinSep_10_FacetSep_Lab Alice"],
                    "labStructId_i": [10],
                    "labStructName_s": ["Lab Alice"],
                }
            ]
        }
    }
    result = extract_hal_candidates("755", "Alice Example", 2017, payload)
    assert not result.award_time.any()
