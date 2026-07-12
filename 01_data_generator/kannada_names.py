"""
Kannada + Roman name pools for realistic AccusedName / VictimName / ComplainantName.
Includes the deliberate transliteration-variant identity used in seeded Connection Set C.
"""

# Roman male first names common in Karnataka
ROMAN_MALE = ["Ramesh", "Suresh", "Manjunath", "Prakash", "Nagaraj", "Shivakumar",
              "Basavaraj", "Mahesh", "Girish", "Santosh", "Kiran", "Anand",
              "Ravi", "Naveen", "Praveen", "Vinod", "Harish", "Umesh"]
ROMAN_FEMALE = ["Lakshmi", "Savitha", "Geetha", "Kavya", "Pooja", "Sunitha",
                "Radha", "Anitha", "Vijaya", "Shobha", "Nandini", "Roopa"]
ROMAN_SURNAME = ["Gowda", "Reddy", "Hegde", "Rao", "Naik", "Shetty", "Patil",
                 "Kumar", "Murthy", "Bhat", "Achar", "Gouda"]

# Kannada-script first names (a small pool; used to make some names script-native)
KANNADA_MALE = ["ರಮೇಶ್", "ಸುರೇಶ್", "ಮಂಜುನಾಥ್", "ಪ್ರಕಾಶ್", "ನಾಗರಾಜ್", "ಶಿವಕುಮಾರ್", "ಮಹೇಶ್"]
KANNADA_FEMALE = ["ಲಕ್ಷ್ಮಿ", "ಸವಿತಾ", "ಗೀತಾ", "ಕಾವ್ಯ", "ಸುನೀತಾ", "ರಾಧಾ"]

# ---- Connection Set C: the transliteration-variant identity ----
# ONE real person, written three different ways across three FIRs.
# ground_truth records these three Accused rows as the same person.
KANNADA_VARIANT_IDENTITY = {
    "true_person_label": "TRUE_PERSON_RAMAIAH",
    "variants": [
        "ರಾಮಯ್ಯ.ಕೆ",   # Kannada script with initial
        "Ramaiah K",     # Roman transliteration
        "ರಾಮು",          # short Kannada form
    ],
    "age": 34,
    "gender_id": 1,
}
