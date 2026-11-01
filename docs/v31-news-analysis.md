# V3.1 — news false-positive analysis (eval120, frozen `7b8fc69`)

**§1–§5 are diagnosis only; no code was changed for them** (commit 44c5f59). §6–§8 were added afterwards and
describe the comparison of approaches and the chosen design. Every news item that V3 candidate 2 (`7b8fc69`) published
on the independent `eval120` sample and that was labelled incorrect (29 items) was re-run through an instrumented
replay of the captured bytes, using `measurements/v3-remediation-2026-11-01/audits/eval120/diag-29-errors.json`. For
each item the replay records:
- the item-gate decision (`classify_item`) and the subject decision (`subject_of`);
- the source page or feed, and the extraction method;
- the date evidence;
- the full body text available in the captured bytes: the feed's `content:encoded` or description, the listing card,
  or the article page if it was fetched.

`eval120` is consumed. It is used here for **diagnosis**, and nothing below is reported as independent validation of a
later change.

## Correction to the category counts

The 29 news errors are:

| Category | Count |
|---|---|
| Content marketing (A) | **20** |
| Parent/group stories (B) | **5** |
| Other (C, D) | **4** |

The "8 group errors" figure counts these 5 news items together with the **3 social profiles** of the same company
(BE KRAFTSALG AS). Those 3 profiles are this sample's 3 social errors, analysed in §4.

## 1. Categories

| Code | Category | News errors | Mechanism (why V3 accepted it) |
|---|---|---|---|
| A1 | Property, plot or project listing published as a blog post | 7 | A `/post/` address on a Wix blog feed (`blog-feed.xml`), or a WordPress root post in the main feed, counts as article evidence (`article_news_path`, `article_main_feed`). The subject is "unstated, on the company's own website", which V3 accepts. No rule looks at the body. |
| A2 | Reader advice, guide or tips | 8 | As A1. The advice rules look only at titles. Most of these titles carry no advice marker ("Markløft: Den ultimative øvelsen …", "Treningsdagbok er forskjellen …"). The body is plainly second-person advice. |
| A3 | Promotional or thought-leadership post | 3 | As A1. Blog listing cards (`/en/blog/…`) with a visible date. |
| A4 | Service or membership page via the blog | 2 | A WordPress blog post ("Melde skade?") and a page with JSON-LD `datePublished` under `/blog/nyheter/`. |
| B | Group-brand story on a site named after the registry parent | 5 | The registry website of BE KRAFTSALG AS is `bodoenergi.no`. V3's operator assessment returns `self`, because the site states BE Kraftsalg's own organisation number. The registry's group structure (`konsernstruktur`, already fetched) shows BE KRAFTSALG AS as a 100% subsidiary of **BODØ ENERGI AS (890892612)**, the organisation the domain is named after. *Corrected in §6.1:* the site is BE Kraftsalg's own (footer: "© 2026 Bodø Energi Kraftsalg · BE Kraftsalg AS · Org.nr. 990 892 687"), trading under the parent's brand, so a story under the "Bodø Energi" name may be either company's. |
| C | Non-article CMS page in the feed | 3 | A WordPress site uses posts as pages: a course offer ("Akvakurs 2026"), a topic page ("Mekanisk behandling") and a "new website" welcome post. They arrive through the feed or the news listing. |
| D | General topic article in a news section | 1 | `/aktuelt/` listing (Frosterød Takst: "Avhendingsloven – tryggere bolighandel", a law explainer). |

**What the errors have in common.** All 29 were accepted on **where** they appeared — a blog or news path, the main
feed, a news listing — never on **what they say**. In 26 of the 29 the subject decision was `UNSTATED`, meaning the
item does not name the company, which V3 accepts on a self-operated site. The 3 exceptions name the company only
incidentally: in the page chrome ("Blogg – Nordic Solutions AS"), a membership page's title suffix, and a one-line
supplier caption.

**What is available to read.**
- Feed items carry their description and, usually, the full `content:encoded` body. Both are in the captured feed
  bytes, but V3 reads only a 240-character description.
- Listing items carry the card paragraph when there is one.
- Five items (BE Kraftsalg, Frosterød) have no body in the captured bytes: listing cards without text.

## 2. Every error

| # | Company (org) | Title | URL | Source (method / section) | Date evidence | Entity in item | Accepted by | Should be rejected because | Category | Systematic? |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | SARPSBORG OG OMEGNS BOLIGBYGGELAG (848720712) | Melde skade? | https://www.sobbl.no/blog/2022/11/09/melde-skade/ | site_feed / www.sobbl.no/feed/ | published: Wed, 09 Nov 2022 09:46:1 | does not name the company | `article_news_path`; subject UNSTATED | a standing service/membership instruction, not an article about a development | A4 | systematic |
| 2 | SARPSBORG OG OMEGNS BOLIGBYGGELAG (848720712) | Bli Medlem | SOBBL | Sarpsborg Og Omegns Boligbyggelag | https://www.sobbl.no/blog/nyheter/minside/ | jsonld_datePublished / www.sobbl.no/blog/nyheter/minside/ | published: 2026-08-18T12:53:25+02:0 | names the company (page title suffix) | `article_news_path`; subject THIS | a standing service/membership instruction, not an article about a development | A4 | systematic |
| 3 | BYGGMESTER FRANK AASHEIM AS (911711664) | Fra oven, Holaker | https://www.huspro.no/post/fra-oven-holaker | site_feed / www.huspro.no/blog-feed.xml | published: Wed, 10 Aug 2022 14:04:0 | does not name the company | `article_news_path`; subject UNSTATED | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |
| 4 | BYGGMESTER FRANK AASHEIM AS (911711664) | Holaker, Maura - flott eneboligtomt | https://www.huspro.no/post/holaker-maura-flott-eneboligtomt | site_feed / www.huspro.no/blog-feed.xml | published: Wed, 21 Sep 2022 09:17:2 | does not name the company | `article_news_path`; subject UNSTATED | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |
| 5 | BYGGMESTER FRANK AASHEIM AS (911711664) | Hurdal, Brustadsletta | https://www.huspro.no/post/hurdal-brustadsletta | site_feed / www.huspro.no/blog-feed.xml | published: Sat, 16 Jul 2022 11:46:0 | does not name the company | `article_news_path`; subject UNSTATED | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |
| 6 | BYGGMESTER FRANK AASHEIM AS (911711664) | Hurdal - Nytt prosjekt | https://www.huspro.no/post/hurdal-nytt-prosjekt | site_feed / www.huspro.no/blog-feed.xml | published: Fri, 24 Jun 2022 17:01:0 | does not name the company | `article_news_path`; subject UNSTATED | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |
| 7 | BYGGMESTER FRANK AASHEIM AS (911711664) | Storslått Villa! | https://www.huspro.no/post/storsl%C3%A5tt-villa | site_feed / www.huspro.no/blog-feed.xml | published: Tue, 09 Aug 2022 07:29:0 | does not name the company | `article_news_path`; subject UNSTATED | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |
| 8 | BYGGMESTER FRANK AASHEIM AS (911711664) | Enebolig med fokus på bærekraft og miljø sentralt i Maura | https://www.huspro.no/post/til-salgs-enebolig-med-fokus-p%C3%A5-b%C3%A | site_feed / www.huspro.no/blog-feed.xml | published: Wed, 19 Apr 2023 14:19:0 | does not name the company | `article_news_path`; subject UNSTATED | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |
| 9 | OSLO PT STUDIO AS (921774087) | Bekymrer du deg mer nå enn før du ble gravid? | https://www.opts.no/post/bekymrer-du-deg-mer-n%C3%A5-enn-f%C3%B8r-du-b | site_feed / www.opts.no/blog-feed.xml | published: Mon, 17 Aug 2026 12:13:0 | does not name the company | `article_news_path`; subject UNSTATED | addresses the reader with advice; no company event | A2 | systematic |
| 10 | OSLO PT STUDIO AS (921774087) | Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker | https://www.opts.no/post/hvorfor-matjournal-kan-v%C3%A6re-det-viktigst | site_feed / www.opts.no/blog-feed.xml | published: Thu, 23 Apr 2026 18:57:1 | does not name the company | `article_news_path`; subject UNSTATED | addresses the reader with advice; no company event | A2 | systematic |
| 11 | OSLO PT STUDIO AS (921774087) | Markløft: Den ultimative øvelsen for styrke og funksjonalitet | https://www.opts.no/post/markl%C3%B8ft-den-ultimative-%C3%B8velsen-for | site_feed / www.opts.no/blog-feed.xml | published: Sun, 07 Apr 2024 22:00:0 | does not name the company | `article_news_path`; subject UNSTATED | addresses the reader with advice; no company event | A2 | systematic |
| 12 | OSLO PT STUDIO AS (921774087) | Oslo PT studio – et perfekt sted for å trene med en PT | https://www.opts.no/post/oslo-pt-studio-et-perfekt-sted-for-%C3%A5-tre | site_feed / www.opts.no/blog-feed.xml | published: Tue, 13 Sep 2022 11:44:5 | does not name the company | `article_news_path`; subject UNSTATED | promotes the service or the author's views; no dated company development | A3 | systematic |
| 13 | OSLO PT STUDIO AS (921774087) | Treningsdagbok er forskjellen på å trene og faktisk få resultater | https://www.opts.no/post/treningsdagbok-er-forskjellen-p%C3%A5-%C3%A5- | site_feed / www.opts.no/blog-feed.xml | published: Fri, 24 Apr 2026 12:22:5 | does not name the company | `article_news_path`; subject UNSTATED | addresses the reader with advice; no company event | A2 | systematic |
| 14 | FROSTERØD TAKST AS (924782544) | Avhendingsloven - tryggere bolighandel | https://www.takstmannen.no/aktuelt/avhendingsloven-tryggere-bolighande | article_time_datetime / www.takstmannen.no/aktuelt | published: 2021-02-15T16:46:25+01:0 | does not name the company | `article_news_path`; subject UNSTATED | explains a law change to home buyers; nothing about the company | D | isolated |
| 15 | DAY OF WEEK AS (927176963) | Order Software Like Takeaway: Delivery-First Development for the Agent | https://dayofweek.com/en/blog/delivery-first-development-agentic-era | listing_visible_date / dayofweek.com/en | stated_on_page: 2026-02-24 | does not name the company | `article_news_path`; subject UNSTATED | promotes the service or the author's views; no dated company development | A3 | systematic |
| 16 | DAY OF WEEK AS (927176963) | The new AI days: delivering more in a week than most ship in a month | https://dayofweek.com/en/blog/the-new-ai-days | listing_visible_date / dayofweek.com/en | stated_on_page: 2026-02-11 | does not name the company | `article_news_path`; subject UNSTATED | promotes the service or the author's views; no dated company development | A3 | systematic |
| 17 | FISKERIFAGLIG OPPLÆRINGSKONTOR FOR ROG (974683296) | Akvakurs 2026 | https://ffor.no/akvakurs2021-2/ | site_feed / ffor.no/feed/ | published: Tue, 03 Mar 2026 10:00:2 | does not name the company | `article_on_news_listing`; subject UNSTATED | a course offer, a topic page and a 'new website' welcome post published as WordPress posts | C | systematic (WordPress sites using posts as pages) |
| 18 | FISKERIFAGLIG OPPLÆRINGSKONTOR FOR ROG (974683296) | Mekanisk behandling | https://ffor.no/mekanisk-behandling/ | site_feed / ffor.no/feed/ | published: Tue, 20 Mar 2018 12:53:4 | does not name the company | `article_on_news_listing`; subject UNSTATED | a course offer, a topic page and a 'new website' welcome post published as WordPress posts | C | systematic (WordPress sites using posts as pages) |
| 19 | FISKERIFAGLIG OPPLÆRINGSKONTOR FOR ROG (974683296) | Velkommen | https://ffor.no/velkommen/ | site_feed / ffor.no/feed/ | published: Wed, 30 Aug 2017 13:14:0 | does not name the company | `article_main_feed`; subject UNSTATED | a course offer, a topic page and a 'new website' welcome post published as WordPress posts | C | systematic (WordPress sites using posts as pages) |
| 20 | NORDIC SOLUTIONS AS (985095779) | 11 Windows 11 tips - Jobb mer effektivt | https://www.ns.no/blog | listing_visible_date / www.ns.no/blog | stated_on_page: 25. mars 2026 | company named only in the listing page chrome ("Blogg – Nordic Solutions AS") | `article_news_path`; subject THIS | addresses the reader with advice; no company event | A2 | systematic |
| 21 | NORDIC SOLUTIONS AS (985095779) | Phishing og sosial manipulasjon – slik beskytter dere virksomheten | https://www.ns.no/blog | listing_visible_date / www.ns.no/blog | stated_on_page: 14. apr. 2026 | company named only in the listing page chrome ("Blogg – Nordic Solutions AS") | `article_news_path`; subject THIS | addresses the reader with advice; no company event | A2 | systematic |
| 22 | NORDIC SOLUTIONS AS (985095779) | Mobilsikkerhet for bedrifter – 8 tiltak | https://www.ns.no/blog | listing_visible_date / www.ns.no/blog | stated_on_page: 16. apr. 2026 | company named only in the listing page chrome ("Blogg – Nordic Solutions AS") | `article_news_path`; subject THIS | addresses the reader with advice; no company event | A2 | systematic |
| 23 | BE KRAFTSALG AS (990892687) | Bodø Bunkermuseum får Bodø Energi-gaven | https://bodoenergi.no/aktuelt/bodo-bunkermuseum-bodo-energi-gaven | listing_visible_date / bodoenergi.no/aktuelt | stated_on_page: 31. august 2026 | names BODØ ENERGI (parent), not BE KRAFTSALG | `article_news_path`; subject UNSTATED | the site is the registry parent's (BODØ ENERGI AS); the story is the parent's sponsorship/community activity and does not name BE KRAFTSALG AS | B | systematic |
| 24 | BE KRAFTSALG AS (990892687) | Bodø Energi-løpet under Marcialonga Bodø – 6 km med ekte lokal energi! | https://bodoenergi.no/aktuelt/bodo-energi-lopet-under-marcialonga-bodo | listing_visible_date / bodoenergi.no/aktuelt | stated_on_page: 18. mai 2026 | names BODØ ENERGI (parent), not BE KRAFTSALG | `article_news_path`; subject UNSTATED | the site is the registry parent's (BODØ ENERGI AS); the story is the parent's sponsorship/community activity and does not name BE KRAFTSALG AS | B | systematic |
| 25 | BE KRAFTSALG AS (990892687) | Musikk, mestring og store drømmer – SlåDæNed fikk Bodø Energi Gaven | https://bodoenergi.no/aktuelt/sladaened-mottok-bodo-energi-gaven | listing_visible_date / bodoenergi.no/aktuelt | stated_on_page: 18. mai 2026 | names BODØ ENERGI (parent), not BE KRAFTSALG | `article_news_path`; subject UNSTATED | the site is the registry parent's (BODØ ENERGI AS); the story is the parent's sponsorship/community activity and does not name BE KRAFTSALG AS | B | systematic |
| 26 | BE KRAFTSALG AS (990892687) | Stafett for livet på Fauske mottok Bodø Energi-gaven | https://bodoenergi.no/aktuelt/stafett-for-livet-pa-fauske-mottok-bodo- | listing_visible_date / bodoenergi.no/aktuelt | stated_on_page: 12. oktober 2026 | names BODØ ENERGI (parent), not BE KRAFTSALG | `article_news_path`; subject UNSTATED | the site is the registry parent's (BODØ ENERGI AS); the story is the parent's sponsorship/community activity and does not name BE KRAFTSALG AS | B | systematic |
| 27 | BE KRAFTSALG AS (990892687) | Vil skape et enda sterkere fellesskap på Kjerringøy | https://bodoenergi.no/aktuelt/vil-skape-et-enda-sterkere-fellesskap-pa | listing_visible_date / bodoenergi.no/aktuelt | stated_on_page: 18. juni 2026 | names BODØ ENERGI (parent), not BE KRAFTSALG | `article_news_path`; subject UNSTATED | the site is the registry parent's (BODØ ENERGI AS); the story is the parent's sponsorship/community activity and does not name BE KRAFTSALG AS | B | systematic |
| 28 | CONNOISSEUR AS (998263743) | Ikke tygg sjokoladen | https://www.sjokoladesmaking.no/nyheter/ikke-tygg-sjokoladen/ | site_feed / www.sjokoladesmaking.no/feed/ | published: Fri, 28 Oct 2022 17:00:0 | does not name the company | `article_news_path`; subject UNSTATED | addresses the reader with advice; no company event | A2 | systematic |
| 29 | KYSTSNEKKER'N AS (998355389) | Ferdige fasader i øyriket | https://www.kystsnekkern.no/ferdige-fasader-i-oyriket/ | site_feed / www.kystsnekkern.no/feed/ | published: Fri, 25 Jul 2025 18:44:3 | names the company as supplier in a one-line project caption | `article_main_feed`; subject THIS | describes a property, plot or completed job for sale/marketing; no company development | A1 | systematic |

## 3. The three reader-addressing cases

| Item | Title rule (V3 candidate 2) | Body text (captured) | Qualifies? |
|---|---|---|---|
| 911771098 "Du store verden" (2018-08-17, homepage article card) | Not advice: bare pronoun | "Bøker kan reise over hele verden … «Detektivbyrå nr. 2» oversettes nå til 18 språk … «Det aller beste» er allerede solgt til Kina, Danmark, Island, Romania og Tyrkia … figurene mine reist til over 20 land" | **Yes.** A company milestone (translation and international sales of its books) in the company's own voice. |
| 921774087 "Bekymrer du deg mer nå enn før du ble gravid?" (feed) | Not advice: "du deg" is not in the narrow construction list | "Hjernen vår liker å ha kontroll. Så hva skjer når hormoner herjer med kropp og hode? … Du vet ikke hvordan morgendagen blir …" | **No.** Second-person advice; no company event. |
| 921774087 "Hvorfor matjournal kan være det viktigste verktøyet du ikke bruker" (feed) | Not advice: "du ikke bruker" is not in the list | "Har du lurt på hvor mange ganger i uken du bør trene styrke for å oppnå dine mål? …" | **No.** Second-person advice. |

**Conclusion.** No title-only rule separates these three cases. "Du store verden" and the two advice titles share the
same surface feature, a bare second-person pronoun. **The body text separates them cleanly:**
- **company-development evidence in the company's voice:** translations, sales, deliveries, appointments, openings;
- **versus second-person instruction.**

The V3.1 rule must therefore be content-based. No URL or company exception is used.

## 4. Social errors (eval120: 40 correct / 43 decided = 93.0%)

| Profile | Accepted by | Should be rejected because |
|---|---|---|
| `facebook.com/bodoenergi` | `handle_is_own_domain_name` | The handle is the website's domain name, but the website belongs to the registry parent BODØ ENERGI AS. |
| `instagram.com/bodoenergi` | `handle_is_own_domain_name` | Same. |
| `linkedin.com/company/bodo-energi` | `handle_is_own_domain_name` | Same. |

All three errors come from the same defect as category B. When a subsidiary's registry website is named after its
registry parent, V3 treats every name on the site as the subsidiary's. **This is general:** every subsidiary whose
registry website carries a registry group company's name is affected. It is not specific to this company.
(*Corrected in §6.1:* the website is the subsidiary's own, not the parent's; the profiles carry the shared brand.)

## 5. Implications for the design

1. **Source.** A news or blog path, a feed, or a listing is necessary context, but **never** sufficient. Blogs (`/post/`,
   `/blog/`, `blog-feed.xml`) and root WordPress posts produced 22 of the 29 errors (A1–A4 and C).
2. **Item.** Property and plot listings, course offers, membership and service pages, and welcome posts are
   recognisable from their title and body vocabulary: "til salgs", "tomten er på 657 kvm", "meld din interesse", "ta
   kontakt … for påmelding", "Bli medlem", "ny nettside".
3. **Content.** The decisive signal is in the body: whether the item reports a dated development of the company (in its
   own voice, or naming it), or instructs or advises the reader. When neither title nor body provides that evidence,
   the item must be **withheld**.
4. **Entity.** The registry group structure must be used: a site named after the registry parent is a group site. Its
   stories and profiles are the subsidiary's only when they name the subsidiary.
