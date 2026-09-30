# NinkoSports News — OpenAI i prevodi, 30. septembar 2026.

OpenAI je dodat u postojeći News lanac. Nema drugog news sistema. API ključ ostaje u postojećem News secret okruženju; nije u repozitorijumu, izveštaju ni logovima.

## Objavljene verzije

- News backend: `2da8129ac4d51a4f734bc313cb3e6259cd92e3cc`, grana `ops/news-free-probe-20260926`; testirano stablo `6812fdac8595dab23c0596090a23fd147c8678b2`.
- News worker deployment: `9d188ff1-51e1-4c64-bd3d-a6317705d53c`.
- Frontend: `7bd60b8b8f53890b51d17b54c5b42f1c220c96f5`, grana `master`; testirano stablo `35acbbcec4b3cd34043efe9c89a5de44895282fa`.
- Frontend deployment: `9fd8df12-20e8-4058-9e79-99df62b542a0`.

## Model i provider lanac

Autentifikovan GET /v1/models na stvarnom News API nalogu potvrdio je `gpt-6-luna` među 133 vidljiva modela. Pilot je zatim dobio 20 uspešnih HTTP odgovora ovog modela.

Za važne fudbalske vesti koristi se postojeći `football_editorial_priority` i `PRIMARY_COMPETITIONS` iz `bot/news_football_priority.py`. Ne postoji nova kopirana lista prioriteta. Luna piše prva u toj grani. Ostale vesti prvo koriste postojeći besplatni writer, a Luna je rezerva za nedostupan ili odbijen nacrt. Pisanje koristi reasoning=low; prevod reasoning=none. Svi pozivi imaju standard service tier, bez tools i bez automatskog izbora drugog modela.

Svaki nacrt prolazi postojeće provere brojeva, imena, izvora, originalnosti, jezika i nezavisnog besplatnog semantičkog validatora. Nedostupan validator ne daje dozvolu za objavu. OpenAI nema pravo da dopunjava činjenice iz memorije. Klasifikacija, routing, dedupe, lige i sportske kategorije ostaju deterministički kod. Image pipeline nije promenjen. Rezultati utakmica nisu ulaz u ovaj provider.

Prevodi koriste postojeći DeepL Free, zatim besplatni AI lanac, zatim Lunu samo za jezike koji nisu uspešno prevedeni. Već spremni ili uspešni delimični prevodi ostaju sačuvani. Plaćeni prevod prolazi i nezavisnu semantičku proveru.

## Budžet i evidencija

Podešavanja samo na News servisu:

```dotenv
OPENAI_API_KEY=<postojeci-secret>
OPENAI_MODEL=gpt-6-luna
OPENAI_ENABLED=true
OPENAI_DAILY_BUDGET_USD=0.50
OPENAI_MONTHLY_BUDGET_USD=15.00
OPENAI_TOTAL_BUDGET_USD=15.00
OPENAI_EXPENSIVE_MODELS_ENABLED=false
OPENAI_WEB_SEARCH_ENABLED=false
OPENAI_ROLLOUT_MODE=production
OPENAI_PRODUCTION_APPROVED=true
OPENAI_MAX_REQUESTS_PER_CYCLE=2
OPENAI_DRY_RUN_ARTICLES=20
NEWS_TRANSLATIONS_ENABLED=1
NEWS_TRANSLATIONS_PER_CYCLE=3
NEWS_TRANSLATION_LANGUAGES_PER_ARTICLE=1
```

Dnevni i mesečni periodi računaju se u UTC. Dodatni ukupni limit od $15 čuva približno $5 od početnih $20 i kada kalendar pređe u novi mesec. Taj ukupni limit se ne resetuje automatski.

Dve nove News tabele, `news_openai_gate` i `news_openai_usage`, koriste postojeću PostgreSQL konekciju. Pre slanja se pod trajnim zaključavanjem rezerviše konzervativna maksimalna cena zahteva. Računaju se i paralelni zahtevi. Nakon poznatog odgovora rezervacija se zamenjuje procenom po stvarnim tokenima. Kod timeouta ili nepoznatog ishoda rezervacija ostaje zauzeta, a isti zahtev se automatski ne ponavlja.

Evidencija sadrži model, svrhu, jezik, ulazne/keširane/cache-write/izlazne tokene, procenu USD, vreme, source hash, article ID, status i ishod provere. Pre objave article ID još ne postoji; trajni source hash povezuje pokušaj sa člankom kada ga postojeći publisher sačuva. Idempotentnost obuhvata izvor, verziju činjenica, svrhu i jezik. Izmena prompta sama ne naplaćuje isti izvor ponovo.

Dosegnut limit zatvara samo plaćenu granu. Besplatni provideri ostaju u radu. Ni stari OpenAI legacy poziv više ne može da zaobiđe monetarni tracker.

## Pilot na 20 stvarnih članaka

Sirovi merni podaci su u `openai-pilot-2026-09-30.json`. Ovo su stvarni API tokeni iz redovnog source-ingestion toka, sa USD izračunatim po zvaničnim cenama, a ne sintetički odgovori.

| Mera | Rezultat |
|---|---:|
| Plaćene operacije | 20 |
| Duple plaćene operacije | 0 |
| Ulazni tokeni ukupno | 48.669 |
| Keširani ulazni tokeni | 23.292 |
| Cache-write tokeni | 2.588 |
| Izlazni tokeni, uključujući reasoning | 6.901 |
| Ukupna procena troška | $0.00628582 |
| Prošlo sve gateove | 9 |
| Zadržano zbog provera | 11 |
| Poslednjih pet sa konačnim podešavanjem | 5/5 prošlo |
| Trošak poslednjih pet | $0.00230481 |

Prvih pet zadržanih nacrta bilo je prekratko. Zato je dopunjeno uputstvo za zaseban puni body od približno 180–240 reči, bez ponavljanja i izmišljanja. Kasniji gateovi zadržali su dodatne brojeve, naziv koji izvor nije naveo, preveliko preklapanje sa izvorom, nepodudaranje takmičenja i izvor tipa analiza. Provere nisu olabavljene. Zatim je za pisanje uključen reasoning=low na istom Luna modelu: poslednjih pet prošlo je sve provere. Nijedan Luna tekst nije objavljen kroz dry-run granu.

Konačni mali uzorak daje oko $0.000461 po pisanju, odnosno **$0.2305 za 500 Luna pisanja dnevno** i **$6.91 za 30 dana**. To je projekcija po pet uspešnih članaka, ne obećanje prolaznosti ili količine. Prevodi i eventualni dodatni pokušaji drugih članaka nisu uključeni u ovu writer projekciju. U stvarnom smart routingu deo vesti ostaje besplatan; ukupna plaćena obrada svih svrha deli iste limite $0.50/$15.

Zvanična standardna cena po milion tokena: input $0.10, cached input $0.01, cache writes $0.125, output $0.50. Izvor: https://developers.openai.com/api/docs/models/gpt-6-luna (provereno 30.09.2026).

## Ispravka problema sa srpskim

Na stvarnom članku 22305 endpoint za srpski vraćao je `available:false, status:missing`. Navigation je imala svoje prevode, ali tekst vesti nije imao spremljen prevod. Kartice i hero naslovi takođe nisu učitavali postojeće prevode.

- Prevod sada ima ograničen deo od četiri zahteva na početku ISTOG News ciklusa, pa ga pisanje ne može potpuno potisnuti. Ukupni postojeći dnevni/request limiti nisu povećani.
- Obrada bira do tri članka po ciklusu, jedan nedostajući jezik po članku, prvo članke bez srpskog. Spremni jezici se ne prevode ponovo.
- Istek malog dela kvote ne označava neobrađene članke kao neuspele.
- Ispravljena je lažna blokada za `Defender Vivian`: uloga se prevodi, ali ime `Vivian` ostaje zaključano. Isto važi za eksplicitne uloge u postojećoj heuristici.
- Naslov, sažetak i body čitaoca koriste postojeći translation endpoint. News kartice, hero, latest/most-read, pager i News sidebar koriste spremljene prevode.
- Najviše četiri istovremena GET zahteva za prevod, sa keširanjem i spajanjem duplikata. Klik čitaoca ne poziva plaćeni AI.
- Nedostajući prevod je jasno označen lokalizovanom porukom i dugmetom za novu proveru.

Produkcioni rezultat stvarnog srpskog prevoda: **provera redovnog ciklusa u toku**. Ne tvrditi da su svi stari članci i svi jezici već popunjeni.

## Testovi i granice scope-a

Poslednji kompletan relevantni backend skup: 296 prolaznih testova. Poslednja dodatna ispravka raspoređivanja: 81 fokusirani test prolazi, uključujući novu proveru neobrađenih članaka. Frontend: 39 prolaznih News/API/UI testova i uspešan production build.

Budžet je testiran na konkurentnim rezervacijama, restartu, UTC prelasku dana/meseca, timeoutu, izgubljenom odgovoru, zabranjenom modelu, keširanom odgovoru, fallbacku i neispravnoj konfiguraciji. Stvarna PostgreSQL probe provera potvrdila je blokadu dnevnog, mesečnog i ukupnog limita uz nula plaćenih poziva. Limit nije dokazivan trošenjem korisnikovih $15.

Backend diff prema pre-task `dd1144ec6042c4fee466472e4927d5948c2a6c56` sadrži samo News writer/router/translation/scheduler kod i News testove. Frontend diff prema `8ee13e024b917184d479392ae88ee17d8f91069d` sadrži samo News prikaz i translation GET funkciju/testove. Po 18 imenovanih zaštićenih live-score/fixture/result/standings/image putanja u proverama ostalo je identično; potpuni diff nema live-score izmene.

Neizmenjeni servisi:
- Shared API: deployment `a6018808-ec70-44a9-8ddc-5a65b30f9c57`.
- Results worker: deployment `25287c7e-08a8-46f8-aa3b-0d85ba6eaf53`.
- Oba ostaju na `ff091f98b6c879c85978d78df7bdcd0853b08dfb`, deployment iz 27. septembra.
- Nisu menjane konfiguracije ni kod Live Scores, fixtures, standings ili results worker-a.
- Railway AI agent nije korišćen. Kod je rađen direktno, deployment postojećih News/News-UI izmena preko konektora.
