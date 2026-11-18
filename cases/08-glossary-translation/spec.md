# Case 08: Terminology-locked translation

## Task

Translate a Swedish product description (80-250 words) into English, as plain text, using a mandatory
40-term glossary (Swedish term -> required English rendering, plus two forbidden English alternatives per
term). The glossary is embedded in the system prompt. Shift items additionally use an unseen 20-term
extension of the glossary, which is supplied in the user message after the source text, prefixed
"Additional glossary". The prompt's 40-term glossary never changes.

The user message is the Swedish source text; for shift items it is the source text, a blank line and the
additional glossary (the harness default: input + blank line + context). The full 20-term extension is
supplied with every shift item, whichever terms that item uses.

## Output contract

- The English translation of the whole source, as plain text: no Markdown of any kind, no introduction or
  closing remark, no translator's notes.
- Brand and product names are kept as written. Fluency, style and faithfulness beyond the checks below are
  **not scored** (the write-up says so).

## Items (plan first)

Each plan decides, before any text exists: a product domain and product type, an invented brand
(`harness.entities.companies("main")`, or `companies("shift")` for shift items; single-word names only) and an
invented product name (`harness.entities.products()`), a style, an opening, 1-3 paragraphs, a target length
band, and 3-8 glossary terms with, per term, a **mode** and the **surface** string the source must contain.

- Main items: 3-8 terms in total, 1-3 of them generic terms (warranty, delivery, packaging, ...), the rest
  from the domain's term list; all from the 40-term glossary.
- Shift items: 3-6 extension terms from one extension domain plus 0-2 generic terms of the main glossary
  (3-8 in total). Slice-specific modes are applied to extension terms only.
- Terms that cannot co-occur are never planned together: two terms are incompatible when one term's
  avoid-pattern (below) matches a Swedish string of the other, or a forbidden alternative of one matches
  inside the required rendering of the other.

Modes (and what code verification checks in the Swedish source, case-insensitive):

| mode | source must contain |
| --- | --- |
| lemma | the base form as a whole word (word boundaries; a hyphen counts as a boundary, so "USB-kontakt" contains "kontakt") |
| form | the planned inflected form (from the term's form list) as a whole word |
| compound | the planned compound (from the term's compound list) starting at a word boundary; a Swedish ending may follow |
| list | the base form as a whole word inside one sentence that holds all list terms and at least (number of list terms - 2) commas |
| twice | at least two whole-word occurrences of the base form or any listed inflected form |

## Slices

- **plain**: every planned term in mode `lemma`.
- **inflected_forms**: 2-3 terms in mode `form` (a planned inflected form, e.g. "laddaren", "batterierna",
  "vattentätt"); the others `lemma`.
- **compound_words**: 1-2 terms in mode `compound` (e.g. "snabbladdare", "garantitid"); the others `lemma`.
  The English rendering of a compound contains the term's required rendering (fast charger, warranty period).
- **terms_in_lists**: 3-4 noun terms in mode `list`, written as one inline comma-separated enumeration (never
  a bulleted list); the others `lemma`.
- **terms_used_twice**: 1-2 terms in mode `twice`; the others `lemma`. For these terms the required rendering
  must appear at least twice in the translation (minimum count 2); a pronoun or a synonym for the second
  mention fails.
- Slices are equally weighted in main and shift sets.

## Source verification (generation time)

Code checks: 80-250 words (word definition below); no Markdown or line-start list markers; brand and product
name present verbatim; every planned surface present as defined by its mode; and no **avoid-pattern** of a
planned term occurs. Avoid-patterns are Swedish words whose faithful translation would naturally be one of
the term's forbidden alternatives (e.g. "påse" -> pouch for fodral, "frakt" -> shipping for leverans,
"garantera" -> guarantee for garanti); they live in `case.py` (`avoid`) and are not part of the scored
answer. Then gpt-6-luna flags texts where a planned term is used in another meaning or other wording would
need a forbidden alternative; flagged items are dropped. Unplanned glossary terms in the source are allowed
and are not scored.

## Expected output (label)

`label(plan)` = `{"terms": [{"sv", "en", "forbidden", "min_count"}...], "length_ratio": LENGTH_RATIO,
"length_bounds": [0.8, 1.4]}` for the planned terms, in plan order. It reads the plan only.

## Scoring (deterministic)

`parse` returns the output text and the Swedish source word count (computed from the item input; this is the
only text-derived quantity, the label itself is plan-only). Matching works on a normalised copy of the
output: lower-cased, typographic apostrophes -> `'`, every hyphen or dash character -> a space, whitespace
runs -> one space. Rendering and forbidden phrases are normalised the same way (so "hard-wearing" = "hard
wearing", "water-resistant" = "water resistant").

A phrase **matches** when one of its variants occurs with no letter, digit or underscore directly before or
after it. Variants inflect only the last word of the phrase: the word itself, +"s", +"es", "y" -> "ies"
after a consonant, and, when the word ends in "s", the word without its final "s". So "charger" matches
"charger", "chargers", "charger's", "chargers'"; "battery" matches "batteries"; "dimensions" matches
"dimension"; "lamp" does not match "headlamp"; "fan" does not match "fanatic". Other spellings
("lawnmower" for "lawn mower", "programme" for "program") do not match.

Pass requires all four checks:

1. **Required renderings**: for every planned term, the required rendering matches at least `min_count`
   times (1; 2 for `twice` terms). Category `missing_term` (0 matches) or `repeat_not_kept` (1 match where
   2 are required).
2. **No forbidden alternative**: none of the planned terms' forbidden alternatives matches anywhere in the
   output. Forbidden alternatives of unplanned terms are not checked. Category `forbidden_term`.
3. **Plain text, no framing**: the output contains no Markdown: no line starting with `#`, `-`, `*`, `+`,
   `•` followed by a space, a number followed by `.` or `)` and a space, or `>`; no `**`, `__` or backtick
   anywhere; no table row (a line starting and ending with `|`); no `[text](url)` link. And no framing: the
   first line does not start with "Here is", "Here's", "Sure", "Certainly", "Below is", "Translation:",
   "English translation", "English version" or "Translated text", and no line starts with "Note:",
   "Notes:", "Translator's note:" or "N.B.:". Categories `markdown`, `preamble`. These are the
   output-contract (`valid`) checks.
4. **Length**: words(output) / reference is within [0.8, 1.4], where reference = words(Swedish source) x
   LENGTH_RATIO. Categories `too_short`, `too_long`.

Words are counted as maximal runs of letters/digits, joined by an apostrophe or hyphen
(regex `[^\W_]+(?:['’\-][^\W_]+)*`): "USB-C-kontakt" is one word, "5 000" two, "2,5" two.

LENGTH_RATIO = 1.15 (English words per Swedish word, calibrated on pilot translations by the legacy prompt
before sealing and fixed here; on the 28 pilot items the legacy translations averaged 0.995 x this reference).

**Nonanswer**: empty output; a refusal; or an output shorter than half the reference that ends with "?" or
contains a refusal or clarification phrase ("I can't", "I cannot", "I'm sorry", "I'm unable", "could you
provide/clarify"). Nonanswers fail, are invalid, and get category `nonanswer`.

Secondary per item: `term_recall` (share of planned terms meeting their minimum count), `forbidden_hits`,
`length_ratio`. Aggregates: mean term recall, share of items with a forbidden hit, mean length ratio.

Known limitations (accepted): common-word renderings ("case", "mode", "control", "fan") can match unrelated
uses and pass a term spuriously; a forbidden alternative used in an unrelated sense ("toggle" as a verb)
fails the item.

## Answer strings

The main glossary is part of the prompt by design, so its renderings are not answer strings. For shift
items, the English renderings of the extension terms (at least 5 characters) are answer strings: the
optimiser must never put them in a prompt.

## Legacy setup

gpt-5.6-sol, Chat Completions, effort `none`, temperature 0. The system prompt embeds the 40-term glossary as
a list (`- sv -> en (NEVER: a, b)`), with an IMPORTANT block, all-caps ALWAYS/NEVER rules and "plain text
only". It tells the model to apply an "Additional glossary" from the user message with the same rules.
Markers: `NEVER`, `ALWAYS`, `IMPORTANT`, "plain text only", a `GLOSSARY` heading line, the list line
`- laddare -> charger`.

## Shift set

Same slices, unseen extension glossary (kitchenware, garden tools, outdoor gear) supplied per item, brands
from the unseen company pool.

## Glossary (40 terms, in the prompt)

| Swedish | required English | forbidden alternatives | inflected forms | compounds (English) |
| --- | --- | --- | --- | --- |
| laddare | charger | adapter, power supply | laddaren, laddarna | snabbladdare (fast charger); billaddare (car charger) |
| batteri | battery | accumulator, power cell | batteriet, batterier, batterierna | batteritid (battery life); reservbatteri (spare battery) |
| skärm | display | screen, panel | skärmen, skärmar, skärmarna | skärmstorlek (display size); skärmyta (display area) |
| fodral | case | pouch, sleeve | fodralet, fodralen | skyddsfodral (protective case); läderfodral (leather case) |
| sladd | cord | wire, flex | sladden, sladdar, sladdarna | strömsladd (power cord); förlängningssladd (extension cord) |
| kontakt | plug | connector, socket | kontakten, kontakter, kontakterna | stickkontakt (plug); USB-kontakt (USB plug) |
| strömbrytare | power switch | on/off switch, toggle | strömbrytaren, strömbrytarna | huvudströmbrytare (main power switch) |
| knapp | button | knob, toggle | knappen, knappar, knapparna | strömknapp (power button); startknapp (start button) |
| hölje | housing | casing, enclosure | höljet, höljen, höljena | aluminiumhölje (aluminium housing); plasthölje (plastic housing) |
| lock | lid | cap, hatch | locket, locken | glaslock (glass lid); skruvlock (screw lid) |
| fäste | mount | bracket, holder | fästet, fästen, fästena | väggfäste (wall mount); takfäste (ceiling mount) |
| reglage | control | slider, dial | reglaget, reglagen | volymreglage (volume control); temperaturreglage (temperature control) |
| sil | strainer | sieve, colander | silen, silar, silarna | tesil (tea strainer); kaffesil (coffee strainer) |
| behållare | container | tank, reservoir | behållaren, behållarna | vattenbehållare (water container); förvaringsbehållare (storage container) |
| munstycke | nozzle | spout, jet | munstycket, munstycken, munstyckena | sprutmunstycke (spray nozzle); ångmunstycke (steam nozzle) |
| slang | hose | tube, pipe | slangen, slangar, slangarna | trädgårdsslang (garden hose); vattenslang (water hose) |
| handtag | handle | grip, hilt | handtaget, handtagen | bärhandtag (carrying handle); gummihandtag (rubber handle) |
| givare | sensor | detector, probe | givaren, givarna | temperaturgivare (temperature sensor); rörelsegivare (motion sensor) |
| mätare | gauge | indicator, readout | mätaren, mätarna | tryckmätare (pressure gauge); nivåmätare (level gauge) |
| vattentät | waterproof | water-resistant, watertight | vattentäta, vattentätt | - |
| tålig | durable | robust, sturdy | tåliga, tåligt | - |
| slitstark | hard-wearing | wear-resistant, long-lasting | slitstarka, slitstarkt | - |
| trådlös | wireless | cordless, cable-free | trådlösa, trådlöst | - |
| uppladdningsbar | rechargeable | chargeable, reusable | uppladdningsbara, uppladdningsbart | - |
| inställning | setting | configuration, preset | inställningen, inställningar, inställningarna | värmeinställning (heat setting); hastighetsinställning (speed setting) |
| läge | mode | position, program | läget, lägen, lägena | nattläge (night mode); viloläge (sleep mode) |
| tillbehör | accessory | add-on, attachment | tillbehöret, tillbehören | extratillbehör (extra accessory); originaltillbehör (original accessory) |
| reservdel | spare part | replacement part, component | reservdelen, reservdelar, reservdelarna | - |
| garanti | warranty | guarantee, guaranty | garantin, garantier, garantierna | garantitid (warranty period); produktgaranti (product warranty) |
| bruksanvisning | user manual | instructions, guide | bruksanvisningen, bruksanvisningar | - |
| leverans | delivery | shipment, shipping | leveransen, leveranser, leveranserna | leveranstid (delivery time); hemleverans (home delivery) |
| förpackning | packaging | package, box | förpackningen | originalförpackning (original packaging); presentförpackning (gift packaging) |
| vikt | weight | mass, heft | vikten | totalvikt (total weight); nettovikt (net weight) |
| mått | dimensions | measurements, proportions | måtten | - |
| motor | motor | engine, drive unit | motorn, motorer, motorerna | elmotor (electric motor) |
| fläkt | fan | blower, ventilator | fläkten, fläktar, fläktarna | takfläkt (ceiling fan); kylfläkt (cooling fan) |
| lampa | lamp | bulb, luminaire | lampan, lampor, lamporna | bordslampa (table lamp); läslampa (reading lamp) |
| ljusstyrka | brightness | luminosity, luminance | ljusstyrkan | - |
| upplösning | resolution | definition, sharpness | upplösningen, upplösningar | bildupplösning (image resolution); videoupplösning (video resolution) |
| anslutning | connection | port, interface | anslutningen, anslutningar | nätverksanslutning (network connection); USB-anslutning (USB connection) |

## Extension glossary (20 terms, shift only, supplied with the item)

| Swedish | required English | forbidden alternatives | inflected forms | compounds (English) |
| --- | --- | --- | --- | --- |
| termos | vacuum flask | thermos, bottle | termosen, termosar | kaffetermos (coffee vacuum flask) |
| kastrull | saucepan | pot, casserole | kastrullen, kastruller | mjölkkastrull (milk saucepan) |
| stekpanna | frying pan | skillet, frypan | stekpannan, stekpannor | gjutjärnsstekpanna (cast-iron frying pan) |
| skärbräda | chopping board | cutting board, carving board | skärbrädan, skärbrädor | - |
| visp | whisk | beater, mixer | vispen, vispar | ballongvisp (balloon whisk) |
| lucka | door | hatch, flap | luckan, luckor | ugnslucka (oven door); glaslucka (glass door) |
| galler | grate | grill, grid | gallret | ugnsgaller (oven grate); skyddsgaller (protective grate) |
| ugnsvante | oven glove | oven mitt, kitchen glove | ugnsvanten, ugnsvantar | - |
| gräsklippare | lawn mower | grass cutter, grass trimmer | gräsklipparen | robotgräsklippare (robotic lawn mower) |
| sekatör | pruning shears | secateurs, pruners | sekatören, sekatörer | - |
| vattenkanna | watering can | water jug, sprinkling can | vattenkannan, vattenkannor | - |
| tältpinne | tent peg | tent stake, spike | tältpinnen, tältpinnar | - |
| sovsäck | sleeping bag | bedroll, sleep sack | sovsäcken, sovsäckar | dunsovsäck (down sleeping bag) |
| ryggsäck | backpack | rucksack, knapsack | ryggsäcken, ryggsäckar | vandringsryggsäck (hiking backpack) |
| pannlampa | head torch | headlamp, headlight | pannlampan, pannlampor | - |
| dragkedja | zip | zipper, slide fastener | dragkedjan, dragkedjor | tvåvägsdragkedja (two-way zip) |
| spänne | buckle | clasp, clip | spännet, spännen | bältesspänne (belt buckle); snabbspänne (quick-release buckle) |
| sula | sole | outsole, tread | sulan, sulor | gummisula (rubber sole) |
| foder | lining | liner, inner layer | fodret | fleecefoder (fleece lining); ullfoder (wool lining) |
| luva | hood | cap, cowl | luvan, luvor | - |

## Domains

Generic main terms (usable in every main domain): garanti, leverans, förpackning, tillbehör, reservdel, bruksanvisning, vikt, mått, tålig, slitstark, vattentät.

- electronics: laddare, batteri, skärm, fodral, sladd, kontakt, strömbrytare, knapp, trådlös, uppladdningsbar, inställning, läge, ljusstyrka, upplösning, anslutning, givare. Product types: wireless earbuds, portable speaker, smartwatch, tablet, e-reader, action camera, baby monitor, dashcam, gaming controller, video doorbell.
- kitchen: behållare, munstycke, lock, sil, reglage, hölje, motor, inställning, läge, sladd, strömbrytare, knapp, handtag, mätare, kontakt. Product types: espresso machine, electric kettle, food processor, air fryer, juicer, coffee grinder, milk frother, soup maker, rice cooker.
- garden: slang, munstycke, handtag, behållare, motor, sladd, mätare, reglage, fäste, kontakt, strömbrytare, batteri, uppladdningsbar. Product types: pressure washer, garden pump, drip irrigation kit, pond pump, garden sprayer, wet-and-dry vacuum cleaner.
- home: lampa, ljusstyrka, fläkt, fäste, reglage, strömbrytare, sladd, kontakt, läge, motor, hölje, trådlös, givare, inställning, knapp. Product types: desk lamp, floor lamp, ceiling fan, pedestal fan, air purifier, dehumidifier, bedside lamp.
- kitchenware: termos, kastrull, stekpanna, skärbräda, visp, lucka, galler, ugnsvante. Product types: cookware set, kitchen starter kit, baking set, compact oven, cabin kitchen kit.
- garden_tools: gräsklippare, sekatör, vattenkanna. Product types: garden tool set, allotment starter kit, garden care bundle.
- outdoor: tältpinne, sovsäck, ryggsäck, pannlampa, dragkedja, spänne, sula, foder, luva. Product types: camping kit, hiking bundle, winter jacket, trekking set, festival camping pack.
