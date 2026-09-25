"""Place names a job's location text may use for what someone searched or set an alert for.
Shared by the /jobs location filter (webapp/jobs_listing.py) and alert rules (alerts/rules.py).

Most job locations carry no country (55% of the warehouse on 2026-09-25) -- "Bengaluru,
Karnataka" -- so "India" has to mean its cities too, and cities have more than one name."""

# Other names a city goes by.
_CITY_NAMES = [
    ("bengaluru", "bangalore"), ("mumbai", "bombay"), ("gurugram", "gurgaon"), ("kolkata", "calcutta"),
    ("chennai", "madras"), ("thiruvananthapuram", "trivandrum"), ("kochi", "cochin"), ("mysuru", "mysore"),
    ("vadodara", "baroda"), ("puducherry", "pondicherry"), ("visakhapatnam", "vizag"),
]
# Places people search for that are a group of cities.
_REGIONS = {
    "ncr": ("ncr", "delhi", "new delhi", "gurugram", "gurgaon", "noida", "greater noida", "ghaziabad", "faridabad"),
}
INDIA_CITIES = (
    "bengaluru", "bangalore", "hyderabad", "secunderabad", "pune", "chennai", "madras", "mumbai", "bombay",
    "navi mumbai", "thane", "delhi", "new delhi", "gurugram", "gurgaon", "noida", "greater noida", "ghaziabad",
    "faridabad", "kolkata", "calcutta", "ahmedabad", "gandhinagar", "kochi", "cochin", "thiruvananthapuram",
    "trivandrum", "coimbatore", "jaipur", "chandigarh", "mohali", "indore", "nagpur", "mysuru", "mysore",
    "bhubaneswar", "vadodara", "baroda", "visakhapatnam", "vizag", "lucknow", "surat", "mangaluru", "mangalore",
    "vijayawada", "madurai", "bhopal", "nashik", "puducherry", "pondicherry",
)

_ALIASES = {}
for names in _CITY_NAMES:
    for name in names:
        _ALIASES[name] = names
_ALIASES.update(_REGIONS)
_ALIASES["india"] = ("india",) + INDIA_CITIES


def spellings(place):
    """Every lower-case name that stands for `place` in a job's location text: "india" ->
    India and its cities; "bangalore" -> bangalore, bengaluru; anything else -> itself."""
    key = " ".join((place or "").lower().split())
    return _ALIASES.get(key, (key,)) if key else ()
