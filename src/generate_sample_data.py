"""
Stage 1: generate FICTIONAL sample reviews so we can build and test the
pipeline before real data is collected.

Every review is marked is_fictional = True and the dashboard will say so.

We deliberately "plant" known patterns (for example: Moov delivery and
pre-order complaints rise in the last 3 weeks). Later, when Claude analyses
these reviews, we can check whether it finds the patterns we planted.
The planted labels are saved to a SEPARATE file (sample_ground_truth.csv)
that the analysis step never reads.

Run:  python src/generate_sample_data.py
"""

import csv
import random
from datetime import date, timedelta

import os
os.environ["WPI_DATASET"] = "sample"   # always writes to the sample dataset
from config import DATA_DIR, REVIEWS_CSV

SEED = 42
N_WEEKS = 8
LAST_WEEK_MONDAY = date(2026, 11, 2)   # last full week: Mon 2 Nov - Sun 8 Nov 2026

# ---------------------------------------------------------------------------
# Sentence bank: short phrases per theme and language.
# ---------------------------------------------------------------------------
SNIPPETS = {
    # --- pain points ---
    "delivery_delay": {
        "en": ["Delivery took almost three weeks longer than the date I was given.",
               "It was supposed to arrive in 5 working days, it took more than three weeks.",
               "Still waiting... the delivery date has moved twice already."],
        "nl": ["De levering duurde bijna drie weken langer dan beloofd.",
               "Ik wacht nog steeds, de leverdatum is al twee keer verschoven."],
        "de": ["Die Lieferung hat fast drei Wochen länger gedauert als angekündigt.",
               "Ich warte immer noch, der Liefertermin wurde schon zweimal verschoben."],
    },
    "preorder_communication": {
        "en": ["I pre-ordered and never got a clear update on when it would ship.",
               "The pre-order date kept changing and I only found out by emailing them myself.",
               "Nobody told me my order was a pre-order until after I paid."],
        "nl": ["Ik had een pre-order en kreeg geen enkele update over de verzending.",
               "Pas na betaling bleek het een pre-order te zijn."],
        "de": ["Vorbestellt und nie ein klares Update bekommen, wann es verschickt wird.",
               "Erst nach der Zahlung habe ich erfahren, dass es eine Vorbestellung war."],
    },
    "damaged_in_transit": {
        "en": ["The box arrived crushed and the remote was missing.",
               "One of the side rails was bent on arrival."],
        "nl": ["De doos was beschadigd en de afstandsbediening ontbrak."],
        "de": ["Der Karton war beschädigt und die Fernbedienung fehlte."],
    },
    "assembly_setup": {
        "en": ["The manual is very basic, it took me an hour to figure out the setup.",
               "Had to adjust the belt myself straight out of the box, instructions were unclear."],
        "nl": ["De handleiding is erg summier, de installatie kostte me een uur."],
        "de": ["Die Anleitung ist sehr dürftig, der Aufbau hat eine Stunde gedauert."],
    },
    "noise": {
        "en": ["It is much louder than advertised, my neighbours downstairs complained.",
               "Started squeaking after two weeks, impossible to use during calls."],
        "nl": ["Veel luider dan verwacht, de onderburen klaagden al.",
               "Na twee weken begon hij te piepen."],
        "de": ["Viel lauter als beworben, die Nachbarn unten haben sich beschwert.",
               "Nach zwei Wochen fing es an zu quietschen."],
    },
    "durability": {
        "en": ["The motor died after four months of light use.",
               "The belt started slipping after two months and now it stops randomly."],
        "nl": ["De motor gaf het na vier maanden al op."],
        "de": ["Der Motor ist nach vier Monaten ausgefallen.",
               "Das Band rutscht nach zwei Monaten und stoppt einfach."],
    },
    "app_connectivity": {
        "en": ["The app keeps losing connection, so step tracking is useless.",
               "The remote stopped pairing after a week."],
        "nl": ["De app verliest steeds de verbinding."],
        "de": ["Die App verliert ständig die Verbindung."],
    },
    "returns_refunds": {
        "en": ["Returning it was a nightmare, I had to pay for shipping a 25 kg box myself.",
               "Waiting over a month for my refund."],
        "nl": ["Retourneren was een drama, ik wacht al een maand op mijn geld."],
        "de": ["Die Rücksendung war ein Albtraum, ich warte seit einem Monat auf die Erstattung."],
    },
    "warranty_claims": {
        "en": ["My warranty claim has been open for six weeks with no answer.",
               "They refused the warranty claim saying it was user damage."],
        "nl": ["Mijn garantieclaim staat al zes weken open."],
        "de": ["Meine Garantieanfrage ist seit sechs Wochen offen."],
    },
    "customer_service": {
        "en": ["Customer service only sends copy-paste answers.",
               "I emailed four times and never got a real reply.",
               "No phone number, chat bot only, very frustrating."],
        "nl": ["De klantenservice reageert alleen met standaardantwoorden.",
               "Vier keer gemaild, nooit een echt antwoord gekregen."],
        "de": ["Der Kundenservice schickt nur Standardantworten.",
               "Viermal gemailt und nie eine richtige Antwort bekommen."],
    },
    # --- purchase drivers ---
    "compact_size": {
        "en": ["I chose it because it slides right under the sofa in my small apartment.",
               "Fits perfectly under my standing desk, that was the main reason to buy."],
        "nl": ["Gekocht omdat hij perfect onder mijn sta-bureau past."],
        "de": ["Gekauft, weil es perfekt unter meinen Stehschreibtisch passt."],
    },
    "quiet_motor": {
        "en": ["I picked this one because it was the quietest model I could find."],
        "nl": ["Ik koos deze omdat hij het stilst was."],
        "de": ["Ich habe mich dafür entschieden, weil es das leiseste Modell war."],
    },
    "price_value": {
        "en": ["Great value for the price compared to the big brands.",
               "Bought it because it was half the price of the alternatives."],
        "nl": ["Goede prijs-kwaliteitverhouding, daarom gekozen."],
        "de": ["Super Preis-Leistungs-Verhältnis, deshalb gekauft."],
    },
    "design_look": {
        "en": ["It actually looks nice in the living room, not like gym equipment."],
        "nl": ["Ziet er mooi uit in de woonkamer, niet als een fitnessapparaat."],
        "de": ["Sieht im Wohnzimmer richtig gut aus, nicht wie ein Fitnessgerät."],
    },
    "work_from_home": {
        "en": ["I work from home and wanted to stop sitting all day.",
               "Bought it to get my steps in during long workdays at home."],
        "nl": ["Ik werk thuis en wilde niet meer de hele dag zitten."],
        "de": ["Ich arbeite im Homeoffice und wollte nicht mehr den ganzen Tag sitzen."],
    },
    "brand_trust": {
        "en": ["Went with them because of the good reviews and the warranty.",
               "A brand I already knew, so it felt like a safe choice."],
        "nl": ["Gekozen vanwege de goede reviews."],
        "de": ["Wegen der guten Bewertungen gewählt."],
    },
    "app_features": {
        "en": ["The app with step tracking was a big reason to buy it."],
        "nl": ["De app met stappenteller was voor mij doorslaggevend."],
        "de": ["Die App mit Schrittzähler war für mich ausschlaggebend."],
    },
    # --- delight ---
    "daily_habit": {
        "en": ["I now walk 10,000 steps a day without thinking about it.",
               "Three months in and I use it every single day."],
        "nl": ["Ik loop nu elke dag 10.000 stappen."],
        "de": ["Ich komme jetzt jeden Tag auf 10.000 Schritte."],
    },
    "quiet_while_working": {
        "en": ["I walk through all my meetings and nobody notices."],
        "nl": ["Ik loop tijdens al mijn meetings en niemand merkt het."],
        "de": ["Ich gehe während aller Meetings und niemand merkt es."],
    },
    "easy_to_store": {
        "en": ["The wheels make it easy to roll away when guests come over."],
        "nl": ["Makkelijk weg te rollen als er bezoek komt."],
        "de": ["Lässt sich leicht wegrollen, wenn Besuch kommt."],
    },
    "helpful_support": {
        "en": ["Had an issue with the remote and support sent a new one within days.",
               "Customer service was friendly and solved my problem in one email."],
        "nl": ["De klantenservice was vriendelijk en loste het direct op."],
        "de": ["Der Kundenservice war freundlich und hat das Problem sofort gelöst."],
    },
    "fast_delivery": {
        "en": ["Ordered on Monday, it was here on Wednesday.",
               "Delivery was quick and the driver even carried it inside."],
        "nl": ["Maandag besteld, woensdag in huis."],
        "de": ["Montag bestellt, Mittwoch geliefert."],
    },
    "build_quality": {
        "en": ["Feels solid and well made, no wobbling at all."],
        "nl": ["Voelt stevig en degelijk aan."],
        "de": ["Fühlt sich stabil und hochwertig an."],
    },
}

TITLES = {
    "positive": {"en": ["Love it", "Exactly what I needed", "Great walking pad", "Very happy"],
                 "nl": ["Top aankoop", "Heel tevreden"],
                 "de": ["Sehr zufrieden", "Top Kauf"]},
    "mixed":    {"en": ["Good product, but...", "Mixed feelings", "Okay overall"],
                 "nl": ["Goed product, maar...", "Gemengde gevoelens"],
                 "de": ["Gutes Produkt, aber...", "Gemischte Gefühle"]},
    "negative": {"en": ["Very disappointed", "Avoid", "Not as promised", "Terrible experience"],
                 "nl": ["Erg teleurgesteld", "Niet zoals beloofd"],
                 "de": ["Sehr enttäuscht", "Nicht wie versprochen"]},
}

CLOSINGS = {
    "positive": {"en": ["Highly recommend.", "Happy with my purchase.", ""],
                 "nl": ["Aanrader!", ""], "de": ["Klare Empfehlung.", ""]},
    "mixed":    {"en": ["Hope they improve this.", ""],
                 "nl": ["Hopelijk verbeteren ze dit.", ""], "de": ["Hoffentlich wird das besser.", ""]},
    "negative": {"en": ["Would not recommend until they fix this.", "Very disappointed.", ""],
                 "nl": ["Niet aan te raden.", ""], "de": ["Nicht zu empfehlen.", ""]},
}

# ---------------------------------------------------------------------------
# Brand profiles: the "story" we plant in the data.
# weights = how often each theme shows up when that kind of theme is picked.
# ---------------------------------------------------------------------------
PROFILES = {
    "moov": {
        "reviews_per_week": 14,
        "sources": {"trustpilot": 1.0},
        "languages": {"en": 0.4, "nl": 0.35, "de": 0.25},
        "neg_share": 0.22,
        "drivers": {"compact_size": 4, "design_look": 4, "quiet_motor": 3, "work_from_home": 3},
        "delights": {"easy_to_store": 3, "quiet_while_working": 3, "helpful_support": 3, "daily_habit": 2},
        "pains": {"delivery_delay": 1, "assembly_setup": 3, "customer_service": 1, "damaged_in_transit": 1},
    },
    "walkingpad": {
        "reviews_per_week": 12,
        "sources": {"trustpilot": 0.4, "amazon": 0.6},
        "languages": {"en": 0.6, "de": 0.25, "nl": 0.15},
        "neg_share": 0.30,
        "drivers": {"brand_trust": 4, "compact_size": 3, "app_features": 2},
        "delights": {"easy_to_store": 3, "build_quality": 3, "daily_habit": 2},
        "pains": {"warranty_claims": 4, "app_connectivity": 3, "customer_service": 2, "noise": 1},
    },
    "merach": {
        "reviews_per_week": 9,
        "sources": {"trustpilot": 0.5, "amazon": 0.5},
        "languages": {"en": 0.6, "de": 0.25, "nl": 0.15},
        "neg_share": 0.35,
        "drivers": {"price_value": 5, "app_features": 3, "work_from_home": 2},
        "delights": {"daily_habit": 3, "fast_delivery": 2},
        "pains": {"durability": 4, "returns_refunds": 3, "delivery_delay": 1, "customer_service": 1},
    },
    "sperax": {
        "reviews_per_week": 8,
        "sources": {"amazon": 0.8, "trustpilot": 0.2},
        "languages": {"en": 0.6, "de": 0.25, "nl": 0.15},
        "neg_share": 0.40,
        "drivers": {"price_value": 5, "compact_size": 3},
        "delights": {"daily_habit": 2, "easy_to_store": 2, "fast_delivery": 2},
        "pains": {"noise": 4, "durability": 4, "warranty_claims": 3},
    },
    "decathlon": {
        "reviews_per_week": 8,
        "sources": {"decathlon": 1.0},
        "languages": {"en": 0.4, "nl": 0.3, "de": 0.3},
        "neg_share": 0.18,
        "drivers": {"brand_trust": 4, "price_value": 3},
        "delights": {"build_quality": 4, "fast_delivery": 3, "helpful_support": 2},
        "pains": {"assembly_setup": 3, "noise": 2},
    },
}

# The planted Moov story: in the last 3 weeks, pre-order and delivery issues spike.
MOOV_SPIKE = {  # week index (0 = oldest) -> overrides
    5: {"neg_share": 0.40, "extra_reviews": 3},
    6: {"neg_share": 0.52, "extra_reviews": 6},
    7: {"neg_share": 0.60, "extra_reviews": 9},
}
MOOV_SPIKE_PAINS = {"delivery_delay": 6, "preorder_communication": 6, "customer_service": 3,
                    "assembly_setup": 1, "damaged_in_transit": 1}

COUNTRY_BY_LANG = {"en": ["NL", "DE", "BE", "AT"], "nl": ["NL", "BE"], "de": ["DE", "AT"]}


def pick(rng, weights):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def pick_distinct(rng, weights, n):
    chosen, pool = [], dict(weights)
    for _ in range(min(n, len(pool))):
        k = pick(rng, pool)
        chosen.append(k)
        pool.pop(k)
    return chosen


def build_review(rng, brand, profile, week_idx, week_monday):
    neg_share = profile["neg_share"]
    pains = profile["pains"]
    if brand == "moov" and week_idx in MOOV_SPIKE:
        neg_share = MOOV_SPIKE[week_idx]["neg_share"]
        pains = MOOV_SPIKE_PAINS

    source = pick(rng, profile["sources"])
    lang = pick(rng, profile["languages"])

    # Trustpilot is about the company, marketplaces about the product.
    if source == "trustpilot":
        company = {"delivery_delay", "preorder_communication", "customer_service",
                   "returns_refunds", "warranty_claims", "damaged_in_transit"}
        pains = {k: w * (2 if k in company else 1) for k, w in pains.items()}
    else:
        product = {"noise", "durability", "app_connectivity", "assembly_setup"}
        pains = {k: w * (2 if k in product else 1) for k, w in pains.items()}

    r = rng.random()
    if r < neg_share:
        sentiment = "negative"
    elif r < neg_share + 0.15:
        sentiment = "mixed"
    else:
        sentiment = "positive"

    themes = []
    if sentiment == "positive":
        themes.append(pick(rng, profile["drivers"]))
        themes += pick_distinct(rng, profile["delights"], rng.choice([1, 2]))
        rating = rng.choice([4, 5, 5])
    elif sentiment == "mixed":
        themes.append(pick(rng, profile["drivers"]))
        themes.append(pick(rng, pains))
        rating = rng.choice([3, 3, 4])
    else:
        if rng.random() < 0.4:
            themes.append(pick(rng, profile["drivers"]))
        themes += pick_distinct(rng, pains, rng.choice([1, 2, 2]))
        rating = rng.choice([1, 1, 2])

    sentences = [rng.choice(SNIPPETS[t][lang]) for t in themes]
    closing = rng.choice(CLOSINGS[sentiment][lang])
    if closing:
        sentences.append(closing)

    review_date = week_monday + timedelta(days=rng.randint(0, 6))
    return {
        "brand": brand,
        "source": source,
        "country": rng.choice(COUNTRY_BY_LANG[lang]),
        "language": lang,
        "review_date": review_date.isoformat(),
        "rating": rating,
        "title": rng.choice(TITLES[sentiment][lang]),
        "text": " ".join(sentences),
        "is_fictional": True,
    }, themes, sentiment


def main():
    rng = random.Random(SEED)
    first_monday = LAST_WEEK_MONDAY - timedelta(weeks=N_WEEKS - 1)
    reviews, truth = [], []

    for week_idx in range(N_WEEKS):
        week_monday = first_monday + timedelta(weeks=week_idx)
        for brand, profile in PROFILES.items():
            n = profile["reviews_per_week"] + rng.randint(-2, 2)
            if brand == "moov" and week_idx in MOOV_SPIKE:
                n += MOOV_SPIKE[week_idx]["extra_reviews"]
            for _ in range(n):
                review, themes, sentiment = build_review(rng, brand, profile, week_idx, week_monday)
                review_id = f"FIC-{len(reviews) + 1:05d}"
                reviews.append({"review_id": review_id, **review})
                truth.append({"review_id": review_id, "planted_sentiment": sentiment,
                              "planted_themes": "|".join(themes)})

    reviews.sort(key=lambda r: r["review_date"])
    DATA_DIR.mkdir(exist_ok=True)

    with open(REVIEWS_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(reviews[0]))
        writer.writeheader()
        writer.writerows(reviews)

    with open(DATA_DIR / "sample_ground_truth.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(truth[0]))
        writer.writeheader()
        writer.writerows(truth)

    print(f"Wrote {len(reviews)} FICTIONAL reviews to {REVIEWS_CSV}")
    print(f"Planted labels saved to {DATA_DIR / 'sample_ground_truth.csv'} (not used by the analysis)")


if __name__ == "__main__":
    main()
