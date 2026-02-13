# TELEGRAM OPS CHEATSHEET
A) New Offer: τρέξε `menu-offer` με date/guests/service/budget + menu lines με portions.
B) Patch & Resume: αν BLOCKED στο recipe-review, συμπλήρωσε CSV και τρέξε `resume`.
C) Search & Open: βρες proposals με φίλτρα, μετά `open-result` για full path.
Outputs:
- menu-offer: `runs/<ts>/menu_offer/...`
- resume: `runs/<ts>/menu_offer_resume_<ts2>/...`
- filed proposals: `proposals/YYYY/MM/<client>/<date>/...`
Macro NEW OFFER:
`python skills/evochia-ops/scripts/run_pipeline.py menu-offer --text "2026-04-10 | 40 άτομα | DEL finger | 30€/άτομο | client: Demo\nNigiri Salmon — 40 portions | σολομός 200g, ρύζι sushi 140g"`
Macro PATCH & RESUME:
`python skills/evochia-ops/scripts/run_pipeline.py resume --menu-offer-run runs/<ts>/menu_offer --apply-recipe-review-csv skills/evochia-ops/data/imports/recipe_review_patch.csv`
Macro SEARCH & OPEN:
`python skills/evochia-ops/scripts/run_pipeline.py search-proposals --client demo --date-from 2026-01-01 --service DEL --limit 5 --reindex`
`python skills/evochia-ops/scripts/run_pipeline.py open-result --search-run runs/<ts>/search --n 1`
