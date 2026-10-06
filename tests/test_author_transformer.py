import unittest

from processing.transformer import extract_authors_from_hal_record


class AuthorTransformerTest(unittest.TestCase):

  def test_realigns_only_author_ids_matching_a_unique_name(self):
    authors = extract_authors_from_hal_record({
        "authFullName_s": [
            "Ye Tao",
            "Sébastien Acket",
            "Emma Beaumont",
            "Henri Galez",
            "Luminita Duma",
            "Yannick Rossez",
        ],
        "authIdHal_s": [
            "luminita-duma",
            "yannick-rossez",
            0,
            0,
            0,
            0,
        ],
        "authIdPerson_i": [1099962, 1099963, 1099964, 1099965, 9094, 739000],
    })

    self.assertEqual(
        [author.hal_id for author in authors],
        [
            "person_1099962",
            "person_1099963",
            "person_1099964",
            "person_1099965",
            "luminita-duma",
            "yannick-rossez",
        ],
    )

  def test_uses_person_id_before_name_fallback(self):
    authors = extract_authors_from_hal_record({
        "authFullName_s": ["Ada Lovelace", "Grace Hopper"],
        "authIdHal_s": ["0", "0"],
        "authIdPerson_i": [42, "0"],
    })

    self.assertEqual(
        [author.hal_id for author in authors],
        ["person_42", "unknown_Grace Hopper"],
    )

  def test_preserves_positional_ids_when_no_shift_is_confirmed(self):
    authors = extract_authors_from_hal_record({
        "authFullName_s": ["Ada Lovelace", "Grace Hopper"],
        "authIdHal_s": ["ada-lovelace", "unrelated-hal-username"],
        "authIdPerson_i": [42, 43],
    })

    self.assertEqual(
        [author.hal_id for author in authors],
        ["ada-lovelace", "unrelated-hal-username"],
    )


if __name__ == "__main__":
  unittest.main()
